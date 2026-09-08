"""Codex Account Tests
===================

Verify protocol requests, quota validation and independent retry scheduling.
"""
from __future__ import annotations

import io
import queue
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_agents_usage_monitor.codex_api import (
    CodexAccount, _fetch, _plan_label, _ReadError, _read_responses, _request, _windows,
)


def _limit(minutes=300, used=35, reset=1800000000):
    return {'usedPercent': used, 'windowDurationMins': minutes, 'resetsAt': reset}


class TestWindows(unittest.TestCase):
    def test_uses_codex_bucket_and_server_periods(self):
        windows = _windows({'rateLimitsByLimitId': {'codex': {'primary': _limit(10080), 'secondary': _limit(300)},
                                                  'unrelated': {'primary': _limit(1)}},
                            'rateLimits': {'primary': _limit(15)}})
        self.assertEqual([window['seconds'] for window in windows], [18000, 604800])
        self.assertEqual(windows[0]['key'], 'codex_secondary')

    def test_legacy_null_and_invalid_fields(self):
        for value in (None, [], {}, _limit(0), _limit(300, True), _limit(300, float('nan')), _limit(300, -1), _limit(reset='tomorrow')):
            with self.subTest(value=value):
                self.assertEqual(_windows({'rateLimits': {'primary': value}}), [])
        self.assertEqual(len(_windows({'rateLimits': {'primary': _limit(300, 0, None), 'secondary': None}})), 1)
        self.assertEqual(_windows({'rateLimits': {'primary': _limit(300, 110)}})[0]['used'], 110)


class TestAccountCache(unittest.TestCase):
    def setUp(self):
        self.client = CodexAccount()
        self.clock = patch('ai_agents_usage_monitor.codex_api.time.monotonic', return_value=100).start()
        patch('ai_agents_usage_monitor.codex_api._find_binary', return_value=Path('codex.exe')).start()
        self.fetch = patch('ai_agents_usage_monitor.codex_api._fetch', return_value=({'plan': 'Plus'}, [_limit()])).start()
        self.addCleanup(patch.stopall)

    def test_one_minute_cache_and_account_switch(self):
        self.client.snapshot(60)
        self.clock.return_value = 159
        self.client.snapshot(60)
        self.assertEqual(self.fetch.call_count, 1)
        self.fetch.return_value = ({'plan': 'Pro'}, [_limit()])
        self.clock.return_value = 160
        self.assertEqual(self.client.snapshot(60)['profile']['plan'], 'Pro')

    def test_errors_clear_previous_account_and_back_off(self):
        self.client.snapshot(60)
        self.fetch.side_effect = _ReadError('codex_account_error')
        self.clock.return_value = 160
        failed = self.client.snapshot(60)
        self.assertIsNone(failed['profile'])
        self.assertEqual(failed['windows'], [])
        self.assertEqual(failed['next_read'] - failed['updated_at'], 120)
        self.clock.return_value = 279
        self.client.snapshot(60)
        self.assertEqual(self.fetch.call_count, 2)
        self.clock.return_value = 280
        failed = self.client.snapshot(60)
        self.assertEqual(failed['next_read'] - failed['updated_at'], 240)
        self.fetch.side_effect = None
        self.clock.return_value = 520
        recovered = self.client.snapshot(60)
        self.assertIsNone(recovered['error'])
        self.assertEqual(recovered['next_read'] - recovered['updated_at'], 60)

    def test_missing_cli_does_not_start_process(self):
        with patch('ai_agents_usage_monitor.codex_api._find_binary', return_value=None):
            self.assertEqual(self.client.snapshot(60)['error'], 'codex_cli_missing')
        self.fetch.assert_not_called()

    def test_read_follows_the_interval_it_is_given(self):
        """A three-minute cadence reads every three minutes, not every minute."""
        self.client.snapshot(180)
        self.clock.return_value = 279
        self.client.snapshot(180)
        self.assertEqual(self.fetch.call_count, 1)

        self.clock.return_value = 280
        self.client.snapshot(180)
        self.assertEqual(self.fetch.call_count, 2)

    def test_reported_next_read_follows_the_interval(self):
        """The popup countdown reflects the chosen cadence, not a fixed minute."""
        snapshot = self.client.snapshot(300)

        self.assertEqual(snapshot['next_read'] - snapshot['updated_at'], 300)

    def test_a_shortened_interval_applies_without_waiting_out_the_old_one(self):
        """Switching from five minutes to one must not hold the old wait.

        The gate measures from the last read, so the pending five-minute wait
        is not a deadline that outlives the choice that created it.
        """
        self.client.snapshot(300)
        self.clock.return_value = 160

        self.client.snapshot(60)

        self.assertEqual(self.fetch.call_count, 2)

    def test_backoff_doubles_from_the_chosen_interval(self):
        """A failure under a slow cadence backs off from that cadence."""
        self.client.snapshot(180)
        self.fetch.side_effect = _ReadError('codex_account_error')
        self.clock.return_value = 280

        failed = self.client.snapshot(180)

        self.assertEqual(failed['next_read'] - failed['updated_at'], 360)

    def test_backoff_ceiling_is_the_shared_setting(self):
        """Codex caps its backoff with the same max_backoff the Claude path uses.

        A private ceiling here would quietly apply the user's setting to one
        provider only - the class of bug this argument exists to prevent.
        """
        from ai_agents_usage_monitor.settings import MAX_BACKOFF

        self.fetch.side_effect = _ReadError('codex_account_error')
        clock = 100
        for _ in range(6):
            clock += MAX_BACKOFF
            self.clock.return_value = clock
            failed = self.client.snapshot(300)

        self.assertEqual(failed['next_read'] - failed['updated_at'], MAX_BACKOFF)

    def test_a_cached_read_never_reports_a_deadline_already_past(self):
        """The popup counts down to next_read, so a stale one freezes the view.

        Handing back the deadline the previous, shorter interval implied leaves
        the popup with nothing to count down to: it drops the countdown and
        sits on "updated N minutes ago" until the next read lands.
        """
        import time as real_time

        self.client.snapshot(60)
        self.clock.return_value = 250          # past the 60s deadline, inside the 300s one

        snapshot = self.client.snapshot(300)

        self.assertEqual(self.fetch.call_count, 1)
        self.assertGreater(snapshot['next_read'], real_time.time())

    def test_a_cached_deadline_is_measured_from_the_last_read(self):
        """The reported wait is what actually remains under the current interval."""
        import time as real_time

        self.client.snapshot(60)
        self.clock.return_value = 130          # 30 seconds after the read

        before = real_time.time()
        snapshot = self.client.snapshot(300)

        self.assertAlmostEqual(snapshot['next_read'] - before, 270, delta=2)

    def test_concurrent_reads_share_one_fetch(self):
        threads = [threading.Thread(target=self.client.snapshot, args=(60,)) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
        self.fetch.assert_called_once()


class TestProtocol(unittest.TestCase):
    def test_response_ids_errors_eof_and_timeout(self):
        process = MagicMock(stdin=io.BytesIO())
        responses = queue.Queue()
        responses.put({'id': 99, 'result': {}})
        responses.put({'id': 1, 'result': {'ok': True}})
        self.assertEqual(_request(process, responses, float('inf'), 1, 'account/read', {}), {'ok': True})
        for record in ({'id': 2, 'error': {'message': 'private data'}}, None):
            responses.put(record)
            with self.assertRaisesRegex(_ReadError, '^codex_account_error$'):
                _request(process, responses, 0, 2, 'account/read', {})
        with self.assertRaises(_ReadError):
            _request(process, responses, 0, 3, 'account/read', {})

    def test_reader_discards_notifications_and_malformed_lines(self):
        responses = queue.Queue()
        _read_responses(io.BytesIO(b'bad\nnull\n{"method":"notice"}\n{"id":1,"result":{}}\n'), responses)
        self.assertEqual(responses.get_nowait(), {'id': 1, 'result': {}})
        self.assertIsNone(responses.get_nowait())
        self.assertTrue(responses.empty())

    def test_fetch_handshake_and_cleanup(self):
        process = MagicMock(stdout=io.BytesIO(), stdin=io.BytesIO())
        process.poll.return_value = None
        account = {'type': 'chatgpt', 'email': 'test@example.test', 'planType': 'plus'}
        results = [{}, {'account': account}, {'rateLimits': {'primary': _limit()}}, {'account': account}]
        with patch('ai_agents_usage_monitor.codex_api.subprocess.Popen', return_value=process) as popen:
            with patch('ai_agents_usage_monitor.codex_api._request', side_effect=results) as request:
                profile, windows = _fetch(Path('codex.exe'))
        self.assertEqual(profile['plan'], 'ChatGPT Plus')
        self.assertEqual(windows[0]['seconds'], 18000)
        self.assertEqual([call.args[4] for call in request.call_args_list], ['initialize', 'account/read', 'account/rateLimits/read', 'account/read'])
        self.assertIn('analytics.enabled=false', popen.call_args.args[0])
        process.terminate.assert_called_once()
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)

    def test_every_plan_tier_is_named_with_the_product(self):
        """The tier alone reads as a fragment, so the product name goes in front."""
        tiers = {'free': 'ChatGPT Free', 'go': 'ChatGPT Go', 'plus': 'ChatGPT Plus', 'pro': 'ChatGPT Pro',
                 'business': 'ChatGPT Business', 'enterprise': 'ChatGPT Enterprise'}
        self.assertEqual({tier: _plan_label(tier) for tier in tiers}, tiers)

    def test_plan_label_does_not_repeat_the_product_name(self):
        self.assertEqual(_plan_label('chatgpt_plus'), 'ChatGPT Plus')

    def test_missing_plan_is_empty_so_the_row_stays_hidden(self):
        for value in ('', '   ', 'chatgpt', None, 42):
            self.assertEqual(_plan_label(value), '')

    def test_login_modes_and_changed_identity(self):
        for account, error in ((None, 'codex_login_required'), ({'type': 'apiKey'}, 'codex_chatgpt_required')):
            process = MagicMock(stdout=io.BytesIO(), stdin=io.BytesIO())
            with patch('ai_agents_usage_monitor.codex_api.subprocess.Popen', return_value=process):
                with patch('ai_agents_usage_monitor.codex_api._request', side_effect=[{}, {'account': account}]):
                    with self.assertRaisesRegex(_ReadError, error):
                        _fetch(Path('codex.exe'))
            self.assertTrue(process.stdout.closed)
        process = MagicMock(stdout=io.BytesIO(), stdin=io.BytesIO())
        with patch('ai_agents_usage_monitor.codex_api.subprocess.Popen', return_value=process):
            results = [{}, {'account': {'type': 'chatgpt', 'email': 'first@example.test'}},
                       {'rateLimits': {'primary': _limit()}}, {'account': {'type': 'chatgpt', 'email': 'second@example.test'}}]
            with patch('ai_agents_usage_monitor.codex_api._request', side_effect=results):
                with self.assertRaisesRegex(_ReadError, 'codex_account_error'):
                    _fetch(Path('codex.exe'))
