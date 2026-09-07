"""Codex Usage Tests
=================

Exercise local rollout counters and incremental reads with synthetic records.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ai_agents_usage_monitor.codex_usage import CodexUsage


class TestCodexUsage(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'sessions' / 'test.jsonl'
        self.path.parent.mkdir()
        self.now = datetime.now(timezone.utc).timestamp()
        self.clock = patch('ai_agents_usage_monitor.codex_usage.time.time', return_value=self.now).start()
        self.monotonic = patch('ai_agents_usage_monitor.codex_usage.time.monotonic', return_value=100).start()
        self.addCleanup(patch.stopall)
        self.reader = CodexUsage(self.root)

    def write(self, records, mode='w'):
        with self.path.open(mode, encoding='utf-8') as stream:
            for record in records:
                stream.write(json.dumps(record) + '\n')

    def event(self, total, last, age=0):
        return {'type': 'event_msg', 'timestamp': datetime.fromtimestamp(self.now - age, timezone.utc).isoformat(),
                'payload': {'type': 'token_count', 'info': {'total_token_usage': {'total_tokens': total},
                            'last_token_usage': {'total_tokens': last}}}}

    def model(self, name):
        return {'type': 'turn_context', 'payload': {'model': name}}

    def meta(self, name):
        provenance = {'model': name} if name else {}
        return {'type': 'session_meta', 'payload': {'session_id': 'a-session', 'originator': 'Codex Desktop',
                'base_instructions': {'text': 'prompt text that must never be retained', 'provenance': provenance}}}

    def test_model_switch_duplicates_and_windows(self):
        self.write([self.model('model-a'), self.event(100, 100, 20000), self.event(100, 100),
                    self.model('model-b'), self.event(160, 60)])
        snap = self.reader.snapshot()
        self.assertEqual([w['tokens'] for w in snap['windows']], [60, 160])
        self.assertEqual(snap['windows'][0]['models'], [{'model': 'model-b', 'tokens': 60}])

    def test_first_inherited_counter_and_counter_reset(self):
        self.write([self.event(1000, 20), self.event(10, 10)])
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 30)

    def test_append_cache_and_incomplete_line(self):
        self.write([self.event(10, 10)])
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 10)
        with self.path.open('a') as stream:
            stream.write(json.dumps(self.event(30, 20)))
        self.monotonic.return_value = 161
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 10)
        with self.path.open('a') as stream:
            stream.write('\n')
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 10)
        self.monotonic.return_value = 222
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 30)

    def test_missing_and_malformed_are_unavailable(self):
        self.assertFalse(self.reader.snapshot()['available'])
        self.write([None, [], {'payload': None}, self.event(True, -1), {'type': 'event_msg', 'payload': {'type': 'token_count', 'info': None}}])
        self.monotonic.return_value = 161
        self.assertFalse(self.reader.snapshot()['available'])

    def test_next_minute_refreshes_even_when_previous_scan_took_time(self):
        self.write([self.event(10, 10)])
        self.reader.snapshot()
        self.write([self.event(20, 10)], mode='a')
        self.clock.return_value = self.now + 60
        self.monotonic.return_value = 159.8
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 20)

    def test_fork_duplicates_and_archived_sessions(self):
        self.write([self.model('model-a'), self.event(10, 10)])
        archive = self.root / 'archived_sessions'
        archive.mkdir()
        (archive / 'copy.jsonl').write_bytes(self.path.read_bytes())
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 10)

    def test_truncation_replaces_cached_entries(self):
        self.write([self.event(10, 10), self.event(20, 10)])
        self.reader.snapshot()
        self.write([self.event(5, 5)])
        self.monotonic.return_value = 161
        self.assertEqual(self.reader.snapshot()['windows'][0]['tokens'], 5)

    def test_boundaries_future_and_expired_records(self):
        self.write([self.event(1, 1, 604801), self.event(2, 1, 604800), self.event(3, 1, 18000), self.event(4, 1, -1)])
        self.assertEqual([w['tokens'] for w in self.reader.snapshot()['windows']], [1, 2])

    def test_imported_session_names_its_model_without_a_turn_context(self):
        """A session imported into the desktop history has no turn_context at all."""
        self.write([self.meta('gpt-6-astra'), self.event(500, 500)])
        self.assertEqual(self.reader.snapshot()['windows'][0]['models'], [{'model': 'gpt-6-astra', 'tokens': 500}])

    def test_turn_context_overrides_the_session_model_then_falls_back_to_it(self):
        """An unnamed turn keeps the session's own model rather than reporting Unknown."""
        self.write([self.meta('gpt-6-astra'), self.event(100, 100),
                    self.model('model-b'), self.event(160, 60),
                    {'type': 'turn_context', 'payload': {}}, self.event(200, 40)])
        self.assertEqual(self.reader.snapshot()['windows'][0]['models'],
                         [{'model': 'gpt-6-astra', 'tokens': 140}, {'model': 'model-b', 'tokens': 60}])

    def test_session_without_provenance_stays_unknown(self):
        self.write([self.meta(''), {'type': 'session_meta', 'payload': {'base_instructions': 'not a dict'}},
                    self.event(70, 70)])
        self.assertEqual(self.reader.snapshot()['windows'][0]['models'], [{'model': 'Unknown', 'tokens': 70}])

    def test_unreadable_file_is_partial(self):
        self.write([self.event(10, 10)])
        with patch.object(self.reader, '_read', side_effect=PermissionError):
            self.assertTrue(self.reader.snapshot()['partial'])
