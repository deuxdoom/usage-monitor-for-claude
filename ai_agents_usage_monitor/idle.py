"""
Idle Detection
===============

Detects user inactivity and workstation lock state on Windows.

Uses ``GetLastInputInfo`` (keyboard/mouse idle time) and
``OpenInputDesktop`` (lock detection) via ctypes - no extra
dependencies required.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes

__all__ = ['get_idle_seconds', 'is_workstation_locked']

# Ensure GetTickCount returns unsigned DWORD (default c_int overflows after ~24.8 days of uptime)
ctypes.windll.kernel32.GetTickCount.restype = ctypes.wintypes.DWORD


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.UINT),
        ('dwTime', ctypes.wintypes.DWORD),
    ]


def get_idle_seconds() -> float:
    """Return seconds since the last keyboard or mouse input.

    Returns
    -------
    float
        Idle duration in seconds.  Returns 0.0 on failure.
    """
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    # Simulate unsigned 32-bit subtraction so the result stays correct
    # when GetTickCount wraps after ~49 days of uptime.
    millis = (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF
    return millis / 1000.0


def is_workstation_locked() -> bool:
    """Return True if the Windows workstation is locked.

    Uses ``OpenInputDesktop`` which returns NULL when the secure
    desktop (lock screen) is active.

    Returns
    -------
    bool
        True if the workstation appears to be locked.
    """
    hdesk = ctypes.windll.user32.OpenInputDesktop(0, False, 0)
    if hdesk:
        ctypes.windll.user32.CloseDesktop(hdesk)
        return False
    return True
