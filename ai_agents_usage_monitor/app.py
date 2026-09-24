"""
Application
=============

System tray application class with adaptive polling and event handling.
"""
from __future__ import annotations

import ctypes
import math
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Any

import pystray  # type: ignore[import-untyped]  # no type stubs available

from .claude_api import api_headers, read_access_token
from .autostart import is_autostart_enabled, set_autostart, sync_autostart_path
from .claude_cache import UsageCache
from .claude_cli import PROJECT_URL
from .codex_api import CodexAccount
from .codex_cli import CodexInstallations
from .command import run_event_command
from .events import quick_action_env, reset_env, startup_env, threshold_env
from .idle import get_idle_seconds, is_workstation_locked
from .instance_id import effective_config_dir, is_default_config_dir
from .settings import (
    ALERT_EXTRA_USAGE_SPENT, ALERT_TIME_AWARE, ALERT_TIME_AWARE_BELOW, ICON_FIELDS, IDLE_PAUSE, NOTIFY_CLAUDE_UPDATE,
    ON_RESET_COMMAND, ON_STARTUP_COMMAND, ON_THRESHOLD_COMMAND, QUICK_ACTION_COMMAND,
    POLL_ERROR, POLL_FAST, POLL_FAST_EXTRA, POLL_INTERVAL, POPUP_VIEW,
    TRAY_PROVIDER, get_alert_thresholds,
)
from .settings_store import save_setting
from .formatting import (
    codex_reset_iso, duration_label, elapsed_pct, field_period, format_codex_tooltip, format_credits,
    format_tooltip, parse_field_name, popup_label,
)
from .i18n import T
from .popup import UsagePopup
from .scheduling import RESET_BUFFER, align_to_reset, clamp_to_reset, earliest_reset, reset_aligned_target, tracked_reset_times
from .tray_icon import create_icon_image, create_status_image, taskbar_uses_light_theme, watch_theme_change
from .tray_menu import build_menu

__all__ = ['AIAgentsUsageMonitor', 'crash_log']

# Refresh intervals offered by the tray menu.  One minute leads because it is
# the app's rule; the slower two exist for a user who deliberately wants fewer
# requests.  The choice is written back to the settings file, so the next start
# keeps the cadence the user picked.  Only the cadence changes: POLL_FAST stays
# at its own value, so the cache cooldown and the reset-aligned confirming poll
# are as exact under a five-minute cadence as under one minute.
REFRESH_INTERVALS = (60, 180, 300)

# Win32 tray mouse messages, delivered by the shell as the WM_NOTIFY lParam.
# pystray natively acts only on WM_LBUTTONUP; WM_LBUTTONDBLCLK drives the
# optional double-click command.
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203


def _future_iso(**kwargs: float) -> str:
    """Return an ISO 8601 timestamp offset from now by the given timedelta kwargs."""
    return (datetime.now(timezone.utc) + timedelta(**kwargs)).isoformat()


def _align_to_reset(interval: int, next_reset: float | None) -> tuple[int, bool]:
    """Shift the next poll so the confirming poll lands just after the reset.

    Binds this app's cadence values to the rule in ``scheduling``, which takes
    them as arguments so it can be read on its own.

    Parameters
    ----------
    interval : int
        The normal cadence interval before reset alignment.
    next_reset : float or None
        Seconds until the nearest upcoming reset, or None.

    Returns
    -------
    tuple[int, bool]
        The (possibly adjusted) interval and whether alignment engaged.
    """
    return align_to_reset(interval, next_reset, POLL_FAST, RESET_BUFFER)


class AIAgentsUsageMonitor:
    """System tray application displaying Claude usage."""

    def __init__(self) -> None:
        """Set up the tray icon with context menu and polling state."""
        self.running = True
        self.cache = UsageCache()
        self.codex_account = CodexAccount()
        self.codex_installations = CodexInstallations()

        # Last raw API response (may contain 'error') - for icon and polling decisions
        self._last_response: dict[str, Any] = {}

        # Notification state
        self._prev_utilization: dict[str, float] = {}
        self._prev_account_uuid: str | None = None
        self._first_update_done = False
        self._notified_thresholds: dict[str, float] = {}

        # Adaptive polling state
        self._fast_polls_remaining = 0
        self._idle_reset_pending = False
        # Guarded by _notify_lock: deferrals arrive from the popup and poll
        # threads while the poll loop flushes.
        self._notify_lock = threading.Lock()
        self._deferred_notifications: dict[str, tuple[str, str]] = {}

        # Popup state
        self._popup_lock = threading.Lock()
        self._popup_open = False
        # Seeded with the launch time so the app polls normally for the first
        # IDLE_PAUSE seconds instead of starting out paused.
        self._popup_closed_at = time.time()
        self._next_poll_time: float | None = None

        # Theme state
        self._light_taskbar = taskbar_uses_light_theme()

        # Which agent the tray icon, its tooltip and the threshold alerts follow.
        self._tray_provider = TRAY_PROVIDER

        # How often the cadence poll runs.
        self._poll_interval = POLL_INTERVAL

        self._popup_view = POPUP_VIEW

        # Non-default config dirs get a tooltip prefix so multiple
        # instances (one per Claude account) can be told apart.
        self._tooltip_prefix = '' if is_default_config_dir() else f'[{effective_config_dir().name}] '

        self.icon = pystray.Icon(
            'usage_monitor',
            icon=create_icon_image(0, 0, self._light_taskbar),
            title=self._tooltip_prefix + T['loading'],
            menu=build_menu(self),
        )

        # Double-click support.  pystray fires the default action (the popup) on
        # every left-button release, so a double-click command requires deferring
        # that single click by the system double-click interval and cancelling it
        # when a second click arrives.  Only wired up when a command is
        # configured, so the default single-click behavior is otherwise untouched.
        self._click_lock = threading.Lock()
        self._single_click_timer: threading.Timer | None = None
        self._swallow_next_up = False
        if QUICK_ACTION_COMMAND:
            self._double_click_seconds = ctypes.windll.user32.GetDoubleClickTime() / 1000.0
            self._install_double_click_handler()

    # Menu actions

    def on_show_popup(self, icon: Any = None, item: Any = None) -> None:
        with self._popup_lock:
            if self._popup_open:
                return
            if time.time() - self._popup_closed_at < 0.15:
                return
            self._popup_open = True
        threading.Thread(target=self._open_popup, daemon=True).start()

    def on_tray_claude(self, icon: Any = None, item: Any = None) -> None:
        self._set_tray_provider('claude')

    def on_tray_codex(self, icon: Any = None, item: Any = None) -> None:
        self._set_tray_provider('codex')

    def _set_tray_provider(self, provider: str) -> None:
        """Point the tray icon, its tooltip and the threshold alerts at one agent.

        The choice is stored as ``tray_provider``, so the next start follows
        the same agent.  The redraw is handed to a worker thread because a
        Codex read starts the app-server and can take seconds, which would
        freeze the menu it was clicked from - and the save goes with it, so
        neither a slow nor an unwritable disk can freeze that menu either.

        Parameters
        ----------
        provider : str
            Either ``'claude'`` or ``'codex'``.
        """
        assert provider in ('claude', 'codex')
        if provider == self._tray_provider:
            return

        self._tray_provider = provider
        threading.Thread(target=self._apply_tray_provider, args=(provider,), daemon=True).start()

    def on_refresh_1min(self, icon: Any = None, item: Any = None) -> None:
        self._set_poll_interval(60)

    def on_refresh_3min(self, icon: Any = None, item: Any = None) -> None:
        self._set_poll_interval(180)

    def on_refresh_5min(self, icon: Any = None, item: Any = None) -> None:
        self._set_poll_interval(300)

    def _set_poll_interval(self, seconds: int) -> None:
        """Change how often the cadence poll runs.

        The poll loop is waiting out the previous interval, so it re-anchors
        its target on the new value rather than being interrupted here: a
        shorter choice therefore takes effect within a second instead of after
        the old, longer wait has run out.  The choice is stored under the same
        ``poll_interval`` key a user sets by hand, so the next start begins on
        the chosen cadence.

        Parameters
        ----------
        seconds : int
            One of ``REFRESH_INTERVALS``.
        """
        assert seconds in REFRESH_INTERVALS

        self._poll_interval = seconds
        save_setting('poll_interval', seconds)

    def on_toggle_autostart(self, icon: Any = None, item: Any = None) -> None:
        set_autostart(not is_autostart_enabled())

    def on_open_project(self, icon: Any = None, item: Any = None) -> None:
        webbrowser.open(PROJECT_URL)

    def on_test_reset_5h(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_RESET_COMMAND, {
            'USAGE_MONITOR_EVENT': 'reset',
            'USAGE_MONITOR_VARIANT': 'five_hour',
            'USAGE_MONITOR_UTILIZATION': '0',
            'USAGE_MONITOR_PREV_UTILIZATION': '95',
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '0',
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '45',
            'USAGE_MONITOR_RESETS_AT': _future_iso(hours=5),
            'USAGE_MONITOR_TITLE': T['notify_reset_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_reset'],
        }, capture_output=True)

    def on_test_reset_7d(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_RESET_COMMAND, {
            'USAGE_MONITOR_EVENT': 'reset',
            'USAGE_MONITOR_VARIANT': 'seven_day',
            'USAGE_MONITOR_UTILIZATION': '0',
            'USAGE_MONITOR_PREV_UTILIZATION': '99',
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '12',
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '0',
            'USAGE_MONITOR_RESETS_AT': _future_iso(days=7),
            'USAGE_MONITOR_TITLE': T['notify_reset_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_reset'],
        }, capture_output=True)

    def on_test_threshold_5h(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_THRESHOLD_COMMAND, {
            'USAGE_MONITOR_EVENT': 'threshold',
            'USAGE_MONITOR_VARIANT': 'five_hour',
            'USAGE_MONITOR_UTILIZATION': '82',
            'USAGE_MONITOR_THRESHOLD': '80',
            'USAGE_MONITOR_RESETS_AT': _future_iso(hours=3),
            'USAGE_MONITOR_TITLE': T['notify_threshold_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_threshold_generic'].format(label=popup_label('five_hour'), pct='82'),
        }, capture_output=True)

    def on_test_threshold_7d(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_THRESHOLD_COMMAND, {
            'USAGE_MONITOR_EVENT': 'threshold',
            'USAGE_MONITOR_VARIANT': 'seven_day',
            'USAGE_MONITOR_UTILIZATION': '81',
            'USAGE_MONITOR_THRESHOLD': '80',
            'USAGE_MONITOR_RESETS_AT': _future_iso(days=4),
            'USAGE_MONITOR_TITLE': T['notify_threshold_title'],
            'USAGE_MONITOR_MESSAGE': T['notify_threshold_generic'].format(label=popup_label('seven_day'), pct='81'),
        }, capture_output=True)

    def on_test_startup(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(ON_STARTUP_COMMAND, {
            'USAGE_MONITOR_EVENT': 'startup',
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '0',
            'USAGE_MONITOR_RESETS_AT_FIVE_HOUR': '',
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '45',
            'USAGE_MONITOR_RESETS_AT_SEVEN_DAY': _future_iso(days=3),
        }, capture_output=True)

    def on_test_quick_action(self, icon: Any = None, item: Any = None) -> None:
        run_event_command(QUICK_ACTION_COMMAND, {
            'USAGE_MONITOR_EVENT': 'quick_action',
            'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '30',
            'USAGE_MONITOR_RESETS_AT_FIVE_HOUR': _future_iso(hours=3),
            'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '55',
            'USAGE_MONITOR_RESETS_AT_SEVEN_DAY': _future_iso(days=4),
        }, capture_output=True)

    def on_quit(self, icon: Any = None, item: Any = None) -> None:
        self.running = False
        self.icon.stop()

    # Popup

    def _should_refresh_usage(self) -> bool:
        """Return whether opening the popup should trigger a background usage fetch.

        Refreshes stale data, with one exception: when a quota reset is closer
        than the cache cooldown, a fetch now would advance
        ``last_success_time`` into the last ``POLL_FAST`` window before the
        reset and force the reset-aligned poll to overshoot.  Such a fetch is
        deferred to the scheduled reset poll, whose fresh data the open popup
        picks up live.  The very first fetch (no data yet) always refreshes.
        """
        last = self.cache.last_success_time
        if last is None:
            return True
        if time.time() - last < POLL_FAST:
            return False

        next_reset = self._seconds_until_next_reset()
        return not (next_reset is not None and next_reset < POLL_FAST)

    def _open_popup(self) -> None:
        # _popup_open is set True under _popup_lock (in on_show_popup) and
        # reset here without the lock.  This is safe because False is the
        # permissive default - a momentary stale True only delays the next open.
        try:
            needs_profile = not self.cache.profile
            needs_refresh = self._should_refresh_usage()
            if needs_profile or needs_refresh:
                # Single thread: ensure_profile() and update() both acquire
                # cache._lock, so they must run sequentially.  Two threads
                # would cause update()'s non-blocking acquire to fail while
                # ensure_profile() holds the lock.
                def _bg_refresh() -> None:
                    if needs_profile:
                        self.cache.ensure_profile()
                    if needs_refresh:
                        self.update()
                threading.Thread(target=_bg_refresh, daemon=True).start()
            UsagePopup(self)
        finally:
            self._popup_closed_at = time.time()
            self._popup_open = False

    # Double-click handling

    def _install_double_click_handler(self) -> None:
        """Replace pystray's tray-message handler with a double-click-aware one.

        Locates the ``WM_NOTIFY`` entry in pystray's handler table by identity
        and swaps in :meth:`_on_tray_message`, keeping the original handler for
        right-click and every other message.
        """
        self._pystray_on_notify = self.icon._on_notify
        for code, handler in self.icon._message_handlers.items():
            if handler == self._pystray_on_notify:
                self.icon._message_handlers[code] = self._on_tray_message
                break

    def _on_tray_message(self, wparam: int, lparam: int) -> int:
        """Dispatch a tray mouse message, adding double-click handling.

        A left-button release schedules the popup after the double-click
        interval; a double-click cancels that pending popup and runs the
        configured command instead.  The trailing release that follows every
        double-click is swallowed so it does not schedule a second popup.  All
        other messages (right-click menu, etc.) fall through to pystray's own
        handler.
        """
        if lparam == WM_LBUTTONUP:
            with self._click_lock:
                if self._swallow_next_up:
                    self._swallow_next_up = False
                    return 0
                if self._single_click_timer is not None:
                    self._single_click_timer.cancel()
                self._single_click_timer = threading.Timer(self._double_click_seconds, self._fire_single_click)
                self._single_click_timer.daemon = True
                self._single_click_timer.start()
            return 0

        if lparam == WM_LBUTTONDBLCLK:
            with self._click_lock:
                self._swallow_next_up = True
                if self._single_click_timer is not None:
                    self._single_click_timer.cancel()
                    self._single_click_timer = None
            self._run_double_click_command()
            return 0

        return self._pystray_on_notify(wparam, lparam)

    def _fire_single_click(self) -> None:
        """Open the popup once the double-click interval passes without a second click.

        Bails out if the timer was cleared meanwhile - a double-click that
        arrived right as the timer fired cancels it here, so the popup never
        opens for a completed double-click.
        """
        with self._click_lock:
            if self._single_click_timer is None:
                return
            self._single_click_timer = None
        self.on_show_popup()

    # Tray rendering

    def _render_tray(self) -> None:
        """Re-render tray icon and tooltip from current state."""
        if self._tray_provider == 'codex':
            self._render_codex_tray(self.codex_account.snapshot(self._poll_interval))
            return

        data = self._last_response
        if 'error' in data:
            self.icon.icon = create_status_image('C!' if data.get('auth_error') else '!', self._light_taskbar)
        else:
            top_field, top_mode = ICON_FIELDS[0].split(':', 1) if ':' in ICON_FIELDS[0] else (ICON_FIELDS[0], 'utilization')
            bottom_field, bottom_mode = ICON_FIELDS[1].split(':', 1) if ':' in ICON_FIELDS[1] else (ICON_FIELDS[1], 'utilization')
            # isinstance instead of truthiness: a configured field may point at
            # a non-dict response value (e.g. the raw limits array).
            top_entry = data.get(top_field)
            bottom_entry = data.get(bottom_field)
            if not isinstance(top_entry, dict):
                top_entry = {}
            if not isinstance(bottom_entry, dict):
                bottom_entry = {}
            pct_top = top_entry.get('utilization', 0) or 0
            pct_bottom = bottom_entry.get('utilization', 0) or 0
            top_period = field_period(top_field)
            bottom_period = field_period(bottom_field)
            time_pct_top = elapsed_pct(top_entry.get('resets_at', ''), top_period) if top_period else None
            time_pct_bottom = elapsed_pct(bottom_entry.get('resets_at', ''), bottom_period) if bottom_period else None
            extra = data.get('extra_usage') or {}
            extra_limit = extra.get('monthly_limit') or 0
            extra_used = extra.get('used_credits') or 0
            # A missing/null monthly_limit means uncapped pay-as-you-go extra
            # usage, which cannot be exhausted.
            extra_usage_available = bool(extra.get('is_enabled')) and (extra_limit <= 0 or extra_used < extra_limit)
            self.icon.icon = create_icon_image(
                pct_top, pct_bottom, self._light_taskbar,
                mode_top=top_mode, mode_bottom=bottom_mode,
                time_pct_top=time_pct_top, time_pct_bottom=time_pct_bottom,
                extra_usage_available=extra_usage_available,
            )
        self.icon.title = self._tooltip_prefix + format_tooltip(data)

    def _render_codex_tray(self, snapshot: dict[str, Any]) -> None:
        """Draw the tray icon and tooltip from the Codex account snapshot.

        Codex reports its windows as a list ordered by length, so the shortest
        one takes the top row and the longest the bottom - the same reading the
        Claude default (session above weekly) gives.  ``icon_fields`` is not
        consulted: it names Claude API fields, which have no Codex counterpart.

        Parameters
        ----------
        snapshot : dict
            A ``CodexAccount.snapshot()`` result.
        """
        windows = snapshot.get('windows') or []
        if snapshot.get('error') or not windows:
            self.icon.icon = create_status_image('!', self._light_taskbar)
        else:
            top, bottom = windows[0], windows[-1]
            self.icon.icon = create_icon_image(
                top['used'], bottom['used'], self._light_taskbar,
                time_pct_top=elapsed_pct(codex_reset_iso(top['resets_at']), top['seconds']),
                time_pct_bottom=elapsed_pct(codex_reset_iso(bottom['resets_at']), bottom['seconds']),
                extra_usage_available=False,
            )
        self.icon.title = self._tooltip_prefix + format_codex_tooltip(snapshot)

    def _apply_tray_provider(self, provider: str) -> None:
        """Redraw the tray for a freshly selected provider, off the tray thread.

        Claude data is already in hand except before the first successful
        fetch, and only a successful fetch starts the cache cooldown, so the
        cold-start branch is free to ask for one right away.

        Parameters
        ----------
        provider : str
            The provider selected in the tray menu.
        """
        if provider == 'codex':
            snapshot = self.codex_account.snapshot(self._poll_interval)
            # A read can take seconds, long enough for the user to switch back:
            # whichever provider is selected now owns the icon, not this one.
            if self._tray_provider != provider:
                return

            save_setting('tray_provider', provider)
            self._render_codex_tray(snapshot)
            self._check_codex_threshold_alerts(snapshot)
        elif self._last_response:
            if self._tray_provider != provider:
                return

            save_setting('tray_provider', provider)
            self._render_tray()
        else:
            self.update()
            if self._tray_provider != provider:
                return

            save_setting('tray_provider', provider)

    def _on_theme_changed(self) -> None:
        """Re-render the tray icon when the Windows theme changes."""
        light = taskbar_uses_light_theme()
        if light == self._light_taskbar:
            return

        self._light_taskbar = light
        if self._last_response:
            self._render_tray()

    # Update orchestration

    def update(self, force: bool = False, bypass_rate_limit: bool = False) -> None:
        """Request a data refresh from the cache and process the result.

        Parameters
        ----------
        force : bool
            When True, bypass the cache cooldown so the refresh happens
            immediately instead of at the next scheduled poll.
        bypass_rate_limit : bool
            When True, additionally ignore an active 429 backoff.  Used
            after a confirmed account switch, where the freshly selected
            account has no polling history that the backoff needs to
            protect.
        """
        # The tray follows Codex, so its quotas must advance on the poll beat even
        # when the Claude fetch below is still inside its cooldown and returns
        # nothing.  CodexAccount.snapshot() holds its own cooldown on the interval
        # it is handed and backs off on failure, so calling it every poll costs
        # nothing extra.
        if self._tray_provider == 'codex':
            codex_snapshot = self.codex_account.snapshot(self._poll_interval)
            self._render_codex_tray(codex_snapshot)
            self._check_codex_threshold_alerts(codex_snapshot)

        result = self.cache.update(force=force, bypass_rate_limit=bypass_rate_limit)
        if result.data is None:
            return

        self._last_response = result.data
        self._render_tray()

        # Handle CLI update notification from token refresh
        if NOTIFY_CLAUDE_UPDATE and result.token_refresh and result.token_refresh.updated:
            self.icon.notify(
                T['notify_update'].format(old=result.token_refresh.old_version, new=result.token_refresh.new_version),
                T['notify_update_title'],
            )

        if 'error' in result.data:
            return

        # The credentials token changed after this usage data was fetched: the user switched
        # accounts while the request was in flight, so the data still belongs to the previous
        # account.  Comparing it against the new account's profile would announce the switch on
        # top of the old account's numbers and consume the UUID baseline, leaving the stale data
        # in place until the next regular poll.  Keep every baseline untouched instead - for a
        # real switch the poll loop's token watcher forces an immediate refetch that reports it
        # with the new data; a same-account token rotation just resumes on the next poll.
        if result.token is not None and result.token != read_access_token():
            return

        # Detect account switch: re-fetch profile if the access token changed, then compare UUIDs.
        # When the user runs 'claude auth login', the token changes and the next profile fetch
        # returns a different account UUID, preventing a false quota-reset notification.
        self.cache.ensure_profile()
        current_profile = self.cache.profile
        current_account_uuid = (current_profile.get('account') or {}).get('uuid') if isinstance(current_profile, dict) else None

        # Unknown identity with a known baseline: the profile fetch failed
        # after a token change, so this usage data may already belong to a
        # different account.  Skip all cross-poll comparisons and keep the
        # baselines untouched; the poll where the profile is readable again
        # detects the switch (or resumes normally for the same account).
        if self._prev_account_uuid is not None and current_account_uuid is None:
            return

        if self._prev_account_uuid is not None and current_account_uuid is not None and current_account_uuid != self._prev_account_uuid:
            email = (current_profile.get('account') or {}).get('email', '')
            message = T['notify_account_switched'].format(email=email) if email else T['notify_account_switched_title']
            self._notify_or_defer('account_switched', message, T['notify_account_switched_title'])
            self._prev_utilization = {}
            self._notified_thresholds = {}
            self._prev_account_uuid = current_account_uuid
            return
        self._prev_account_uuid = current_account_uuid

        # Collect all quota fields with utilization (extra_usage has a different structure)
        quota_fields: dict[str, float] = {}
        for key, value in result.data.items():
            if key == 'extra_usage':
                continue
            if isinstance(value, dict) and 'utilization' in value:
                quota_fields[key] = value.get('utilization', 0) or 0

        # Notify when quota resets after being nearly exhausted, but only if no other quota is blocking usage.
        # While idle/locked, defer notifications until the user returns (avoids lock screen privacy concerns).
        # The message carries no field information, so several quotas resetting
        # within one polling gap still produce a single notification.
        reset_detected = False
        for key, pct in quota_fields.items():
            prev = self._prev_utilization.get(key)
            if prev is None:
                continue

            parsed = parse_field_name(key)
            if parsed is None:
                continue

            _, unit, _ = parsed
            reset_threshold = 95 if unit == 'hour' else 98
            any_blocking = any(other_pct >= 99 for other_key, other_pct in quota_fields.items() if other_key != key)

            if prev > reset_threshold and pct < prev and not any_blocking:
                reset_detected = True

        if reset_detected:
            self._notify_or_defer('reset', T['notify_reset'], T['notify_reset_title'])

        # Run reset command on any detected usage drop (independent of notification threshold)
        for key, pct in quota_fields.items():
            prev = self._prev_utilization.get(key)
            if prev is not None and pct < prev:
                self._run_reset_command(key, pct, prev, data=result.data, entry=result.data.get(key, {}))
                self._idle_reset_pending = False

        self._check_threshold_alerts(result.data)

        # Adaptive polling: speed up when icon top field usage is increasing
        icon_top_key = ICON_FIELDS[0].split(':', 1)[0]
        icon_top_pct = quota_fields.get(icon_top_key, 0)
        icon_top_prev = self._prev_utilization.get(icon_top_key)
        if icon_top_prev is not None and icon_top_pct > icon_top_prev:
            self._fast_polls_remaining = POLL_FAST_EXTRA + 1
        elif self._fast_polls_remaining > 0:
            self._fast_polls_remaining -= 1

        self._prev_utilization = quota_fields

        if not self._first_update_done:
            self._run_startup_command(result.data)

        self._first_update_done = True

    # Notifications

    def _notify_or_defer(self, category: str, message: str, title: str) -> None:
        """Show a notification immediately, or defer it if the user is away.

        Parameters
        ----------
        category : str
            Deduplication key (e.g. ``'reset'``, ``'threshold_five_hour'``).
            While deferred, only the latest notification per category is
            kept so the user does not get a flood on return.
        message : str
            Notification body text.
        title : str
            Notification title.
        """
        if self._is_user_away():
            with self._notify_lock:
                self._deferred_notifications[category] = (message, title)
        else:
            self.icon.notify(message, title)

    def _flush_deferred_notifications(self) -> None:
        """Show all deferred notifications and clear the queue.

        The queue is swapped out under the lock so a deferral landing
        mid-flush (from the popup thread) is kept for the next flush
        instead of mutating the dict being iterated.
        """
        with self._notify_lock:
            pending, self._deferred_notifications = self._deferred_notifications, {}
        for message, title in pending.values():
            self.icon.notify(message, title)

    def _check_codex_threshold_alerts(self, snapshot: dict[str, Any]) -> None:
        """Run the threshold alerts against the Codex quota windows.

        Codex windows carry their length in ``seconds`` instead of encoding it
        in the field name, so the period and the label are passed in rather
        than derived from the key.  Everything else - which threshold was last
        notified, the time-aware suppression, the reset on a usage drop - is
        the shared machinery, so both providers behave identically.
        """
        windows = snapshot.get('windows') or []
        data = {
            window['key']: {'utilization': window['used'], 'resets_at': codex_reset_iso(window['resets_at'])}
            for window in windows
        }
        periods = {window['key']: window['seconds'] for window in windows}

        self._check_threshold_alerts(data, periods=periods)

    def _check_threshold_alerts(self, data: dict[str, Any], periods: dict[str, int] | None = None) -> None:
        """Show a notification when usage crosses a configured threshold.

        Dynamically detects all quota fields in the API response.  For
        each field, finds the highest threshold exceeded by current
        utilization.  If it exceeds a threshold not yet notified, shows a
        single notification with the current usage percentage.  When usage
        drops (e.g. after reset), tracking resets so thresholds can
        re-trigger in the next cycle.

        Parameters
        ----------
        data : dict
            Quota entries keyed by field, each with ``utilization`` and
            ``resets_at``.
        periods : dict or None
            Window length in seconds per field, for quotas that do not encode
            it in their name (Codex).  None means derive both the period and
            the label from the field name, which is what Claude fields do.
        """
        for variant_key, entry in data.items():
            if variant_key == 'extra_usage':
                continue
            if not isinstance(entry, dict) or entry.get('utilization') is None:
                continue

            pct = entry['utilization']
            thresholds = get_alert_thresholds(variant_key)
            if not thresholds:
                continue

            exceeded = [t for t in thresholds if pct >= t]
            highest_exceeded = max(exceeded) if exceeded else 0
            last_notified = self._notified_thresholds.get(variant_key, 0)

            if ALERT_TIME_AWARE and highest_exceeded > last_notified and highest_exceeded < ALERT_TIME_AWARE_BELOW:
                period = periods.get(variant_key) if periods is not None else field_period(variant_key)
                if period:
                    time_pct = elapsed_pct(entry.get('resets_at'), period)
                    if time_pct is not None and pct <= time_pct:
                        self._notified_thresholds[variant_key] = highest_exceeded
                        continue

            if highest_exceeded > last_notified:
                title = T['notify_threshold_title']
                label = duration_label(periods[variant_key]) if periods is not None else popup_label(variant_key)
                message = T['notify_threshold_generic'].format(label=label, pct=f'{pct:.0f}')
                self._notify_or_defer(f'threshold_{variant_key}', message, title)
                self._run_threshold_command(variant_key, pct, highest_exceeded, entry, title, message)
                self._notified_thresholds[variant_key] = highest_exceeded
            elif highest_exceeded < last_notified:
                self._notified_thresholds[variant_key] = highest_exceeded

        if periods is None:
            self._check_extra_usage_alerts(data)

    def _check_extra_usage_alerts(self, data: dict[str, Any]) -> None:
        """Show a notification when extra usage crosses a configured threshold.

        Extra usage has a different data format (``used_credits`` /
        ``monthly_limit``) and no time-based reset, so it is handled
        separately from the sliding-window quotas.
        """
        extra = data.get('extra_usage')
        if not extra or not extra.get('is_enabled'):
            return

        used = extra.get('used_credits', 0) or 0
        currency = extra.get('currency')
        decimal_places = extra.get('decimal_places')
        used_text = format_credits(used, currency, decimal_places)

        limit = extra.get('monthly_limit', 0) or 0
        if limit > 0:
            pct = used / limit * 100
            thresholds = get_alert_thresholds('extra_usage')
            exceeded = [t for t in thresholds if pct >= t]
            highest_exceeded = max(exceeded) if exceeded else 0
            last_notified = self._notified_thresholds.get('extra_usage', 0)

            if highest_exceeded > last_notified:
                title = T['notify_threshold_title']
                limit_text = format_credits(limit, currency, decimal_places)
                message = T['notify_threshold_extra_usage'].format(
                    pct=f'{pct:.0f}', used=used_text, limit=limit_text,
                )
                self._notify_or_defer('threshold_extra_usage', message, title)
                self._run_threshold_command(
                    'extra_usage', pct, highest_exceeded, extra, title, message,
                    extra_used=used_text, extra_limit=limit_text,
                )
                self._notified_thresholds['extra_usage'] = highest_exceeded
            elif highest_exceeded < last_notified:
                self._notified_thresholds['extra_usage'] = highest_exceeded

        self._check_extra_usage_spent_alerts(extra, used, used_text)

    def _check_extra_usage_spent_alerts(self, extra: dict[str, Any], used: float, used_text: str) -> None:
        """Show a notification when extra-usage spending crosses a configured amount.

        Amounts in ``ALERT_EXTRA_USAGE_SPENT`` are absolute major-unit values
        (e.g. dollars), so they also work for accounts whose extra usage has
        no monthly limit and can never produce a percentage.
        """
        if not ALERT_EXTRA_USAGE_SPENT:
            return

        decimal_places = extra.get('decimal_places')
        places = decimal_places if decimal_places is not None else 2
        spent = used / (10 ** places)

        exceeded = [amount for amount in ALERT_EXTRA_USAGE_SPENT if spent >= amount]
        highest_exceeded = max(exceeded) if exceeded else 0
        last_notified = self._notified_thresholds.get('extra_usage_spent', 0)

        if highest_exceeded > last_notified:
            title = T['notify_threshold_title']
            message = T['notify_threshold_extra_usage_spent'].format(used=used_text)
            self._notify_or_defer('threshold_extra_usage_spent', message, title)
            self._run_threshold_command(
                'extra_usage_spent', None, highest_exceeded, extra, title, message,
                extra_used=used_text,
            )
            self._notified_thresholds['extra_usage_spent'] = highest_exceeded
        elif highest_exceeded < last_notified:
            self._notified_thresholds['extra_usage_spent'] = highest_exceeded

    # Event commands
    #
    # Each of these is the same shape: the setting decides whether anything
    # runs, `events` builds what the command is told, and the runner is called
    # here.  Keeping the settings and the runner on this side is what lets the
    # environment assembly stay pure and separately readable.

    def _run_startup_command(self, data: dict[str, Any]) -> None:
        """Run the startup command once the first update has landed."""
        if not ON_STARTUP_COMMAND:
            return

        run_event_command(ON_STARTUP_COMMAND, startup_env(data))

    def _run_double_click_command(self) -> None:
        """Run the quick action against the latest quota state.

        A quick action is user-driven, so a command that exits non-zero
        surfaces its stderr in an error dialog (``capture_output``) instead of
        failing silently - unlike the automatic reset, threshold and startup
        commands.  It typically starts a program the user then keeps open, so a
        non-zero exit long afterwards is that program's own business rather
        than a wrong path (``report_late_failures=False``).
        """
        if not QUICK_ACTION_COMMAND:
            return

        run_event_command(QUICK_ACTION_COMMAND, quick_action_env(self._last_response),
                          capture_output=True, report_late_failures=False)

    def _run_reset_command(
        self, variant: str, pct: float, prev_pct: float, *, data: dict[str, Any], entry: dict[str, Any],
    ) -> None:
        """Run the reset command for a quota that just reset."""
        if not ON_RESET_COMMAND:
            return

        run_event_command(ON_RESET_COMMAND, reset_env(variant, pct, prev_pct, data, entry))

    def _run_threshold_command(
        self, variant: str, pct: float | None, threshold: float,
        entry: dict[str, Any], title: str, message: str,
        *, extra_used: str = '', extra_limit: str = '',
    ) -> None:
        """Run the threshold command, unless this is still the first update.

        Skipped before ``_first_update_done`` so thresholds already exceeded
        when the app starts do not fire commands.  The notification still goes
        out - commands react to *events*, not to *state*.
        """
        if not ON_THRESHOLD_COMMAND or not self._first_update_done:
            return

        env_vars = threshold_env(variant, pct, threshold, entry, title, message,
                                 extra_used=extra_used, extra_limit=extra_limit)
        run_event_command(ON_THRESHOLD_COMMAND, env_vars)

    # Polling

    def _seconds_until_next_reset(self) -> float | None:
        """Return seconds until the earliest upcoming quota reset, or None."""
        return earliest_reset(self._tracked_reset_times(), datetime.now(timezone.utc))

    def _tracked_reset_times(self) -> list[str]:
        """ISO reset times of every quota this poll actually fetches.

        The Codex windows are handed over only while the tray follows Codex,
        because ``update()`` reads them on the same beat only then.  They come
        from the cached snapshot: the scheduler must never start an
        app-server read to decide how long to wait.
        """
        codex_windows = self.codex_account.cached.get('windows') if self._tray_provider == 'codex' else None

        return tracked_reset_times(self._last_response, codex_windows, codex_reset_iso)

    def _account_switched(self) -> bool:
        """Return whether the current credentials belong to a different account.

        Probes the account profile with the token now in the credentials
        file (bypassing the 429 backoff, since a freshly selected account
        cannot be the source of that rate limit) and compares its UUID
        against the last seen one.  Returns False until a baseline UUID is
        known, so the first successful update is never taken for a switch.
        """
        if self._prev_account_uuid is None:
            return False

        self.cache.ensure_profile(bypass_rate_limit=True)
        profile = self.cache.profile
        current_uuid = (profile.get('account') or {}).get('uuid') if isinstance(profile, dict) else None

        return current_uuid is not None and current_uuid != self._prev_account_uuid

    def _reset_aligned_poll_target(self, next_reset: float) -> float:
        """Absolute time for a poll landing just after a reset.

        Parameters
        ----------
        next_reset : float
            Seconds until the upcoming reset.
        """
        return reset_aligned_target(next_reset, self.cache.last_success_time, time.time(), POLL_FAST, RESET_BUFFER)

    def _clamp_target_to_reset(self, target: float) -> float:
        """Pull a poll target back to the reset-aligned slot when it would overshoot.

        Parameters
        ----------
        target : float
            Absolute time the poll is currently scheduled for.
        """
        return clamp_to_reset(target, self._seconds_until_next_reset(), self.cache.last_success_time,
                              time.time(), POLL_FAST, RESET_BUFFER)

    def _calculate_poll_interval(self) -> int:
        """Determine the next poll interval based on current state.

        Returns
        -------
        int
            Seconds to wait before the next poll.
        """
        data = self._last_response

        if data.get('rate_limited'):
            remaining = self.cache.rate_limit_remaining
            interval = max(math.ceil(remaining), self._poll_interval) if remaining > 0 else self._poll_interval
        elif 'error' in data:
            interval = POLL_ERROR
        elif self._fast_polls_remaining > 0:
            interval = POLL_FAST
        else:
            interval = self._poll_interval

        # Align the next poll around an imminent reset for faster feedback.
        # The confirming poll is placed just after the reset; a follow-up uses
        # POLL_FAST regardless of user activity (quota was likely exhausted).
        next_reset = self._seconds_until_next_reset()
        interval, aligned = _align_to_reset(interval, next_reset)
        if aligned:
            self._fast_polls_remaining = max(self._fast_polls_remaining, 2)

        return interval

    def _is_user_away(self) -> bool:
        """Return True if the user is idle or the workstation is locked.

        Used only to defer notifications until the user is back.  Whether
        polling runs is a separate question, answered by ``_polling_paused``.
        """
        if is_workstation_locked():
            return True
        return IDLE_PAUSE > 0 and get_idle_seconds() >= IDLE_PAUSE

    def _polling_paused(self) -> bool:
        """Return whether polling is paused because nothing is on screen.

        An open popup - pinned or not - is the one view that needs live
        numbers, so polling follows it: it runs while the popup is up and for
        ``IDLE_PAUSE`` seconds after it closes, then stops until the popup is
        opened again.  ``idle_pause = 0`` disables the pause entirely.

        Deliberately independent of ``_is_user_away()``: this is about what
        the app is showing, not where the user is.
        """
        if self._popup_open or IDLE_PAUSE <= 0:
            return False

        return time.time() - self._popup_closed_at >= IDLE_PAUSE

    def _wait_for_popup(self, until: float | None = None) -> None:
        """Block until the popup is opened again or the app is stopping.

        Parameters
        ----------
        until : float | None
            Optional deadline (``time.time()`` epoch).  When set, the wait
            ends even with the popup still closed, so a time-critical poll
            (the quota-reset command) can still fire on time.
        """
        while self.running and self._polling_paused():
            if until is not None and time.time() >= until:
                break
            time.sleep(2)

    def poll_loop(self) -> None:
        """Poll the API in a loop with adaptive intervals.

        Polling tracks the popup: it runs while the popup is open and for
        ``IDLE_PAUSE`` seconds after it closes, then pauses until the popup
        is opened again.  User idle time and lock state do not pause it -
        they only defer notifications (see ``_notify_or_defer``).
        """
        self.cache.ensure_profile()
        force_next = False
        while self.running:
            # Read before the update, not after: an account switch that lands while the
            # request is in flight would otherwise already be part of the token read
            # afterwards and never register as a change - leaving the previous account's
            # usage on screen until the next regular poll.
            token_seen = read_access_token()
            self.update(force=force_next, bypass_rate_limit=force_next)
            force_next = False
            interval = self._calculate_poll_interval()

            # Only a wait that is running out the chosen cadence follows a menu
            # change.  An error retry, a fast poll or a reset-aligned slot keeps
            # the timing it was given: those answer a state of the data, not a
            # preference about how often to look.
            cadence_wait = interval == self._poll_interval

            target = time.time() + interval
            self._next_poll_time = target
            last_success_seen = self.cache.last_success_time
            while self.running and time.time() < target:
                time.sleep(1)

                # React to a credentials token change between polls. A switch to
                # a different account forces an immediate refresh (bypassing the
                # cooldown) so the new account's usage shows right away. A token
                # change while the last fetch failed auth is retried at once so a
                # freshly refreshed token recovers usage and profile without
                # waiting out the error cadence or needing a restart.
                current_token = read_access_token()
                if current_token and current_token != token_seen:
                    token_seen = current_token
                    if self._account_switched():
                        force_next = True
                        break
                    if self._last_response.get('auth_error'):
                        break

                # The tray menu can change the refresh interval mid-wait.  Re-anchor
                # the target on the new value so a shorter choice takes effect at
                # once instead of only after the old, longer wait has run out.
                if cadence_wait and self._poll_interval != interval:
                    interval = self._poll_interval
                    last = self.cache.last_success_time
                    anchor = last if last is not None else time.time() - interval
                    target = self._clamp_target_to_reset(anchor + interval)
                    self._next_poll_time = target

                # Re-anchor the wait target after a backward clock jump -
                # otherwise the poll would stall until the wall clock catches
                # up with the pre-jump target, potentially for hours.  The
                # bound leaves room for reset-aligned targets, which may lie
                # up to roughly POLL_FAST past a normal interval.
                if target - time.time() > interval + POLL_FAST:
                    target = time.time() + interval
                    self._next_poll_time = target

                # If another thread (popup) fetched successfully, push the next
                # poll a full interval past that fetch to avoid a redundant one.
                # Only react to an actual new fetch (last_success advanced).
                lst = self.cache.last_success_time
                if lst is not None and (last_success_seen is None or lst > last_success_seen):
                    last_success_seen = lst
                    # Never let that push move the poll past a reset-aligned slot
                    # nor into the danger window before the reset.
                    target = self._clamp_target_to_reset(max(target, lst + interval))
                    self._next_poll_time = target

                # Show notifications deferred while the user was away as soon
                # as they are present.
                if self._deferred_notifications and not self._is_user_away():
                    self._flush_deferred_notifications()

                # Pause polling once the popup has been closed for IDLE_PAUSE
                # seconds - no view is left that needs live numbers.  The one
                # exception: with on_reset_command configured the pause is
                # interrupted at the reset so the command still fires on time.
                # _idle_reset_pending keeps polling until the reset is actually
                # confirmed (a usage drop), which covers server-side delay and
                # transient network errors.  It is cleared by update() on that
                # drop, not on return, so a popup closed again before the
                # confirmation resumes the reset wake-up.
                if self._polling_paused():
                    reset_deadline = None
                    if ON_RESET_COMMAND:
                        next_reset = self._seconds_until_next_reset()
                        if next_reset is not None:
                            reset_deadline = time.time() + next_reset + RESET_BUFFER
                            self._idle_reset_pending = True
                        elif self._idle_reset_pending:
                            reset_deadline = time.time() + self._poll_interval

                    self._wait_for_popup(until=reset_deadline)

                    if reset_deadline is not None and self._polling_paused():
                        # Woke for the reset with the popup still closed - poll once.
                        break

                    self._flush_deferred_notifications()
                    lst = self.cache.last_success_time
                    if lst is None:
                        continue

                    next_reset = self._seconds_until_next_reset()
                    if next_reset is not None and next_reset < POLL_FAST:
                        # Back within the cooldown window before a reset: polling
                        # now would advance last_success into that window and force
                        # the confirming poll to overshoot.  Realign the wait to
                        # just after the reset and keep waiting for it.
                        target = self._reset_aligned_poll_target(next_reset)
                        self._next_poll_time = target
                        continue

                    if time.time() - lst >= interval:
                        break

    # Lifecycle

    def _on_icon_ready(self, icon: Any) -> None:
        """Called by pystray in a separate thread once the tray icon is set up."""
        try:
            icon.visible = True
            if getattr(sys, 'frozen', False):
                sync_autostart_path()
            if not api_headers():
                icon.notify(f"{T['warn_no_token']}\n{T['warn_login']}", T['app_name'])
            threading.Thread(target=watch_theme_change, args=(self._on_theme_changed,), daemon=True).start()
            self.poll_loop()
        except Exception:
            crash_log(traceback.format_exc())

    def run(self) -> None:
        self.icon.run(setup=self._on_icon_ready)


def crash_log(msg: str) -> None:
    """Show a crash message box (for windowless EXE builds)."""
    ctypes.windll.user32.MessageBoxW(0, msg[:2000], 'AI Agents Usage Monitor - Error', 0x10)
