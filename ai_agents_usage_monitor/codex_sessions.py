"""
Codex Session Rollouts
=======================

Read token counters from local Codex rollouts without accessing credentials.
Only numeric usage, model names and timestamps are retained in memory.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = ['CodexUsage']

# The local summary windows.  This module is where their lengths are
# decided; the popup matches its server bars against whatever comes back
# in the snapshot rather than repeating these numbers.
_FIVE_HOURS = 5 * 3600
_WEEK = 7 * 86400


@dataclass
class _Rollout:
    offset: int = 0
    model: str = 'Unknown'
    session_model: str = 'Unknown'
    total: int | None = None
    mtime: int = 0
    entries: list[tuple[float, str, int, int]] = field(default_factory=list)


class CodexUsage:
    """Incrementally read local rollouts and cache snapshots for 60 seconds.

    Parameters
    ----------
    root : Path or None
        Codex home; defaults to CODEX_HOME or the user's .codex directory.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
        self._files: dict[Path, _Rollout] = {}
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] | None = None
        self._checked = 0.0

    def snapshot(self) -> dict[str, Any]:
        """Return rolling five-hour and seven-day recorded token totals.

        Returns
        -------
        dict
            Windows with per-model totals, scan time and partial-read status.
            Missing records are unavailable, never evidence of zero usage.
        """
        with self._lock:
            now = time.time()
            if self._snapshot is not None and time.monotonic() - self._checked < 60 and int(now // 60) == int(self._snapshot['updated_at'] // 60):
                return self._snapshot
            partial = False
            paths: set[Path] = set()
            for folder in ('sessions', 'archived_sessions'):
                try:
                    for path in (self._root / folder).rglob('*.jsonl'):
                        if path.stat().st_mtime >= now - _WEEK:
                            paths.add(path)
                except OSError:
                    partial = True
            for path in paths:
                try:
                    self._read(path, now)
                except OSError:
                    partial = True
            self._files = {path: state for path, state in self._files.items() if path in paths}
            # Forked rollouts can repeat the parent's exact recorded events.
            entries = set()
            for state in self._files.values():
                entries.update(state.entries)
            windows = []
            for seconds in (_FIVE_HOURS, _WEEK):
                models: dict[str, int] = {}
                for timestamp, model, tokens, cumulative in entries:
                    if now - seconds <= timestamp <= now:
                        models[model] = models.get(model, 0) + tokens
                windows.append({
                    'seconds': seconds, 'tokens': sum(models.values()),
                    'models': [{'model': model, 'tokens': tokens} for model, tokens in sorted(models.items(), key=lambda item: (-item[1], item[0]))],
                })
            self._snapshot = {'windows': windows, 'updated_at': now, 'partial': partial, 'available': bool(entries)}
            self._checked = time.monotonic()
            return self._snapshot

    def _read(self, path: Path, now: float) -> None:
        """Consume complete appended lines and retry unfinished lines next time."""
        stat = path.stat()
        state = self._files.setdefault(path, _Rollout())
        if stat.st_size < state.offset or (stat.st_size == state.offset and stat.st_mtime_ns != state.mtime):
            state = _Rollout()
            self._files[path] = state
        with path.open('rb') as stream:
            stream.seek(state.offset)
            while line := stream.readline():
                if not line.endswith(b'\n'):
                    break
                state.offset = stream.tell()
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                self._consume(state, record)
        state.mtime = stat.st_mtime_ns
        state.entries = [entry for entry in state.entries if entry[0] >= now - _WEEK]

    def _consume(self, state: _Rollout, record: Any) -> None:
        """Use cumulative deltas so repeated token-count events are not billed twice."""
        if not isinstance(record, dict):
            return
        payload = record.get('payload')
        if not isinstance(payload, dict):
            return
        if record.get('type') == 'session_meta':
            # A session imported into the desktop history has no turn_context record
            # at all - its model is only named in the instruction provenance.  Nothing
            # else from base_instructions is read: it holds the full prompt text.
            state.session_model = _provenance_model(payload) or state.session_model
            state.model = state.session_model
            return
        if record.get('type') == 'turn_context':
            model = payload.get('model')
            state.model = model if isinstance(model, str) and model else state.session_model
            return
        if record.get('type') != 'event_msg' or payload.get('type') != 'token_count':
            return
        info = payload.get('info')
        if not isinstance(info, dict):
            return
        total = _tokens(info.get('total_token_usage'))
        last = _tokens(info.get('last_token_usage'))
        if total is None:
            return
        if state.total == total:
            return
        # The first event may inherit a parent thread's cumulative counters.
        delta = last if state.total is None or total < state.total else total - state.total
        state.total = total
        if delta is None or delta <= 0:
            return
        try:
            stamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                return
            timestamp = stamp.timestamp()
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return
        state.entries.append((timestamp, state.model, delta, total))


def _provenance_model(payload: dict[str, Any]) -> str:
    """Read the model a session was started with out of its instruction provenance."""
    instructions = payload.get('base_instructions')
    provenance = instructions.get('provenance') if isinstance(instructions, dict) else None
    model = provenance.get('model') if isinstance(provenance, dict) else None
    return model if isinstance(model, str) and model else ''


def _tokens(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    count = value.get('total_tokens')
    return count if type(count) is int and count >= 0 else None
