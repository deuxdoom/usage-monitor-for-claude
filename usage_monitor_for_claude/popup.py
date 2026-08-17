"""
Popup Window
=============

Dark-themed HTML popup window showing account info and usage bars.
Uses pywebview with Edge WebView2 for smooth CSS transitions and
flexible layout.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import logging
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import webview  # type: ignore[import-untyped]  # no type stubs available

from . import __version__
from . import session_logs
from .api import CLAUDE_CONFIG_DIR
from .claude_cli import CHANGELOG_URL, find_installations
from .formatting import (
    divider_positions, elapsed_pct, expand_popup_fields, field_countdown_only, field_period,
    format_count, format_credits, popup_label, time_until,
)
from .i18n import T
from .settings import BAR_BG, BAR_DIVIDER, BAR_FG, BAR_FG_WARN, BAR_MARKER, BG, COMPACT_HIDE, FG, FG_DIM, FG_HEADING, FG_LINK, POPUP_FIELDS, POPUP_MARGIN

logger = logging.getLogger(__name__)

# A field's estimated total (tokens_used / utilization) is only shown once
# the percentage is high enough that dividing by it is not just amplifying
# noise - at 0.3%, for instance, a handful of tokens either way swings the
# estimate by tens of thousands.
_MIN_UTILIZATION_FOR_ESTIMATE = 1.0

_POPUP_DIR = Path(__file__).parent / 'popup'
_BASELINE_DPI = 96
_GWL_EXSTYLE = -20
_WS_EX_APPWINDOW = 0x00040000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_LAYERED = 0x00080000
_LWA_ALPHA = 0x00000002
_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_WM_QUIT = 0x0012


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('rcMonitor', ctypes.wintypes.RECT),
        ('rcWork', ctypes.wintypes.RECT),
        ('dwFlags', ctypes.wintypes.DWORD),
    ]


__all__ = ['UsagePopup']

if TYPE_CHECKING:
    from .app import UsageMonitorForClaude
    from .cache import CacheSnapshot


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _usage_entries(usage: dict[str, Any]) -> list[tuple[str, dict[str, Any] | None, int | None, str]]:
    """Return ``(label, data, period, field)`` tuples from the given usage data.

    The raw *field* name is included so the popup can hide individual bars
    by field name when the pinned compact view is configured.
    """
    fields = expand_popup_fields(POPUP_FIELDS, usage)
    return [(popup_label(key), usage.get(key), field_period(key), key) for key in fields]


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


def _snapshot_to_dict(
    snap: CacheSnapshot, installations: list[dict[str, str]] | None = None, next_poll_time: float | None = None,
) -> dict[str, Any]:
    """Convert a CacheSnapshot to a JSON-serializable dict for the popup JS.

    Parameters
    ----------
    snap : CacheSnapshot
        Immutable snapshot of the cache state.
    installations : list or None
        Pre-computed installation list, or None to detect now.
    next_poll_time : float or None
        Unix timestamp of the next scheduled API poll.
    """
    # Profile - truthiness check (not `is not None`): hides the account section when the API
    # returns an empty or incomplete response, instead of rendering empty Email/Plan fields.
    profile = None
    if snap.profile:
        account = snap.profile.get('account') or {}
        org = snap.profile.get('organization') or {}
        # The account row shows the name by default and only reveals the email
        # when clicked; the email is the piece worth not leaving on screen
        # during a screen share.  Accounts without a name fall back to a
        # blurred email, handled in the popup JS.
        profile = {
            'email': account.get('email', ''),
            'name': account.get('full_name') or account.get('display_name') or '',
            'plan': org.get('organization_type', '').replace('_', ' ').title(),
        }

    # Usage bars
    usage = []
    if snap.usage:
        for label, entry, period, field in _usage_entries(snap.usage):
            if not entry or entry.get('utilization') is None:
                continue
            pct = entry.get('utilization', 0) or 0
            resets_at = entry.get('resets_at', '')
            time_pct = elapsed_pct(resets_at, period) if period else None
            warn = pct >= 100 or (time_pct is not None and pct > time_pct)
            marker_rel = max(0.0, min(1.0, time_pct / 100)) if time_pct is not None else None

            usage.append({
                'key': field,
                'label': label,
                'pct_text': f'{pct:.0f}%',
                'fill_pct': max(0.0, min(1.0, pct / 100)),
                'warn': warn,
                'reset_text': time_until(resets_at, countdown_only=field_countdown_only(field)) if resets_at else '',
                'dividers': divider_positions(resets_at, period) if period else [],
                'marker_rel': marker_rel,
            })

    # Extra usage
    extra = None
    if snap.usage:
        extra_data = snap.usage.get('extra_usage')
        if extra_data and extra_data.get('is_enabled'):
            used = extra_data.get('used_credits')
            if used is not None:
                limit = extra_data.get('monthly_limit', 0) or 0
                currency = extra_data.get('currency')
                decimal_places = extra_data.get('decimal_places')
                if limit > 0:
                    pct = used / limit * 100
                    extra = {
                        'has_limit': True,
                        'pct_text': f'{pct:.0f}%',
                        'fill_pct': max(0.0, min(1.0, pct / 100)),
                        'spent_text': T['extra_usage_spent'].format(
                            used=format_credits(used, currency, decimal_places),
                            limit=format_credits(limit, currency, decimal_places),
                        ),
                    }
                else:
                    # No monthly cap (e.g. uncapped pay-as-you-go credits) - show
                    # what has been spent without a percentage bar to imply a limit.
                    extra = {
                        'has_limit': False,
                        'pct_text': '',
                        'fill_pct': 0.0,
                        'spent_text': T['extra_usage_spent_no_limit'].format(
                            used=format_credits(used, currency, decimal_places),
                        ),
                    }

    # Installations
    if installations is None:
        installations = [{'name': i.name, 'version': i.version} for i in find_installations()]

    # Status - pass raw timestamps for JS live timer; fallback text for initial load
    if not snap.usage:
        if snap.last_error:
            status: dict[str, Any] = {'text': snap.last_error[:120], 'is_error': True}
        else:
            status = {'text': T['status_refreshing'], 'is_error': False, 'refreshing': True}
    else:
        status = {
            'last_success_time': snap.last_success_time,
            'next_poll_time': next_poll_time,
            'refreshing': snap.refreshing,
            'error': snap.last_error[:120] if snap.last_error else None,
        }

    return {
        'profile': profile,
        'usage': usage,
        'extra': extra,
        'installations': installations,
        'status': status,
    }


def _init_config(snap: CacheSnapshot, next_poll_time: float | None = None) -> dict[str, Any]:
    """Build the config object passed to JS ``init()`` after the page loads."""
    return {
        'colors': {
            'bg': BG, 'fg': FG, 'fg_dim': FG_DIM, 'fg_heading': FG_HEADING, 'fg_link': FG_LINK,
            'bar_bg': BAR_BG, 'bar_fg': BAR_FG, 'bar_fg_warn': BAR_FG_WARN, 'bar_divider': BAR_DIVIDER, 'bar_marker': BAR_MARKER,
        },
        't': {
            'title': T['popup_title'], 'account': T['account'], 'email': T['email'], 'plan': T['plan'],
            'usage': T['usage'], 'extra_usage': T['extra_usage'], 'name': T['name'],
            'reveal_email': T['reveal_email'], 'hide_email': T['hide_email'],
            'claude_code': T['claude_code'], 'changelog': T['changelog'],
            'pin_popup': T['pin_popup'], 'unpin_popup': T['unpin_popup'], 'refresh': T['refresh'],
            'detail_tokens': T['detail_tokens'], 'detail_messages': T['detail_messages'],
            'detail_estimated': T['detail_estimated'], 'detail_models': T['detail_models'],
            'detail_loading': T['detail_loading'], 'detail_unavailable': T['detail_unavailable'],
            'detail_no_usage': T['detail_no_usage'], 'detail_source': T['detail_source'],
            'status_updated_s': T['status_updated_s'], 'status_updated': T['status_updated'],
            'status_next_update': T['status_next_update'], 'status_refreshing': T['status_refreshing'],
            'duration_hm': T['duration_hm'], 'duration_m': T['duration_m'], 'duration_s': T['duration_s'],
        },
        'app_version': __version__,
        'compact_hide': COMPACT_HIDE,
        'data': _snapshot_to_dict(snap, next_poll_time=next_poll_time),
    }


# ---------------------------------------------------------------------------
# JS-callable API
# ---------------------------------------------------------------------------

class _PopupApi:
    """Methods exposed to JavaScript via pywebview's JS bridge."""

    def __init__(self, popup: UsagePopup) -> None:
        self._popup = popup

    def close(self) -> None:
        self._popup._close()

    def open_url(self) -> None:
        webbrowser.open(CHANGELOG_URL)

    def refresh(self) -> bool:
        return self._popup._manual_refresh()

    def session_detail(self, field: str) -> dict[str, Any]:
        return self._popup._session_detail(field)

    def set_pinned(self, pinned: bool) -> bool:
        return self._popup._set_pinned(pinned)

    def begin_drag(self) -> bool:
        return self._popup._begin_drag()

    def drag(self) -> bool:
        return self._popup._drag()

    def end_drag(self) -> None:
        self._popup._end_drag()

    def report_height(self, height: int) -> None:
        """Called by JS ResizeObserver when content height changes.

        pywebview dispatches every bridge call on a fresh thread, so two
        rapid reports could interleave and apply the earlier resize after
        the later one, or both start the show path.  The geometry lock
        serializes the whole check-resize-show sequence.
        """
        if not height:
            return

        popup = self._popup
        with popup._geometry_lock:
            if height == popup._last_height:
                return
            popup._last_height = height
            popup._resize_and_position(height)
            if not popup._shown:
                popup._show_window()


# ---------------------------------------------------------------------------
# Popup window
# ---------------------------------------------------------------------------

class UsagePopup:
    """Dark-themed HTML popup window showing account info and usage bars."""

    WIDTH = 340
    _CHECK_MS = 2000
    _REFRESH_MIN_INTERVAL = 5.0

    def __init__(self, app: UsageMonitorForClaude) -> None:
        """Create and display a popup window with usage details.

        Blocks the calling thread until the window is closed.
        Requires ``webview.start()`` to be running on the main thread.

        Parameters
        ----------
        app : UsageMonitorForClaude
            Parent application providing ``cache`` for data access.
        """
        self.app = app
        self._running = True
        self._pinned = False
        self._moved_while_pinned = False
        self._dragging = False
        self._drag_offset = (0, 0)
        self._drag_start_dpi = 0
        self._closed = threading.Event()
        self._popup_hwnd = 0
        self._pump_tid = 0
        # Serializes the resize/show geometry path across pywebview's
        # per-call bridge threads.
        self._geometry_lock = threading.Lock()
        # Serializes manual refreshes against each other and carries the
        # timestamp used to rate-limit repeated button presses.
        self._refresh_lock = threading.Lock()
        self._last_manual_refresh = 0.0
        self._cached_installations: list[dict[str, str]] | None = None
        initial_height = 400
        # 0 means "no height reported yet": the first ResizeObserver report
        # must always count as a change so the window gets resized,
        # positioned, and shown even when the content is exactly
        # initial_height tall.
        self._last_height = 0
        snap = app.cache.snapshot
        self._last_version = snap.version

        api = _PopupApi(self)

        self._window = webview.create_window(
            '', url=str(_POPUP_DIR / 'popup.html'),
            width=self.WIDTH, height=initial_height,
            resizable=False, frameless=True, shadow=False,
            easy_drag=False,
            on_top=True, hidden=True,
            background_color=BG,
            js_api=api,
        )
        self._shown = False
        self._window.events.loaded += self._on_loaded
        self._window.events.closed += self._on_window_closed
        threading.Thread(target=self._dismiss_watch, daemon=True).start()
        self._closed.wait()

    def _on_loaded(self) -> None:
        """Inject config and show the window transparently for layout."""
        config = _init_config(self.app.cache.snapshot, next_poll_time=self.app._next_poll_time)
        self._window.evaluate_js(f'init({json.dumps(config)})')

        self._popup_hwnd = self._window.native.Handle.ToInt32()

        # Hide the taskbar icon and enable layered mode for opacity control.
        # WinForms sets WS_EX_APPWINDOW by default, which forces a taskbar
        # button even when WS_EX_TOOLWINDOW is present - both must be fixed.
        # WS_EX_LAYERED is needed for SetLayeredWindowAttributes (opacity).
        ex_style = ctypes.windll.user32.GetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            self._popup_hwnd, _GWL_EXSTYLE,
            (ex_style | _WS_EX_TOOLWINDOW | _WS_EX_LAYERED) & ~_WS_EX_APPWINDOW,
        )

        # Show fully transparent so JS can layout and report the real height
        ctypes.windll.user32.SetLayeredWindowAttributes(self._popup_hwnd, 0, 0, _LWA_ALPHA)
        self._window.show()

    def _show_window(self) -> None:
        """Make the popup visible after the first resize positioned it correctly."""
        # Remove the layered style to restore normal rendering
        ex_style = ctypes.windll.user32.GetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(self._popup_hwnd, _GWL_EXSTYLE, ex_style & ~_WS_EX_LAYERED)
        self._shown = True
        threading.Thread(target=self._update_loop, daemon=True).start()

    def _dismiss_watch(self) -> None:
        """Close the popup on click-outside, Escape, or focus change.

        Combines three Win32 mechanisms in a single message pump:

        * ``WH_MOUSE_LL`` - catches clicks outside the popup bounds
        * ``WH_KEYBOARD_LL`` - catches Escape even without focus
        * ``EVENT_SYSTEM_FOREGROUND`` - catches Alt-Tab, browser open, etc.

        The foreground hook uses a short delay to ride out the brief
        focus bounce that WebView2 causes between its host and renderer
        process on every click inside the content area.
        """
        this_thread = ctypes.windll.kernel32.GetCurrentThreadId()

        # Force creation of this thread's message queue before publishing the
        # thread id, so a WM_QUIT posted by _post_pump_quit() from another
        # thread cannot be lost in the queue-creation window.
        msg = ctypes.wintypes.MSG()
        ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # PM_NOREMOVE
        self._pump_tid = this_thread

        def _post_quit() -> None:
            if self._shown and not self._pinned:
                ctypes.windll.user32.PostThreadMessageW(this_thread, _WM_QUIT, 0, 0)

        # -- Shared argtypes for CallNextHookEx --
        _call_next = ctypes.windll.user32.CallNextHookEx
        _call_next.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
        _call_next.restype = ctypes.c_long

        # -- Mouse hook: click outside popup bounds --
        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [('pt', ctypes.wintypes.POINT), ('mouseData', ctypes.wintypes.DWORD),
                         ('flags', ctypes.wintypes.DWORD), ('time', ctypes.wintypes.DWORD),
                         ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]

        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        def mouse_proc(code, wparam, lparam):
            if code >= 0 and wparam == 0x0201:  # WM_LBUTTONDOWN
                popup_hwnd = self._popup_hwnd
                if popup_hwnd:
                    rect = ctypes.wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(popup_hwnd, ctypes.byref(rect))
                    info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    if not (rect.left <= info.pt.x <= rect.right and rect.top <= info.pt.y <= rect.bottom):
                        _post_quit()
            return _call_next(None, code, wparam, lparam)

        # -- Keyboard hook: Escape key --
        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [('vkCode', ctypes.wintypes.DWORD), ('scanCode', ctypes.wintypes.DWORD),
                         ('flags', ctypes.wintypes.DWORD), ('time', ctypes.wintypes.DWORD),
                         ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]

        @ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        def kb_proc(code, wparam, lparam):
            if code >= 0 and wparam == 0x0100:  # WM_KEYDOWN
                info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if info.vkCode == 0x1B:  # VK_ESCAPE
                    _post_quit()
            return _call_next(None, code, wparam, lparam)

        # -- Foreground event with delayed check --
        WINEVENT_CALLBACK = ctypes.WINFUNCTYPE(
            None, ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD, ctypes.wintypes.HWND,
            ctypes.wintypes.LONG, ctypes.wintypes.LONG, ctypes.wintypes.DWORD, ctypes.wintypes.DWORD,
        )

        _fg_timer: threading.Timer | None = None

        def _delayed_fg_check() -> None:
            """Check if focus is still outside the popup after the delay."""
            popup_hwnd = self._popup_hwnd
            if not popup_hwnd or not self._shown:
                return
            fg = ctypes.windll.user32.GetForegroundWindow()
            if fg == popup_hwnd:
                return
            if ctypes.windll.user32.IsChild(popup_hwnd, fg):
                return
            if ctypes.windll.user32.GetAncestor(fg, 3) == popup_hwnd:  # GA_ROOTOWNER
                return
            _post_quit()

        @WINEVENT_CALLBACK
        def fg_proc(_hook, _event, hwnd, _id_obj, _id_child, _thread, _time):
            nonlocal _fg_timer
            popup_hwnd = self._popup_hwnd
            if not popup_hwnd:
                return
            # Quick accept: focus moved to a child/owned window of our popup
            if ctypes.windll.user32.IsChild(popup_hwnd, hwnd):
                return
            if ctypes.windll.user32.GetAncestor(hwnd, 3) == popup_hwnd:  # GA_ROOTOWNER
                return
            # Delay the dismiss to ride out WebView2's focus bounce
            # between host and renderer process on content clicks.
            if _fg_timer is not None:
                _fg_timer.cancel()
            _fg_timer = threading.Timer(0.2, _delayed_fg_check)
            _fg_timer.daemon = True
            _fg_timer.start()

        mouse_hook = ctypes.windll.user32.SetWindowsHookExW(14, mouse_proc, None, 0)  # WH_MOUSE_LL
        kb_hook = ctypes.windll.user32.SetWindowsHookExW(13, kb_proc, None, 0)  # WH_KEYBOARD_LL
        # EVENT_SYSTEM_FOREGROUND with WINEVENT_SKIPOWNPROCESS
        fg_hook = ctypes.windll.user32.SetWinEventHook(0x0003, 0x0003, None, fg_proc, 0, 0, 0x0002)

        try:
            while self._running and ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            if _fg_timer is not None:
                _fg_timer.cancel()
            ctypes.windll.user32.UnhookWindowsHookEx(mouse_hook)
            ctypes.windll.user32.UnhookWindowsHookEx(kb_hook)
            ctypes.windll.user32.UnhookWinEvent(fg_hook)
            self._pump_tid = 0

        self._close()

    def _post_pump_quit(self) -> None:
        """Wake the dismiss-watch pump so it can remove its hooks and exit.

        The pump blocks inside ``GetMessageW`` and re-checks ``_running``
        only after a message arrives, so setting the flag alone is not
        enough - especially while pinned, where the user-dismissal path
        (``_post_quit``) never posts.
        """
        if self._pump_tid:
            ctypes.windll.user32.PostThreadMessageW(self._pump_tid, _WM_QUIT, 0, 0)

    def _on_window_closed(self) -> None:
        self._running = False
        self._post_pump_quit()
        self._closed.set()

    def _close(self) -> None:
        self._running = False
        self._post_pump_quit()
        try:
            self._window.destroy()
        except Exception:
            pass
        self._closed.set()

    def _set_pinned(self, pinned: bool) -> bool:
        self._pinned = bool(pinned)
        if not self._pinned:
            self._moved_while_pinned = False
        return self._pinned

    def _begin_drag(self) -> bool:
        """Anchor the cursor to the window for a pinned-popup drag.

        Records the physical offset between the cursor and the window's
        top-left corner.  Dragging is then done entirely in physical
        screen coordinates, which keeps the cursor anchored even across
        monitors with different DPI scaling, where logical-pixel deltas
        would jump at the boundary.
        """
        if not self._pinned or not self._popup_hwnd:
            return False

        cursor = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(self._popup_hwnd, ctypes.byref(rect))
        self._drag_offset = (cursor.x - rect.left, cursor.y - rect.top)
        self._drag_start_dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        self._dragging = True
        return True

    def _drag(self) -> bool:
        """Reposition the popup so the cursor keeps its initial grab offset.

        Each step computes the absolute window position from the current
        physical cursor position, so out-of-order calls converge on the
        right spot instead of accumulating drift.
        """
        if not self._dragging or not self._pinned or not self._popup_hwnd:
            return False

        cursor = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
        x = cursor.x - self._drag_offset[0]
        y = cursor.y - self._drag_offset[1]
        ctypes.windll.user32.SetWindowPos(self._popup_hwnd, 0, x, y, 0, 0, _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE)
        self._moved_while_pinned = True
        return True

    def _end_drag(self) -> None:
        """Finish a drag and correct the size after a cross-monitor DPI change.

        Crossing a monitor boundary triggers Windows' Per-Monitor-V2
        rescale, which can race with pywebview's size handling and leave
        the popup mis-sized.  Re-asserting the size once, against the
        destination monitor's DPI, makes the final dimensions
        deterministic.  Position is preserved by ``resize``'s default
        top-left fix point.
        """
        self._dragging = False
        if not self._popup_hwnd:
            return

        current_dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        if current_dpi != self._drag_start_dpi:
            with self._geometry_lock:
                self._window.resize(self.WIDTH, self._last_height)

    def _push_snapshot(self, snap: CacheSnapshot, next_poll_time: float | None, rescan_installations: bool) -> None:
        """Render *snap* into the open popup.

        Raises whatever ``evaluate_js`` raises; callers decide how to
        recover.  ``_last_version`` is committed only after a successful
        push so a failed one is retried instead of being swallowed by the
        dedup check.
        """
        if rescan_installations or self._cached_installations is None:
            self._cached_installations = [{'name': i.name, 'version': i.version} for i in find_installations()]

        data = _snapshot_to_dict(snap, installations=self._cached_installations, next_poll_time=next_poll_time)
        self._window.evaluate_js(f'updateData({json.dumps(data)})')
        self._last_version = snap.version

    def _session_detail(self, field: str) -> dict[str, Any]:
        """Local-transcript detail for a clicked usage bar: tokens, messages, models.

        Reads ``<config dir>/projects/*.jsonl`` for the same window the
        bar's percentage covers, so the numbers returned are exact sums of
        what Claude Code actually recorded - not a re-derivation of the
        official percentage.  Runs on a pywebview bridge thread; any
        failure (unreadable transcripts, a field this fork does not track
        detail for) yields the empty shape below rather than raising, so a
        broken detail fetch cannot take down the popup.

        Parameters
        ----------
        field : str
            'five_hour' or 'seven_day'.  Anything else returns the empty
            shape - there is no local-log equivalent for a model-scoped or
            unlabeled quota.

        Returns
        -------
        dict
            ``{unavailable, tokens, messages, estimated_total, models}``.
            ``unavailable`` is True when there is nothing meaningful to
            show (unsupported field, unreadable transcripts) - the popup
            renders a fallback message rather than a zeroed report, which
            would misleadingly claim "confirmed zero usage". When False,
            ``tokens``/``messages``/``estimated_total`` are comma-grouped
            strings ready to display (``estimated_total`` may still be
            ``None`` - see below), and ``models`` is a list of
            ``{model, tokens, pct}`` with ``tokens`` comma-grouped and
            ``pct`` a string like ``'96.6'``.

            ``estimated_total`` is ``tokens / (utilization / 100)``,
            included only once the utilization is high enough for that
            division to be meaningful. It is an extrapolation from the
            API's own reported percentage, not a guess at Anthropic's
            actual limit - the two can disagree since the transcripts and
            the API may not account for tokens identically.
        """
        unavailable: dict[str, Any] = {
            'unavailable': True, 'tokens': None, 'messages': None, 'estimated_total': None, 'models': [],
        }

        period = field_period(field)
        if period is None or field not in ('five_hour', 'seven_day'):
            return unavailable

        try:
            snap = self.app.cache.snapshot
            entry = (snap.usage or {}).get(field) if snap else None
        except Exception:
            entry = None
        if not isinstance(entry, dict):
            return unavailable

        resets_at_raw = entry.get('resets_at')
        utilization = entry.get('utilization')

        now = time.time()
        end = now
        if resets_at_raw:
            try:
                text = resets_at_raw[:-1] + '+00:00' if resets_at_raw.endswith('Z') else resets_at_raw
                end = datetime.fromisoformat(text).timestamp()
            except ValueError:
                end = now
        start = end - period

        try:
            stats = session_logs.usage_in_window(CLAUDE_CONFIG_DIR / 'projects', start, end)
        except Exception:
            logger.debug('session_detail: local log scan failed', exc_info=True)
            return unavailable

        estimated_total = None
        if (
            isinstance(utilization, (int, float))
            and utilization >= _MIN_UTILIZATION_FOR_ESTIMATE
            and stats.total_tokens > 0
        ):
            estimated_total = format_count(round(stats.total_tokens / (utilization / 100)))

        return {
            'unavailable': False,
            'tokens': format_count(stats.total_tokens),
            'messages': format_count(stats.message_count),
            'estimated_total': estimated_total,
            'models': [
                {'model': m.model, 'tokens': format_count(m.tokens), 'pct': f'{m.fraction * 100:.1f}'}
                for m in stats.models
            ],
        }

    def _manual_refresh(self) -> bool:
        """Fetch usage data now, on user request from the popup's refresh button.

        Runs on a pywebview bridge thread, so the JS promise resolves once
        the fetch is done and the popup has been re-rendered.  ``force``
        bypasses the cache cooldown and the 429 backoff, which is what the
        user asked for by clicking - but repeated presses are throttled to
        one fetch per ``_REFRESH_MIN_INTERVAL`` seconds so the button cannot
        be used to hammer the API.  A refresh already in flight is not
        joined; the caller simply gets ``False``.

        Returns
        -------
        bool
            True if a fetch was actually performed.
        """
        if not self._running:
            return False

        if not self._refresh_lock.acquire(blocking=False):
            return False

        try:
            now = time.time()
            if now - self._last_manual_refresh < self._REFRESH_MIN_INTERVAL:
                return False
            self._last_manual_refresh = now

            if not self.app.cache.profile:
                self.app.cache.ensure_profile()
            self.app.update(force=True)
        except Exception:
            # A failed fetch is already reflected in the snapshot's error
            # state; never let it propagate into the JS bridge.
            return False
        finally:
            self._refresh_lock.release()

        if not self._running:
            return False

        try:
            self._push_snapshot(self.app.cache.snapshot, self.app._next_poll_time, rescan_installations=True)
        except Exception:
            # The periodic update loop pushes the same data within _CHECK_MS.
            return True

        return True

    def _update_loop(self) -> None:
        """Poll for data changes and push updates to the popup."""
        last_next_poll_time = self.app._next_poll_time
        while self._running:
            time.sleep(self._CHECK_MS / 1000)
            if not self._running:
                break
            try:
                snap = self.app.cache.snapshot
                next_poll_time = self.app._next_poll_time
                if snap.version == self._last_version and next_poll_time == last_next_poll_time:
                    continue
                self._push_snapshot(snap, next_poll_time, rescan_installations=snap.version != self._last_version)
                last_next_poll_time = next_poll_time
            except Exception:
                # A transient failure (snapshot conversion, filesystem scan,
                # one-off evaluate_js hiccup) must not end the update stream -
                # a pinned popup can live for days.  The destroyed-window
                # case exits via the _running flag on the next iteration.
                continue

    def _tray_position(self, physical_width: int, physical_height: int) -> tuple[int, int]:
        """Calculate popup position near the system tray.

        Parameters
        ----------
        physical_width : int
            Actual window width in physical pixels.
        physical_height : int
            Actual window height in physical pixels.

        The popup is kept clear of the taskbar by two independent bounds:
        the monitor work area Windows reports, and the taskbar window's own
        rectangle.  The stricter of the two wins.  The second bound matters
        because an auto-hiding taskbar is not subtracted from the work area
        at all, so the work area alone would place the popup underneath it.
        The ``popup_margin`` setting is the gap left beyond that bound, in
        physical pixels.

        Returns
        -------
        tuple[int, int]
            Logical (x, y) coordinates.  Callers that need physical pixels
            must multiply by the DPI scale factor.
        """
        tray_hwnd = ctypes.windll.user32.FindWindowW('Shell_TrayWnd', None)
        hmon = ctypes.windll.user32.MonitorFromWindow(tray_hwnd, 2)  # MONITOR_DEFAULTTONEAREST

        mon_info = _MONITORINFO()
        mon_info.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mon_info))
        mon = mon_info.rcMonitor
        work = mon_info.rcWork

        dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / _BASELINE_DPI

        margin = POPUP_MARGIN
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

    def _resize_and_position(self, height: int) -> None:
        """Resize the window and reposition it near the system tray.

        The first call happens while the window is still transparent
        (opacity 0), so separate resize/move calls cause no visible jump.

        pywebview 6.x ``resize()`` applies DPI scaling internally (consistent
        with ``move()``), so both expect logical pixels.  Physical dimensions
        are still computed for ``_tray_position``, which needs them to
        calculate the correct logical position against the physical work-area
        coordinates returned by Win32.
        """
        dpi = ctypes.windll.user32.GetDpiForWindow(self._popup_hwnd) or ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / _BASELINE_DPI
        physical_width = int(self.WIDTH * scale)
        physical_height = int(height * scale)
        self._window.resize(self.WIDTH, height)
        if self._pinned and self._moved_while_pinned:
            return
        x, y = self._tray_position(physical_width, physical_height)
        self._window.move(x, y)
