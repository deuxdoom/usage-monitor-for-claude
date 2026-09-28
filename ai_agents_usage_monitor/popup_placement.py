"""
Popup Placement
================

Where the popup window sits on screen, worked out in Win32 physical pixels:
the DPI scale of the window's monitor, the spot beside the tray, and the
clamp that keeps a moved window on its monitor.  Resizing and moving the
window stay with the popup, which hands pywebview logical pixels.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes

__all__ = [
    'BASELINE_DPI', 'MONITORINFO', 'clamp_to_work_area', 'in_lower_half', 'tray_anchor', 'window_and_work_area',
    'window_dpi', 'window_scale',
]

# Windows' 100% scale: a window's DPI divided by this is its scale factor.
BASELINE_DPI = 96
_MONITOR_DEFAULTTONEAREST = 2


class MONITORINFO(ctypes.Structure):
    """Win32 ``MONITORINFO``: a monitor's bounds and its work area."""

    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('rcMonitor', ctypes.wintypes.RECT),
        ('rcWork', ctypes.wintypes.RECT),
        ('dwFlags', ctypes.wintypes.DWORD),
    ]


def window_dpi(hwnd: int) -> int:
    """Return the DPI of the window's monitor, or the system DPI when Windows reports none for it."""
    return ctypes.windll.user32.GetDpiForWindow(hwnd) or ctypes.windll.user32.GetDpiForSystem()


def window_scale(hwnd: int) -> float:
    """Return the window's DPI scale factor against the 96-DPI baseline."""
    return window_dpi(hwnd) / BASELINE_DPI


def tray_anchor(popup_hwnd: int, physical_width: int, physical_height: int, margin: int) -> tuple[int, int]:
    """Return the logical top-left that puts a window of this physical size beside the tray.

    The window is kept clear of the taskbar by two independent bounds: the
    monitor work area Windows reports, and the taskbar window's own
    rectangle.  The stricter of the two wins.  The second bound matters
    because an auto-hiding taskbar is not subtracted from the work area at
    all, so the work area alone would place the window underneath it.

    Parameters
    ----------
    popup_hwnd : int
        The popup's window handle, whose monitor DPI converts the result.
    physical_width, physical_height : int
        The window size in physical pixels.
    margin : int
        The gap left beyond that bound, in physical pixels.

    Returns
    -------
    tuple[int, int]
        Logical (x, y) coordinates.  Callers that need physical pixels
        must multiply by the DPI scale factor.
    """
    tray_hwnd = ctypes.windll.user32.FindWindowW('Shell_TrayWnd', None)
    hmon = ctypes.windll.user32.MonitorFromWindow(tray_hwnd, _MONITOR_DEFAULTTONEAREST)

    mon_info = MONITORINFO()
    mon_info.cbSize = ctypes.sizeof(MONITORINFO)
    ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mon_info))
    mon = mon_info.rcMonitor
    work = mon_info.rcWork

    scale = window_scale(popup_hwnd)
    left, top, right, bottom = _available_bounds(tray_hwnd, mon, work)

    if work.left > mon.left:    # left-side taskbar
        x = left + margin
    else:
        x = right - physical_width - margin

    if work.top > mon.top:      # top taskbar
        y = top + margin
    else:
        y = bottom - physical_height - margin

    return int(x / scale), int(y / scale)


def window_and_work_area(hwnd: int) -> tuple[ctypes.wintypes.RECT, ctypes.wintypes.RECT] | None:
    """Return the window's rectangle and its monitor's work area, or None when Windows cannot read either."""
    window = ctypes.wintypes.RECT()
    mon_info = MONITORINFO()
    mon_info.cbSize = ctypes.sizeof(MONITORINFO)
    hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(window)) \
            or not ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mon_info)):
        return None

    return window, mon_info.rcWork


def in_lower_half(window: ctypes.wintypes.RECT, work: ctypes.wintypes.RECT) -> bool:
    """Return True when the window's vertical center lies below the work area's."""
    return window.top + window.bottom > work.top + work.bottom


def clamp_to_work_area(left: int, top: int, width: int, height: int, work: ctypes.wintypes.RECT) -> tuple[int, int]:
    """Return the top-left that keeps a ``width`` x ``height`` window inside ``work``.

    All values are physical pixels.  A window taller or wider than the work
    area is aligned to its top or left edge, so the title row stays reachable.
    """
    left = max(work.left, min(left, work.right - width))
    top = max(work.top, min(top, work.bottom - height))
    return left, top


def _available_bounds(
    tray_hwnd: int, mon: ctypes.wintypes.RECT, work: ctypes.wintypes.RECT,
) -> tuple[int, int, int, int]:
    """Return the ``(left, top, right, bottom)`` the popup may occupy.

    Starts from the monitor work area and shrinks it by the taskbar
    window's own rectangle where the two disagree.  They disagree when the
    taskbar is set to auto-hide: Windows then reports the full monitor as
    work area, even though the bar reappears over that space on hover.

    Only the edge the taskbar actually sits on is trimmed, decided by
    comparing the bar's rectangle against the monitor: a bar wider than it
    is tall is horizontal, and its position within the monitor says whether
    it is at the top or the bottom.  A taskbar rectangle that covers the
    whole monitor, or that cannot be read, is ignored rather than trusted.

    Parameters
    ----------
    tray_hwnd : int
        Handle of the ``Shell_TrayWnd`` window, or 0 if not found.
    mon : RECT
        Monitor bounds in physical pixels.
    work : RECT
        Monitor work area in physical pixels.

    Returns
    -------
    tuple[int, int, int, int]
        Bounds in physical pixels.
    """
    left, top, right, bottom = work.left, work.top, work.right, work.bottom
    if not tray_hwnd:
        return left, top, right, bottom

    bar = ctypes.wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(tray_hwnd, ctypes.byref(bar)):
        return left, top, right, bottom

    bar_width = bar.right - bar.left
    bar_height = bar.bottom - bar.top
    if bar_width <= 0 or bar_height <= 0:
        return left, top, right, bottom

    # A bar spanning the entire monitor tells us nothing about which edge to
    # avoid; trimming by it would push the popup off-screen.
    if bar_width >= mon.right - mon.left and bar_height >= mon.bottom - mon.top:
        return left, top, right, bottom

    if bar_width >= bar_height:  # horizontal taskbar
        if bar.top - mon.top <= mon.bottom - bar.bottom:
            top = max(top, bar.bottom)
        else:
            bottom = min(bottom, bar.top)
    elif bar.left - mon.left <= mon.right - bar.right:
        left = max(left, bar.right)
    else:
        right = min(right, bar.left)

    return left, top, right, bottom
