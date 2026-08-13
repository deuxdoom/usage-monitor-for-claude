"""Unit tests for usage_monitor_for_claude.session_logs.

Covers: token/message extraction from transcript lines, dedupe of retried
turns, window filtering, the mtime-based file skip, and per-file caching.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from usage_monitor_for_claude.session_logs import (
    ModelUsage, WindowStats, _extract_entry, _parse_timestamp, clear_cache, usage_in_window,
)


def _iso(*args, **kwargs) -> str:
    return datetime(*args, tzinfo=timezone.utc, **kwargs).isoformat().replace('+00:00', 'Z')


def _epoch(*args, **kwargs) -> float:
    return datetime(*args, tzinfo=timezone.utc, **kwargs).timestamp()


def _assistant_line(
    message_id: str, model: str, input_tokens: int = 0, output_tokens: int = 0,
    cache_creation: int = 0, cache_read: int = 0, timestamp: str = '2026-08-13T10:00:00Z',
    request_id: str | None = None,
) -> dict:
    return {
        'type': 'assistant',
        'timestamp': timestamp,
        'message': {
            'id': message_id,
            'model': model,
            'usage': {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cache_creation_input_tokens': cache_creation,
                'cache_read_input_tokens': cache_read,
            },
        },
        'requestId': request_id or f'{message_id}-req',
    }


def _write_jsonl(path: Path, lines: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for line in lines:
            handle.write((json.dumps(line) if not isinstance(line, str) else line) + '\n')


# ---------------------------------------------------------------------------
# _parse_timestamp
# ---------------------------------------------------------------------------

class TestParseTimestamp(unittest.TestCase):
    def test_z_suffix(self):
        self.assertEqual(_parse_timestamp('2026-08-13T10:00:00Z'), _epoch(2026, 8, 13, 10, 0, 0))

    def test_explicit_offset(self):
        self.assertEqual(_parse_timestamp('2026-08-13T10:00:00+00:00'), _epoch(2026, 8, 13, 10, 0, 0))

    def test_naive_treated_as_utc(self):
        self.assertEqual(_parse_timestamp('2026-08-13T10:00:00'), _epoch(2026, 8, 13, 10, 0, 0))

    def test_non_string_returns_none(self):
        self.assertIsNone(_parse_timestamp(1755075600))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_timestamp(''))

    def test_malformed_returns_none(self):
        self.assertIsNone(_parse_timestamp('not-a-date'))


# ---------------------------------------------------------------------------
# _extract_entry
# ---------------------------------------------------------------------------

class TestExtractEntry(unittest.TestCase):
    def test_extracts_assistant_turn(self):
        entry = _extract_entry(_assistant_line('m1', 'claude-sonnet-4-6', input_tokens=100, output_tokens=50))
        self.assertIsNotNone(entry)
        self.assertEqual(entry.total_tokens, 150)
        self.assertEqual(entry.model, 'claude-sonnet-4-6')

    def test_sums_all_four_token_kinds(self):
        entry = _extract_entry(_assistant_line(
            'm1', 'claude-opus-4-8', input_tokens=10, output_tokens=20, cache_creation=5, cache_read=3,
        ))
        self.assertEqual(entry.total_tokens, 38)

    def test_user_turn_ignored(self):
        self.assertIsNone(_extract_entry({'type': 'user', 'timestamp': '2026-08-13T10:00:00Z'}))

    def test_missing_usage_ignored(self):
        data = {'type': 'assistant', 'timestamp': '2026-08-13T10:00:00Z', 'message': {'id': 'm1', 'model': 'x'}}
        self.assertIsNone(_extract_entry(data))

    def test_zero_tokens_ignored(self):
        self.assertIsNone(_extract_entry(_assistant_line('m1', 'x', input_tokens=0, output_tokens=0)))

    def test_missing_timestamp_ignored(self):
        line = _assistant_line('m1', 'x', input_tokens=10)
        del line['timestamp']
        self.assertIsNone(_extract_entry(line))

    def test_missing_model_falls_back_to_unknown(self):
        line = _assistant_line('m1', 'x', input_tokens=10)
        del line['message']['model']
        entry = _extract_entry(line)
        self.assertEqual(entry.model, 'unknown')

    def test_dedupe_key_from_message_and_request_id(self):
        entry = _extract_entry(_assistant_line('m1', 'x', input_tokens=10, request_id='r1'))
        self.assertEqual(entry.dedupe_key, 'm1:r1')

    def test_dedupe_key_none_without_request_id(self):
        line = _assistant_line('m1', 'x', input_tokens=10)
        del line['requestId']
        entry = _extract_entry(line)
        self.assertIsNone(entry.dedupe_key)


# ---------------------------------------------------------------------------
# usage_in_window
# ---------------------------------------------------------------------------

class TestUsageInWindow(unittest.TestCase):
    def setUp(self):
        clear_cache()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(clear_cache)

    def test_missing_directory_returns_empty(self):
        stats = usage_in_window(self.root / 'does-not-exist', 0, 1e12)
        self.assertEqual(stats, WindowStats(total_tokens=0, message_count=0, models=[]))

    def test_sums_tokens_within_window(self):
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [
            _assistant_line('m1', 'claude-sonnet-4-6', input_tokens=100, output_tokens=50,
                             timestamp=_iso(2026, 8, 13, 10, 0, 0)),
            _assistant_line('m2', 'claude-sonnet-4-6', input_tokens=200, output_tokens=0,
                             timestamp=_iso(2026, 8, 13, 10, 30, 0)),
        ])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 350)
        self.assertEqual(stats.message_count, 2)

    def test_entries_outside_window_excluded(self):
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [
            _assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 1, 0, 0, 0)),
            _assistant_line('m2', 'x', input_tokens=200, timestamp=_iso(2026, 8, 13, 10, 0, 0)),
        ])
        os.utime(self.root / 'p1' / 'a.jsonl', (_epoch(2026, 8, 13, 10, 0, 0),) * 2)
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 200)

    def test_window_end_is_exclusive(self):
        ts = _iso(2026, 8, 13, 11, 0, 0)
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [_assistant_line('m1', 'x', input_tokens=100, timestamp=ts)])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 0)

    def test_window_start_is_inclusive(self):
        ts = _iso(2026, 8, 13, 9, 0, 0)
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [_assistant_line('m1', 'x', input_tokens=100, timestamp=ts)])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 100)

    def test_duplicate_message_request_pair_counted_once(self):
        """A retried turn logged twice must not double-count the same tokens."""
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [
            _assistant_line('m1', 'x', input_tokens=100, request_id='r1', timestamp=_iso(2026, 8, 13, 10, 0, 0)),
            _assistant_line('m1', 'x', input_tokens=100, request_id='r1', timestamp=_iso(2026, 8, 13, 10, 0, 1)),
        ])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 100)
        self.assertEqual(stats.message_count, 1)

    def test_entries_without_dedupe_key_never_collapsed(self):
        line1 = _assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0))
        del line1['requestId']
        line2 = _assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 1))
        del line2['requestId']
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [line1, line2])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 200)

    def test_malformed_line_skipped_others_kept(self):
        good = _assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0))
        _write_jsonl(self.root / 'p1' / 'a.jsonl', ['not json{{{', good])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 100)

    def test_multiple_files_aggregated(self):
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [
            _assistant_line('m1', 'claude-sonnet-4-6', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0)),
        ])
        _write_jsonl(self.root / 'p2' / 'b.jsonl', [
            _assistant_line('m2', 'claude-opus-4-8', input_tokens=200, timestamp=_iso(2026, 8, 13, 10, 0, 0)),
        ])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 300)
        self.assertEqual(stats.message_count, 2)

    def test_old_file_skipped_by_mtime_without_parsing(self):
        """A file whose mtime predates the window is never opened."""
        path = self.root / 'p1' / 'a.jsonl'
        _write_jsonl(path, [_assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0))])
        old_time = _epoch(2026, 1, 1, 0, 0, 0)
        os.utime(path, (old_time, old_time))

        with patch('usage_monitor_for_claude.session_logs._parse_file') as mock_parse:
            stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        mock_parse.assert_not_called()
        self.assertEqual(stats.total_tokens, 0)

    def test_unchanged_file_not_reparsed_on_second_call(self):
        path = self.root / 'p1' / 'a.jsonl'
        _write_jsonl(path, [_assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0))])

        stats1 = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        with patch('usage_monitor_for_claude.session_logs._parse_file') as mock_parse:
            stats2 = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        mock_parse.assert_not_called()
        self.assertEqual(stats1.total_tokens, stats2.total_tokens)

    def test_modified_file_is_reparsed(self):
        path = self.root / 'p1' / 'a.jsonl'
        _write_jsonl(path, [_assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0))])
        usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))

        time.sleep(0.01)
        _write_jsonl(path, [
            _assistant_line('m1', 'x', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0)),
            _assistant_line('m2', 'x', input_tokens=50, timestamp=_iso(2026, 8, 13, 10, 5, 0)),
        ])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.total_tokens, 150)

    def test_model_breakdown_sorted_by_tokens_descending(self):
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [
            _assistant_line('m1', 'claude-sonnet-4-6', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0)),
            _assistant_line('m2', 'claude-opus-4-8', input_tokens=300, timestamp=_iso(2026, 8, 13, 10, 5, 0)),
        ])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual([m.model for m in stats.models], ['claude-opus-4-8', 'claude-sonnet-4-6'])
        self.assertAlmostEqual(stats.models[0].fraction, 0.75)
        self.assertAlmostEqual(stats.models[1].fraction, 0.25)

    def test_same_model_aggregated_across_files(self):
        _write_jsonl(self.root / 'p1' / 'a.jsonl', [
            _assistant_line('m1', 'claude-sonnet-4-6', input_tokens=100, timestamp=_iso(2026, 8, 13, 10, 0, 0)),
        ])
        _write_jsonl(self.root / 'p2' / 'b.jsonl', [
            _assistant_line('m2', 'claude-sonnet-4-6', input_tokens=50, timestamp=_iso(2026, 8, 13, 10, 5, 0)),
        ])
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(len(stats.models), 1)
        self.assertEqual(stats.models[0].tokens, 150)

    def test_empty_window_has_no_models(self):
        stats = usage_in_window(self.root, _epoch(2026, 8, 13, 9, 0, 0), _epoch(2026, 8, 13, 11, 0, 0))
        self.assertEqual(stats.models, [])


if __name__ == '__main__':
    unittest.main()
