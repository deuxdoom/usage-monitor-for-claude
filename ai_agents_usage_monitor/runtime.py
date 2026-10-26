"""
Application Runtime
===================

Identify the portable launcher separately from its private Python process.
"""
from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path

__all__ = ['application_executable', 'application_pid', 'external_environment', 'hold_runtime_lease']


def hold_runtime_lease() -> None:
    """Keep this runtime marked active even if only the outer launcher is terminated."""
    lease_path = os.environ.get('AI_AGENTS_USAGE_MONITOR_LEASE') if getattr(sys, 'frozen', False) else None
    if lease_path:
        lease = Path(lease_path).open('rb')
        atexit.register(lease.close)


def application_executable() -> Path:
    """Return the public EXE whose folder owns settings and automatic startup."""
    launcher = os.environ.get('AI_AGENTS_USAGE_MONITOR_EXE') if getattr(sys, 'frozen', False) else None
    return Path(launcher or sys.executable)


def application_pid() -> int:
    """Return the launcher PID that must exit before the public EXE can be replaced."""
    launcher_pid = os.environ.get('AI_AGENTS_USAGE_MONITOR_PID') if getattr(sys, 'frozen', False) else None
    return int(launcher_pid) if launcher_pid else os.getpid()


def external_environment() -> dict[str, str]:
    """Keep user-launched programs independent of this application's temporary directory."""
    env = dict(os.environ)
    for key in ('TEMP', 'TMP'):
        original = env.get('AI_AGENTS_USAGE_MONITOR_ORIGINAL_' + key)
        if original is not None:
            if original:
                env[key] = original
            else:
                env.pop(key, None)
    return {key: value for key, value in env.items() if not key.startswith('AI_AGENTS_USAGE_MONITOR_')}
