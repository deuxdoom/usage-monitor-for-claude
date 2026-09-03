"""
Notification Identity Tests
===========================

Unit tests for the toast-notification identity registration.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import usage_monitor_for_claude.notification_identity as ni


class TestRegisterNotificationIdentity(unittest.TestCase):
    """Tests for register_notification_identity()."""

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_registers_name_icon_and_sets_aumid(self, mock_winreg, mock_ctypes):
        """A present logo writes DisplayName + IconUri (the logo path) and then adopts the AUMID."""
        logo = MagicMock()
        logo.is_file.return_value = True
        logo.__str__.return_value = r'C:\fake\notification_logo.ico'

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        mock_winreg.CreateKey.assert_called_once_with(mock_winreg.HKEY_CURRENT_USER, ni._REG_PATH)
        writes = {c.args[1]: c.args[4] for c in mock_winreg.SetValueEx.call_args_list}
        self.assertEqual(list(writes), ['DisplayName', 'IconUri'])
        self.assertEqual(writes['IconUri'], r'C:\fake\notification_logo.ico')
        mock_ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once()

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_writes_configured_display_name(self, mock_winreg, mock_ctypes):
        """DisplayName is written with the module's brand name."""
        logo = MagicMock()
        logo.is_file.return_value = True

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        display_call = next(c for c in mock_winreg.SetValueEx.call_args_list if c.args[1] == 'DisplayName')
        self.assertEqual(display_call.args[4], ni.DISPLAY_NAME)

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_skips_everything_when_logo_missing(self, mock_winreg, mock_ctypes):
        """A missing logo leaves the default identity (tray icon) untouched."""
        logo = MagicMock()
        logo.is_file.return_value = False

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        mock_winreg.CreateKey.assert_not_called()
        mock_ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_not_called()

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_does_not_adopt_aumid_when_registry_fails(self, mock_winreg, mock_ctypes):
        """A registry write failure keeps the tray icon rather than an empty one."""
        mock_winreg.CreateKey.side_effect = OSError('access denied')
        logo = MagicMock()
        logo.is_file.return_value = True

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        mock_ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_not_called()

    def test_registry_path_matches_aumid(self):
        """The registry path targets the same AUMID the process adopts."""
        self.assertTrue(ni._REG_PATH.endswith(ni.APP_USER_MODEL_ID))
        self.assertIn(r'Software\Classes\AppUserModelId', ni._REG_PATH)


class TestRemoveLegacyIdentity(unittest.TestCase):
    """Tests that startup clears the registry key of the app's former identity.

    The app was renamed, so every machine that ran an earlier version carries a
    key nothing reads any more.  Removing it must never be able to cost a
    startup, and must never reach past the one key it is meant to clear.
    """

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_legacy_key_is_deleted_on_startup(self, mock_winreg, _mock_ctypes):
        logo = MagicMock()
        logo.is_file.return_value = True

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        mock_winreg.DeleteKey.assert_called_once_with(mock_winreg.HKEY_CURRENT_USER, ni._LEGACY_REG_PATH)

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_legacy_key_is_deleted_even_without_a_logo(self, mock_winreg, _mock_ctypes):
        """The cleanup runs before the early return a missing logo takes."""
        logo = MagicMock()
        logo.is_file.return_value = False

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        mock_winreg.DeleteKey.assert_called_once_with(mock_winreg.HKEY_CURRENT_USER, ni._LEGACY_REG_PATH)
        mock_winreg.CreateKey.assert_not_called()

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_missing_legacy_key_still_registers_the_identity(self, mock_winreg, mock_ctypes):
        """Already deleted (or never present) is the normal case, not a failure."""
        mock_winreg.DeleteKey.side_effect = FileNotFoundError('key not found')
        logo = MagicMock()
        logo.is_file.return_value = True

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        mock_ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once()

    @patch.object(ni, 'ctypes')
    @patch.object(ni, 'winreg')
    def test_undeletable_legacy_key_still_registers_the_identity(self, mock_winreg, mock_ctypes):
        """A refused delete - no permission, or subkeys present - is not fatal."""
        mock_winreg.DeleteKey.side_effect = PermissionError('access denied')
        logo = MagicMock()
        logo.is_file.return_value = True

        with patch.object(ni, '_NOTIFICATION_LOGO', logo):
            ni.register_notification_identity()

        mock_ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once()

    def test_legacy_path_is_a_different_key_under_the_same_parent(self):
        """The cleanup targets the former AUMID only - never the current one."""
        self.assertNotEqual(ni._LEGACY_REG_PATH, ni._REG_PATH)
        self.assertTrue(ni._LEGACY_REG_PATH.startswith(r'Software\Classes\AppUserModelId'))
        self.assertNotIn(ni.APP_USER_MODEL_ID, ni._LEGACY_REG_PATH)


if __name__ == '__main__':
    unittest.main()
