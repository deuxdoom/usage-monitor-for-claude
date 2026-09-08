"""
Event Command Environments
===========================

Translate quota state into the environment variables each event command
receives.  Every function here is pure: which command is configured, whether
the event should fire at all, and the call to the runner all stay with the
caller, so this module can be read as the answer to one question - what does a
command get told about what happened.
"""
from __future__ import annotations

from typing import Any

from .formatting import format_credits
from .i18n import T

__all__ = ['quick_action_env', 'quota_snapshot_env', 'reset_env', 'startup_env', 'threshold_env']


def quota_snapshot_env(data: dict[str, Any]) -> dict[str, str]:
    """Build environment variables describing the current quota state.

    Emits one ``USAGE_MONITOR_UTILIZATION_<FIELD>`` /
    ``USAGE_MONITOR_RESETS_AT_<FIELD>`` pair per detected quota field, plus
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
        if key == 'extra_usage' or not isinstance(entry, dict) or 'utilization' not in entry:
            continue
        env_vars[f'USAGE_MONITOR_UTILIZATION_{key.upper()}'] = str(round(entry.get('utilization', 0) or 0))
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
