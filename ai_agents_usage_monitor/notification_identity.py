"""
Notification Identity
=====================

Registers the fixed name and neutral logo used by Windows Runtime toasts.
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


def register_notification_identity() -> bool:
    """Adopt a fixed notification identity for this process.

    Writes ``DisplayName`` and ``IconUri`` to ``HKCU`` and adopts the process
    ``AppUserModelID``. The logo path changes with each private runtime, so
    registration runs on every startup before any window is created.

    The key left behind by the app's previous identity is removed first, so
    the cleanup still happens on a machine where the registration below
    cannot run.

    Returns
    -------
    bool
        True only after registration and adoption succeed. A failure lets
        notification delivery fall back to the tray balloon.
    """
    _remove_legacy_identity()

    if not _NOTIFICATION_LOGO.is_file():
        return False

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            winreg.SetValueEx(key, 'DisplayName', 0, winreg.REG_SZ, DISPLAY_NAME)
            winreg.SetValueEx(key, 'IconUri', 0, winreg.REG_EXPAND_SZ, str(_NOTIFICATION_LOGO))
        hresult = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(APP_USER_MODEL_ID))
    except OSError:
        return False

    return hresult == 0


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
