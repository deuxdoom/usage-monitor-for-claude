"""
Notification Identity
=====================

Registers a fixed toast-notification identity (name and logo) for the process.

Windows shows the process's app icon in the header of a tray notification.
Without an explicit identity that icon is the live tray icon, which reflects
the most-exhausted quota - so a "quota reset" or "50% used" toast would carry
the exhausted glyph and contradict its own text.  Registering an
``AppUserModelID`` with a neutral logo makes every toast show that logo
instead, independent of the tray icon.
"""
from __future__ import annotations

import ctypes
import winreg
from pathlib import Path

__all__ = ['register_notification_identity']

# Stable per-application identity.  Every instance (one per Claude account)
# shares it, so notifications group under one name and logo.
APP_USER_MODEL_ID = 'deuxdoom.UsageMonitorForClaude'
DISPLAY_NAME = 'AI Agents Usage Monitor'

# Neutral branded logo (empty usage bars) shown as the notification icon.
# A multi-size .ico (16-256 px) so Windows picks a crisp frame for the small
# toast header instead of downscaling a single large image.
_NOTIFICATION_LOGO = Path(__file__).resolve().parent / 'notification_logo.ico'

# HKCU key the shell reads to resolve the identity's display name and icon.
# A registry entry is enough - no Start Menu shortcut is required.
_REG_PATH = r'Software\Classes\AppUserModelId\{}'.format(APP_USER_MODEL_ID)

# Identity this app registered before it was renamed.  Its key is dead weight
# on every machine that ran an earlier version, so startup removes it once.
# Safe to drop from the code once no one is upgrading from before 1.80.0.
_LEGACY_REG_PATH = r'Software\Classes\AppUserModelId\JensDuttke.UsageMonitorForClaude'


def register_notification_identity() -> None:
    """Adopt a fixed notification identity for this process.

    Writes the ``DisplayName`` and ``IconUri`` registration to ``HKCU`` and,
    only if that succeeds, sets the process ``AppUserModelID`` so toasts use
    the registered name and logo.  Re-run on every startup because a frozen
    build extracts the logo to a fresh temporary directory each run, changing
    its path.

    The key left behind by the app's previous identity is removed first, so
    the cleanup still happens on a machine where the registration below
    cannot run.

    On any failure - a missing logo file or a registry write error - the
    process keeps its default identity (the live tray icon).  This is never
    fatal: a notification icon must not stop the app from starting, and
    falling back to the tray icon is better than an empty one.
    """
    _remove_legacy_identity()

    if not _NOTIFICATION_LOGO.is_file():
        return

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            winreg.SetValueEx(key, 'DisplayName', 0, winreg.REG_SZ, DISPLAY_NAME)
            winreg.SetValueEx(key, 'IconUri', 0, winreg.REG_EXPAND_SZ, str(_NOTIFICATION_LOGO))
    except OSError:
        return

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(APP_USER_MODEL_ID))


def _remove_legacy_identity() -> None:
    """Delete the registry key of the identity this app used to register.

    Best-effort and silent: the key is already gone on a first-time install
    and on every start after the first, and a machine that will not let it be
    deleted is no reason to fail a startup.  ``DeleteKey`` also refuses a key
    that has subkeys, so nothing that grew under it is removed blindly.
    """
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _LEGACY_REG_PATH)
    except OSError:
        pass
