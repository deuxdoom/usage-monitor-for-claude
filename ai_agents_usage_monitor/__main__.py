"""Entry point for ``python -m ai_agents_usage_monitor``."""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import traceback
from pathlib import Path

# The copied helper must bypass configuration, single-instance and tray startup.
if len(sys.argv) > 1 and sys.argv[1] == '--apply-update':
    from ai_agents_usage_monitor.updater import run_update_helper

    sys.exit(run_update_helper(*sys.argv[2:]) if len(sys.argv) == 6 else 2)

from ai_agents_usage_monitor.instance_id import parse_config_dir

_verbose = '--verbose' in sys.argv

# --config-dir selects which Claude account to monitor. It must be
# resolved into CLAUDE_CONFIG_DIR before any other package import:
# api, settings, verbose and i18n all read the variable at import or
# first-use time. Keep every other package import below this block.
_config_dir = parse_config_dir(sys.argv)
if _config_dir is not None:
    _config_path = Path(_config_dir)
    if not _config_path.is_dir():
        ctypes.windll.user32.MessageBoxW(
            0, f'--config-dir directory does not exist:\n{_config_dir}',
            'AI Agents Usage Monitor - Error', 0x10,
        )
        sys.exit(1)
    os.environ['CLAUDE_CONFIG_DIR'] = str(_config_path.resolve())

# In frozen builds (console=False), stdout/stderr go nowhere.
# --verbose attaches a console so diagnostics are visible.
if _verbose and getattr(sys, 'frozen', False):
    from ai_agents_usage_monitor.verbose import setup_console
    setup_console()

# Per-Monitor V2 must be set before pywebview's legacy SetProcessDPIAware() call,
# which only sets SYSTEM_DPI_AWARE and breaks native menu hover at high DPI.
# The API exists only from Windows 10 1703; ctypes raises AttributeError for a
# missing export, which must not kill startup - pywebview's legacy call is the
# fallback on older systems.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))
except AttributeError:
    pass

if _verbose:
    from ai_agents_usage_monitor.verbose import print_startup_diagnostics
    print_startup_diagnostics()

import webview  # type: ignore[import-untyped]  # no type stubs available

from ai_agents_usage_monitor.app import AIAgentsUsageMonitor, crash_log
from ai_agents_usage_monitor.notification_identity import register_notification_identity
from ai_agents_usage_monitor.single_instance import ensure_single_instance
from ai_agents_usage_monitor.updater import check_and_offer_update

if _verbose:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-5s %(name)s: %(message)s',
        datefmt='%H:%M:%S',
    )


def _verbose_step(label: str) -> None:
    """Print a startup progress step in verbose mode."""
    if _verbose:
        print(f'  [startup] {label}', flush=True)


def _run_app() -> None:
    """Run the tray application in a background thread (called by webview)."""
    try:
        if _verbose:
            from ai_agents_usage_monitor.verbose import print_runtime_diagnostics
            print_runtime_diagnostics()

        _verbose_step('AIAgentsUsageMonitor()...')
        app = AIAgentsUsageMonitor()
        _verbose_step('AIAgentsUsageMonitor()... OK')

        threading.Thread(target=check_and_offer_update, args=(app,), daemon=True).start()

        _verbose_step('app.run...')
        app.run()
    except Exception:
        _verbose_step(f'CRASH: {traceback.format_exc()}')
        crash_log(traceback.format_exc())
    finally:
        # Destroy all webview windows (keeper + any open popups) so
        # webview.start() on the main thread returns.
        for win in list(webview.windows):
            try:
                win.destroy()
            except Exception:
                pass


try:
    _verbose_step('ensure_single_instance...')
    if not ensure_single_instance():
        _verbose_step('another instance is running, exiting')
        sys.exit(0)
    _verbose_step('ensure_single_instance... OK')

    # Give notifications a fixed logo instead of the live tray icon.
    # Must run before any window is created (AppUserModelID requirement).
    _verbose_step('register_notification_identity...')
    register_notification_identity()

    # pywebview requires the main thread for its GUI event loop.
    # A persistent hidden window keeps the loop alive while the
    # tray app and popup windows are managed in background threads.
    _verbose_step('webview.create_window...')
    webview.create_window('', html='', hidden=True)
    _verbose_step('webview.create_window... OK')

    _verbose_step('webview.start...')
    webview.start(func=_run_app)
    _verbose_step('webview.start returned')
except Exception:
    crash_log(traceback.format_exc())
