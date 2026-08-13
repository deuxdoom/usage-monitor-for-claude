"""Supplementary usage detail read from local Claude Code session transcripts.

The ``/api/oauth/usage`` endpoint only reports a percentage and a reset time
for the five-hour and seven-day limits - it does not disclose token counts,
message counts, or which models were used.  Claude Code itself writes every
turn to a JSONL transcript under ``<config dir>/projects/**/*.jsonl``, and
each assistant turn's ``usage`` block carries exact token counts and the
model that produced it.  This module scans those files to answer "how much,
and with which models" for a given time window, entirely from data already
on disk - nothing beyond the existing ``/api/oauth/usage`` call leaves the
machine.

The numbers here are exact sums of what the transcripts recorded, not an
estimate; they will not exactly equal whatever internal accounting Anthropic
uses for the quota (a general availability-style guess about what a rate
limit measures), but they are real recorded consumption, not a heuristic.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    'ModelUsage', 'WindowStats', 'clear_cache', 'usage_in_window',
]

# A transcript file's mtime is treated as an upper bound on the timestamp of
# any entry inside it (Claude Code appends chronologically).  A file whose
# mtime falls before the window we are asked about cannot contribute, so it
# is skipped without being opened.  The buffer absorbs filesystem timestamp
# granularity and clock drift between the machine and the API's reported
# reset times.
_MTIME_SKIP_BUFFER_SECONDS = 3600


@dataclass(frozen=True)
class _LogEntry:
    """One assistant turn's token usage, as recorded in a transcript line."""

    timestamp: float  # Unix epoch, UTC
    total_tokens: int
    model: str
    dedupe_key: str | None


@dataclass
class _FileCache:
    """Parsed entries for one transcript file, valid as of (mtime, size)."""

    mtime: float
    size: int
    entries: list[_LogEntry]


@dataclass(frozen=True)
class ModelUsage:
    """One model's share of a window's token usage."""

    model: str
    tokens: int
    fraction: float  # 0..1 of the window's total_tokens


@dataclass(frozen=True)
class WindowStats:
    """Aggregated local-transcript usage for a time window."""

    total_tokens: int
    message_count: int
    models: list[ModelUsage] = field(default_factory=list)


_cache_lock = threading.Lock()
_file_cache: dict[Path, _FileCache] = {}


def clear_cache() -> None:
    """Drop all cached per-file parse results.

    Exists for tests and for the (unlikely) case of ``CLAUDE_CONFIG_DIR``
    changing mid-run; normal operation never needs to call this, since
    ``usage_in_window`` already re-parses a file whenever its mtime or size
    changes.
    """
    with _cache_lock:
        _file_cache.clear()


def _parse_timestamp(value: Any) -> float | None:
    """Parse a transcript entry's ``timestamp`` field to a Unix epoch.

    Returns ``None`` for anything not a non-empty ISO 8601 string, so a
    malformed or missing timestamp drops the entry rather than raising.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + '+00:00' if value.endswith('Z') else value
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _extract_entry(data: dict[str, Any]) -> _LogEntry | None:
    """Pull one usage entry out of a parsed transcript line, if it has one.

    Only assistant turns carry a token usage block.  A turn with usage but
    no billable tokens (e.g. logged before generation, or an interrupted
    turn without a completion) contributes nothing and is skipped.
    """
    if data.get('type') != 'assistant':
        return None

    message = data.get('message')
    if not isinstance(message, dict):
        return None

    usage = message.get('usage')
    if not isinstance(usage, dict):
        return None

    total = (
        (usage.get('input_tokens') or 0)
        + (usage.get('output_tokens') or 0)
        + (usage.get('cache_creation_input_tokens') or 0)
        + (usage.get('cache_read_input_tokens') or 0)
    )
    if total <= 0:
        return None

    timestamp = _parse_timestamp(data.get('timestamp'))
    if timestamp is None:
        return None

    model = message.get('model') or 'unknown'

    # Retried or resumed turns can appear twice in a transcript with the same
    # message/request pair; without a key to catch that, a retry would be
    # double-counted as extra usage that was never actually billed twice.
    message_id = message.get('id') or data.get('message_id')
    request_id = data.get('requestId') or data.get('request_id')
    dedupe_key = f'{message_id}:{request_id}' if message_id and request_id else None

    return _LogEntry(timestamp=timestamp, total_tokens=int(total), model=model, dedupe_key=dedupe_key)


def _parse_file(path: Path) -> list[_LogEntry]:
    """Parse every usage-bearing line in one transcript file.

    Malformed lines and I/O errors are skipped rather than raised - a
    transcript can be mid-write while this runs, and one bad line or a
    momentarily locked file must not blank out every other file's data.
    """
    entries: list[_LogEntry] = []
    try:
        with path.open('r', encoding='utf-8', errors='replace') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(data, dict):
                    continue
                entry = _extract_entry(data)
                if entry is not None:
                    entries.append(entry)
    except OSError:
        return []
    return entries


def _cached_entries(path: Path) -> list[_LogEntry]:
    """Return *path*'s parsed entries, reusing the cache when the file is unchanged."""
    try:
        stat = path.stat()
    except OSError:
        return []

    with _cache_lock:
        cached = _file_cache.get(path)
        if cached is not None and cached.mtime == stat.st_mtime and cached.size == stat.st_size:
            return cached.entries

    entries = _parse_file(path)

    with _cache_lock:
        _file_cache[path] = _FileCache(mtime=stat.st_mtime, size=stat.st_size, entries=entries)
    return entries


def usage_in_window(projects_dir: Path, start: float, end: float) -> WindowStats:
    """Sum local transcript usage for the half-open window ``[start, end)``.

    Parameters
    ----------
    projects_dir : Path
        The ``projects`` directory to scan (``<config dir>/projects``).
    start, end : float
        Window bounds as Unix epoch seconds, UTC.

    Returns
    -------
    WindowStats
        Zeroed out (empty ``models`` list) when the directory does not
        exist or nothing in it falls inside the window - never raises for
        a missing or empty directory.
    """
    if not projects_dir.is_dir():
        return WindowStats(total_tokens=0, message_count=0, models=[])

    total_tokens = 0
    message_count = 0
    tokens_by_model: dict[str, int] = {}
    seen_keys: set[str] = set()
    mtime_cutoff = start - _MTIME_SKIP_BUFFER_SECONDS

    for path in projects_dir.rglob('*.jsonl'):
        try:
            if path.stat().st_mtime < mtime_cutoff:
                continue
        except OSError:
            continue

        for entry in _cached_entries(path):
            if not (start <= entry.timestamp < end):
                continue
            if entry.dedupe_key is not None:
                if entry.dedupe_key in seen_keys:
                    continue
                seen_keys.add(entry.dedupe_key)

            total_tokens += entry.total_tokens
            message_count += 1
            tokens_by_model[entry.model] = tokens_by_model.get(entry.model, 0) + entry.total_tokens

    models = [
        ModelUsage(model=name, tokens=tokens, fraction=(tokens / total_tokens) if total_tokens else 0.0)
        for name, tokens in tokens_by_model.items()
    ]
    models.sort(key=lambda m: m.tokens, reverse=True)

    return WindowStats(total_tokens=total_tokens, message_count=message_count, models=models)
