"""
Event Command Environments
===========================

Translate quota state into the environment variables each event command
receives, and supply the samples the tray menu's test entries send.  Every
function here only builds a dict: which command is configured, whether the
event should fire at all, and the call to the runner all stay with the
caller, so this module can be read as the answer to one question - what does a
command get told about what happened.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .formatting import format_credits, is_active_quota, popup_label
from .i18n import T

__all__ = [
    'quick_action_env', 'quota_snapshot_env', 'reset_env', 'sample_quick_action_env', 'sample_reset_env',
    'sample_startup_env', 'sample_threshold_env', 'startup_env', 'threshold_env',
]


def quota_snapshot_env(data: dict[str, Any]) -> dict[str, str]:
    """Build environment variables describing the current quota state.

    Emits one ``USAGE_MONITOR_UTILIZATION_<FIELD>`` /
    ``USAGE_MONITOR_RESETS_AT_<FIELD>`` pair per quota field that applies to
    the account - a quota the API only announces, or reports without a
    utilization, is left out rather than reported as 0% - plus
    ``USAGE_MONITOR_EXTRA_USED`` when paid extra usage is enabled and
    ``USAGE_MONITOR_EXTRA_LIMIT`` when it also has a monthly limit (an
    uncapped account has no limit to report).  Shared by the startup and
    quick-action environments.

    Parameters
    ----------
    data : dict
        A successful usage response.
    """
    env_vars: dict[str, str] = {}
    for key, entry in data.items():
        if key == 'extra_usage' or not is_active_quota(key, entry):
            continue
        env_vars[f'USAGE_MONITOR_UTILIZATION_{key.upper()}'] = str(round(entry['utilization']))
        env_vars[f'USAGE_MONITOR_RESETS_AT_{key.upper()}'] = entry.get('resets_at') or ''

    extra = data.get('extra_usage') or {}
    if extra.get('is_enabled'):
        limit = extra.get('monthly_limit', 0) or 0
        used = extra.get('used_credits', 0) or 0
        currency = extra.get('currency')
        decimal_places = extra.get('decimal_places')
        env_vars['USAGE_MONITOR_EXTRA_USED'] = format_credits(used, currency, decimal_places)
        if limit > 0:
            env_vars['USAGE_MONITOR_EXTRA_LIMIT'] = format_credits(limit, currency, decimal_places)

    return env_vars


def startup_env(data: dict[str, Any]) -> dict[str, str]:
    """Environment for the startup command, which sees the full quota state."""
    return {'USAGE_MONITOR_EVENT': 'startup', **quota_snapshot_env(data)}


def quick_action_env(data: dict[str, Any]) -> dict[str, str]:
    """Environment for the quick action, mirroring the startup command's."""
    return {'USAGE_MONITOR_EVENT': 'quick_action', **quota_snapshot_env(data)}


def reset_env(variant: str, pct: float, prev_pct: float, data: dict[str, Any], entry: dict[str, Any]) -> dict[str, str]:
    """Environment for the reset command.

    Parameters
    ----------
    variant : str
        The quota field that reset.
    pct : float
        Utilization after the reset.
    prev_pct : float
        Utilization before it.
    data : dict
        The full quota state, read for the two summary variables.
    entry : dict
        The field's own entry, read for its next reset time.
    """
    pct_5h = (data.get('five_hour') or {}).get('utilization', 0) or 0
    pct_7d = (data.get('seven_day') or {}).get('utilization', 0) or 0

    return {
        'USAGE_MONITOR_EVENT': 'reset',
        'USAGE_MONITOR_VARIANT': variant,
        'USAGE_MONITOR_UTILIZATION': str(round(pct)),
        'USAGE_MONITOR_PREV_UTILIZATION': str(round(prev_pct)),
        'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': str(round(pct_5h)),
        'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': str(round(pct_7d)),
        'USAGE_MONITOR_RESETS_AT': entry.get('resets_at') or '',
        'USAGE_MONITOR_TITLE': T['notify_reset_title'],
        'USAGE_MONITOR_MESSAGE': T['notify_reset'],
    }


def threshold_env(
    variant: str, pct: float | None, threshold: float,
    entry: dict[str, Any], title: str, message: str,
    *, extra_used: str = '', extra_limit: str = '',
) -> dict[str, str]:
    """Environment for the threshold command.

    ``pct`` is None for spend-amount alerts, which have no utilization
    percentage; ``USAGE_MONITOR_UTILIZATION`` is omitted in that case.

    Parameters
    ----------
    variant : str
        The quota field that crossed the threshold.
    pct : float or None
        Current utilization, or None for a spend-amount alert.
    threshold : float
        The threshold that was crossed.
    entry : dict
        The field's own entry, read for its reset time.
    title : str
        Notification title, passed through to the command.
    message : str
        Notification body, passed through to the command.
    extra_used : str
        Formatted extra-usage spend, when the alert is about extra usage.
    extra_limit : str
        Formatted extra-usage limit, when the account has one.
    """
    env_vars = {
        'USAGE_MONITOR_EVENT': 'threshold',
        'USAGE_MONITOR_VARIANT': variant,
    }
    if pct is not None:
        env_vars['USAGE_MONITOR_UTILIZATION'] = str(round(pct))
    env_vars.update({
        'USAGE_MONITOR_THRESHOLD': str(round(threshold)),
        'USAGE_MONITOR_RESETS_AT': entry.get('resets_at') or '',
        'USAGE_MONITOR_TITLE': title,
        'USAGE_MONITOR_MESSAGE': message,
    })
    if extra_used:
        env_vars['USAGE_MONITOR_EXTRA_USED'] = extra_used
    if extra_limit:
        env_vars['USAGE_MONITOR_EXTRA_LIMIT'] = extra_limit

    return env_vars


# The "Test event commands" tray menu fires each command with a sample below:
# plausible values under the same variable names the real event sets, so a
# script can be checked against what it will actually be told.

def sample_reset_env(variant: str) -> dict[str, str]:
    """Sample environment for a reset of the session or the weekly quota.

    Parameters
    ----------
    variant : str
        ``'five_hour'`` or ``'seven_day'`` - the quota the sample reports as reset.
    """
    assert variant in ('five_hour', 'seven_day')

    if variant == 'five_hour':
        prev_pct, five_hour_pct, seven_day_pct, resets_at = '95', '0', '45', _future_iso(hours=5)
    else:
        prev_pct, five_hour_pct, seven_day_pct, resets_at = '99', '12', '0', _future_iso(days=7)

    return {
        'USAGE_MONITOR_EVENT': 'reset',
        'USAGE_MONITOR_VARIANT': variant,
        'USAGE_MONITOR_UTILIZATION': '0',
        'USAGE_MONITOR_PREV_UTILIZATION': prev_pct,
        'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': five_hour_pct,
        'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': seven_day_pct,
        'USAGE_MONITOR_RESETS_AT': resets_at,
        'USAGE_MONITOR_TITLE': T['notify_reset_title'],
        'USAGE_MONITOR_MESSAGE': T['notify_reset'],
    }


def sample_threshold_env(variant: str) -> dict[str, str]:
    """Sample environment for the session or the weekly quota crossing 80%.

    Parameters
    ----------
    variant : str
        ``'five_hour'`` or ``'seven_day'`` - the quota the sample reports.
    """
    assert variant in ('five_hour', 'seven_day')

    pct, resets_at = ('82', _future_iso(hours=3)) if variant == 'five_hour' else ('81', _future_iso(days=4))

    return {
        'USAGE_MONITOR_EVENT': 'threshold',
        'USAGE_MONITOR_VARIANT': variant,
        'USAGE_MONITOR_UTILIZATION': pct,
        'USAGE_MONITOR_THRESHOLD': '80',
        'USAGE_MONITOR_RESETS_AT': resets_at,
        'USAGE_MONITOR_TITLE': T['notify_threshold_title'],
        'USAGE_MONITOR_MESSAGE': T['notify_threshold_generic'].format(label=popup_label(variant), pct=pct),
    }


def sample_startup_env() -> dict[str, str]:
    """Sample environment for the startup command: a fresh session beside a partly used week."""
    return {
        'USAGE_MONITOR_EVENT': 'startup',
        'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '0',
        'USAGE_MONITOR_RESETS_AT_FIVE_HOUR': '',
        'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '45',
        'USAGE_MONITOR_RESETS_AT_SEVEN_DAY': _future_iso(days=3),
    }


def sample_quick_action_env() -> dict[str, str]:
    """Sample environment for the quick action, shaped like the startup command's."""
    return {
        'USAGE_MONITOR_EVENT': 'quick_action',
        'USAGE_MONITOR_UTILIZATION_FIVE_HOUR': '30',
        'USAGE_MONITOR_RESETS_AT_FIVE_HOUR': _future_iso(hours=3),
        'USAGE_MONITOR_UTILIZATION_SEVEN_DAY': '55',
        'USAGE_MONITOR_RESETS_AT_SEVEN_DAY': _future_iso(days=4),
    }


def _future_iso(**offset: float) -> str:
    """Return an ISO 8601 timestamp offset from now by the given ``timedelta`` arguments."""
    return (datetime.now(timezone.utc) + timedelta(**offset)).isoformat()
