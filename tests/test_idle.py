"""
Idle Detection Tests
======================

Unit tests for idle time and workstation lock detection.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_agents_usage_monitor import idle as idle_mod


class TestGetIdleSeconds(unittest.TestCase):
    """Tests for get_idle_seconds() via GetLastInputInfo."""

    @patch.object(idle_mod.ctypes, 'windll', create=True)
    def test_returns_idle_duration(self, mock_windll):
        """Returns seconds since last input based on tick counts."""
        mock_windll.kernel32.GetTickCount.return_value = 310_000

        def fake_get_last_input(byref_arg):
            # The ctypes.byref() wrapper is opaque, so reach into the
            # _LASTINPUTINFO via the underlying _obj attribute.
            obj = byref_arg._obj
            obj.dwTime = 300_000
            return True

        mock_windll.user32.GetLastInputInfo.side_effect = fake_get_last_input

        result = idle_mod.get_idle_seconds()
        self.assertAlmostEqual(result, 10.0, places=1)

    @patch.object(idle_mod.ctypes, 'windll', create=True)
    def test_returns_zero_on_failure(self, mock_windll):
        """Returns 0.0 when GetLastInputInfo fails."""
        mock_windll.user32.GetLastInputInfo.return_value = False

        result = idle_mod.get_idle_seconds()
        self.assertEqual(result, 0.0)

    @patch.object(idle_mod.ctypes, 'windll', create=True)
    def test_zero_idle_when_just_active(self, mock_windll):
        """Returns 0.0 when last input tick equals current tick."""
        mock_windll.kernel32.GetTickCount.return_value = 500_000

        def fake_get_last_input(byref_arg):
            byref_arg._obj.dwTime = 500_000
            return True

        mock_windll.user32.GetLastInputInfo.side_effect = fake_get_last_input

        result = idle_mod.get_idle_seconds()
        self.assertEqual(result, 0.0)

    @patch.object(idle_mod.ctypes, 'windll', create=True)
    def test_tick_count_wraparound_computes_correct_idle(self, mock_windll):
        """Computes correct idle time when GetTickCount wraps around (~49 days)."""
        mock_windll.kernel32.GetTickCount.return_value = 100

        def fake_get_last_input(byref_arg):
            # dwTime is near max DWORD, GetTickCount wrapped to low value
            byref_arg._obj.dwTime = 4_294_967_000
            return True

        mock_windll.user32.GetLastInputInfo.side_effect = fake_get_last_input

        result = idle_mod.get_idle_seconds()
        # Unsigned 32-bit: (100 - 4294967000) & 0xFFFFFFFF = 396 ms
        self.assertAlmostEqual(result, 0.396)


class TestIsWorkstationLocked(unittest.TestCase):
    """Tests for is_workstation_locked() via OpenInputDesktop."""

    @patch.object(idle_mod.ctypes, 'windll', create=True)
    def test_locked_when_null_handle(self, mock_windll):
        """Returns True when OpenInputDesktop returns NULL (0)."""
        mock_windll.user32.OpenInputDesktop.return_value = 0

        self.assertTrue(idle_mod.is_workstation_locked())
        mock_windll.user32.CloseDesktop.assert_not_called()

    @patch.object(idle_mod.ctypes, 'windll', create=True)
    def test_unlocked_when_valid_handle(self, mock_windll):
        """Returns False when OpenInputDesktop returns a valid handle."""
        mock_windll.user32.OpenInputDesktop.return_value = 42

        self.assertFalse(idle_mod.is_workstation_locked())
        mock_windll.user32.CloseDesktop.assert_called_once_with(42)


if __name__ == '__main__':
    unittest.main()
