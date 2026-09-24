"""
Tray Menu
==========

Build the tray icon's context menu.  The whole menu is here in one piece so its
shape - the heading, which item a left click fires, what is hidden rather than
greyed out - can be read without the rest of the app around it.

The monitor is passed in whole rather than as a list of callbacks: the radio
items have to read its current choice on every open, so the menu needs the live
object, not a snapshot of it.
"""
from __future__ import annotations

import sys
from typing import Any

import pystray  # type: ignore[import-untyped]  # no type stubs available

from .autostart import is_autostart_enabled
from .i18n import T
from .settings import ON_RESET_COMMAND, ON_STARTUP_COMMAND, ON_THRESHOLD_COMMAND, QUICK_ACTION_COMMAND

__all__ = ['build_menu']


def build_menu(monitor: Any) -> pystray.Menu:
    """Assemble the tray context menu for a monitor instance.

    Parameters
    ----------
    monitor : AIAgentsUsageMonitor
        The running monitor, read for its menu handlers and for the current
        tray provider, refresh interval and popup font the radio items check
        against.
    """
    return pystray.Menu(
        # Names the app at the top of the menu. Disabled so it reads as a
        # heading and cannot be clicked, and without an action so it stays
        # inert; `default` remains on "show usage", which is what a left
        # click on the tray icon has to keep firing.
        pystray.MenuItem(T['app_name'], None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(T['menu_show'], monitor.on_show_popup, default=True),
        pystray.Menu.SEPARATOR,
        # The agent names are product names and read the same in every
        # language, exactly as the popup's own switch shows them, so
        # they are written out instead of going through a locale key.
        pystray.MenuItem(T['menu_tray_provider'], pystray.Menu(
            pystray.MenuItem(
                'Claude', monitor.on_tray_claude,
                checked=lambda item: monitor._tray_provider == 'claude', radio=True,
            ),
            pystray.MenuItem(
                'Codex', monitor.on_tray_codex,
                checked=lambda item: monitor._tray_provider == 'codex', radio=True,
            ),
        )),
        pystray.MenuItem(T['menu_refresh_interval'], pystray.Menu(
            pystray.MenuItem(
                T['refresh_minutes'].format(n=1), monitor.on_refresh_1min,
                checked=lambda item: monitor._poll_interval == 60, radio=True,
            ),
            pystray.MenuItem(
                T['refresh_minutes'].format(n=3), monitor.on_refresh_3min,
                checked=lambda item: monitor._poll_interval == 180, radio=True,
            ),
            pystray.MenuItem(
                T['refresh_minutes'].format(n=5), monitor.on_refresh_5min,
                checked=lambda item: monitor._poll_interval == 300, radio=True,
            ),
        )),
        pystray.MenuItem(T['menu_font'], pystray.Menu(
            pystray.MenuItem(
                T['font_system'], monitor.on_font_system,
                checked=lambda item: monitor._popup_font == 'system', radio=True,
            ),
            pystray.MenuItem(
                T['font_pretendard'], monitor.on_font_pretendard,
                checked=lambda item: monitor._popup_font == 'pretendard', radio=True,
            ),
        )),
        pystray.MenuItem(
            T['autostart'], monitor.on_toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
            visible=getattr(sys, 'frozen', False),
        ),
        pystray.MenuItem(T['test_commands'], pystray.Menu(
            pystray.MenuItem(T['test_reset_5h'], monitor.on_test_reset_5h, enabled=bool(ON_RESET_COMMAND)),
            pystray.MenuItem(T['test_reset_7d'], monitor.on_test_reset_7d, enabled=bool(ON_RESET_COMMAND)),
            pystray.MenuItem(T['test_threshold_5h'], monitor.on_test_threshold_5h, enabled=bool(ON_THRESHOLD_COMMAND)),
            pystray.MenuItem(T['test_threshold_7d'], monitor.on_test_threshold_7d, enabled=bool(ON_THRESHOLD_COMMAND)),
            pystray.MenuItem(T['test_startup'], monitor.on_test_startup, enabled=bool(ON_STARTUP_COMMAND)),
            pystray.MenuItem(T['test_quick_action'], monitor.on_test_quick_action, enabled=bool(QUICK_ACTION_COMMAND)),
        # Hidden rather than greyed out when no event command is
        # configured: for the majority of users the submenu can never
        # do anything, so it is only clutter in the context menu.
        ), visible=bool(ON_RESET_COMMAND or ON_STARTUP_COMMAND or ON_THRESHOLD_COMMAND or QUICK_ACTION_COMMAND)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(T['menu_project'], monitor.on_open_project),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(T['quit'], monitor.on_quit),
    )
