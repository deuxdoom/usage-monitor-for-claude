"""
Popup Display Data
==================

Build the page's initial configuration and provider display data from snapshots.
Installation discovery and window operations belong to the caller.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import __version__
from .formatting import (
    codex_reset_iso, divider_positions, dollar_credit, duration_label, elapsed_pct, expand_popup_fields,
    field_countdown_only, field_period, format_count, format_credits, popup_label, time_until,
)
from .i18n import LANG_CODE, T
from .settings import (
    BAR_BG, BAR_DIVIDER, BAR_FG, BAR_FG_ALT, BAR_FG_WARN, BAR_MARKER, BG, COMPACT_HIDE, FG, FG_DIM, FG_HEADING, FG_LINK,
    POPUP_FIELDS, POPUP_VIEW, TIME_FORMAT,
)
from .theme import SIGNATURE_COLORS

__all__ = [
    'SESSION_DETAIL_FIELDS', 'codex_account_to_dict', 'init_config', 'session_detail_to_dict', 'session_window',
    'snapshot_to_dict', 'unavailable_session_detail',
]

if TYPE_CHECKING:
    from .claude_cache import CacheSnapshot
    from .claude_sessions import WindowStats

# The Claude quotas whose window the local transcripts can reproduce: the
# session and the weekly quota.  A model-scoped or unlabeled quota has no
# local-log equivalent.  The bar data marks these fields and session_detail()
# accepts only them, so the page keeps no list of its own.
SESSION_DETAIL_FIELDS = ('five_hour', 'seven_day')

# A field's estimated total (tokens_used / utilization) is only shown once
# the percentage is high enough that dividing by it is not just amplifying
# noise - at 0.3%, for instance, a handful of tokens either way swings the
# estimate by tens of thousands.
_MIN_UTILIZATION_FOR_ESTIMATE = 1.0


def init_config(
    snap: CacheSnapshot, installations: list[dict[str, str]], next_poll_time: float | None = None,
    view: str = POPUP_VIEW, provider: str = 'claude', material: str = 'matte', framed: bool = False,
) -> dict[str, Any]:
    """Build the config object passed to JS ``init()`` after the page loads.

    Parameters
    ----------
    snap : CacheSnapshot
        The data the page renders first.
    installations : list
        Installation names and versions already read by the caller.
    next_poll_time : float or None
        Unix timestamp of the next scheduled poll, for the footer countdown.
    view : str
        One of ``POPUP_VIEWS`` - which view the page opens in.
    provider : str
        ``'claude'`` or ``'codex'`` - the agent the detail view opens on,
        which is the one the tray icon follows.
    material : str
        One of ``POPUP_MATERIALS`` - the surface the page draws.  Matte by
        default, because a page drawing glass over a window without the
        glass layer shows black behind it.
    framed : bool
        True when DWM rounds the window, so the page leaves its own edge
        stroke out.
    """
    return {
        'colors': {
            'bg': BG, 'fg': FG, 'fg_dim': FG_DIM, 'fg_heading': FG_HEADING, 'fg_link': FG_LINK,
            'bar_bg': BAR_BG, 'bar_fg': BAR_FG, 'bar_fg_alt': BAR_FG_ALT, 'bar_fg_warn': BAR_FG_WARN,
            'bar_divider': BAR_DIVIDER, 'bar_marker': BAR_MARKER, **SIGNATURE_COLORS,
        },
        't': {
            'title': T['app_name'], 'account': T['account'], 'email': T['email'], 'plan': T['plan'],
            'usage': T['usage'], 'extra_usage': T['extra_usage'], 'name': T['name'],
            'show_more_limits': T['show_more_limits'], 'show_fewer_limits': T['show_fewer_limits'],
            'reveal_email': T['reveal_email'], 'hide_email': T['hide_email'],
            'claude_code': T['claude_code'], 'changelog': T['changelog'], 'project_on_github': T['menu_project'],
            'pin_popup': T['pin_popup'], 'unpin_popup': T['unpin_popup'], 'close_popup': T['close_popup'], 'refresh': T['refresh'],
            'view_bar': T['view_bar'], 'view_detail': T['view_detail'],
            'bar_used': T['bar_used'], 'bar_left': T['bar_left'],
            'bar_mode_used': T['bar_mode_used'], 'bar_mode_left': T['bar_mode_left'],
            'bar_toggle_hint': T['bar_toggle_hint'], 'bar_fill_hint': T['bar_fill_hint'], 'drag_to_move': T['drag_to_move'],
            'detail_tokens': T['detail_tokens'], 'detail_messages': T['detail_messages'],
            'detail_estimated': T['detail_estimated'], 'detail_models': T['detail_models'],
            'detail_loading': T['detail_loading'], 'detail_unavailable': T['detail_unavailable'],
            'detail_no_usage': T['detail_no_usage'], 'detail_source': T['detail_source'],
            **{key: value for key, value in T.items() if key.startswith('codex_')},
            'status_updated_s': T['status_updated_s'], 'status_updated': T['status_updated'],
            'status_next_update': T['status_next_update'], 'status_refreshing': T['status_refreshing'],
            'duration_hm': T['duration_hm'], 'duration_m': T['duration_m'], 'duration_ms': T['duration_ms'], 'duration_s': T['duration_s'],
        },
        'app_version': __version__,
        'compact_hide': COMPACT_HIDE,
        'view': view,
        'provider': provider,
        'material': material,
        'framed': framed,
        # The app's language rather than the system's: the bar clock formats
        # its date in it, and the page sets it as the document language so
        # heading tracking suits the script.
        'lang_tag': LANG_CODE,
        'time_format': TIME_FORMAT,
        'data': snapshot_to_dict(snap, installations, next_poll_time=next_poll_time),
    }


def snapshot_to_dict(
    snap: CacheSnapshot, installations: list[dict[str, str]], next_poll_time: float | None = None,
) -> dict[str, Any]:
    """Convert a CacheSnapshot to a JSON-serializable dict for the popup JS.

    Parameters
    ----------
    snap : CacheSnapshot
        Immutable snapshot of the cache state.
    installations : list
        Installation names and versions already read by the caller.
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

            bar = {
                'key': field,
                'label': label,
                'period_seconds': period,
                'pct_text': f'{pct:.0f}%',
                'left_text': f'{max(0.0, 100 - pct):.0f}%',
                'fill_pct': max(0.0, min(1.0, pct / 100)),
                'warn': warn,
                'pace_text': _pace_text(pct, time_pct),
                'reset_text': time_until(resets_at, countdown_only=field_countdown_only(field)) if resets_at else '',
                'dividers': divider_positions(resets_at, period) if period else [],
                'marker_rel': marker_rel,
                'session_detail': field in SESSION_DETAIL_FIELDS,
            }
            credit = dollar_credit(entry)
            if credit is not None:
                bar.update(_credit_texts(*credit, resets_at))
            usage.append(bar)

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
                balance_text = _prepaid_balance_text(snap.prepaid)
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
                        'balance_text': balance_text,
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
                        'balance_text': balance_text,
                    }

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


def codex_account_to_dict(snapshot: dict[str, Any], local_periods: set[int],
                          next_poll_time: float | None) -> dict[str, Any]:
    """Format server quota windows with the same markers and reset text as Claude.

    Parameters
    ----------
    snapshot : dict
        A ``CodexAccount.snapshot()`` result.
    local_periods : set of int
        Window lengths the local rollout reader actually produced.  A server
        window offers its expandable token detail only when a local window of
        the same length exists, so the two sides stay in step without either
        naming the periods - changing the local windows moves the detail with
        them instead of silently leaving a bar that expands into nothing.
    next_poll_time : float or None
        The app's own poll beat, which both provider views count down to.  A
        Codex-only deadline would tick to a different moment depending on when
        the user first opened the tab, so the two views are handed the same one.
        None falls back to the read's own deadline, which is all there is
        before the first cadence poll has been scheduled.
    """
    usage = []
    for window in snapshot['windows']:
        period = window['seconds']
        day_scoped = period % 86400 == 0
        pct = window['used']
        # An unused Codex window can carry resetsAt without an active session.
        reset = codex_reset_iso(window['resets_at']) if pct > 0 else ''
        time_pct = elapsed_pct(reset, period) if reset else None
        usage.append({
            'key': window['key'], 'label': duration_label(period), 'period_seconds': period,
            'pct_text': f'{pct:.0f}%', 'left_text': f'{max(0.0, 100 - pct):.0f}%',
            'fill_pct': max(0.0, min(1.0, pct / 100)),
            'warn': pct >= 100 or (time_pct is not None and pct > time_pct),
            'pace_text': _pace_text(pct, time_pct),
            'detail_seconds': period if period in local_periods else None,
            'reset_text': time_until(reset, countdown_only=not day_scoped) if reset else '',
            'dividers': divider_positions(reset, period) if reset else [],
            'marker_rel': max(0.0, min(1.0, time_pct / 100)) if time_pct is not None else None,
        })
    return {
        'profile': snapshot['profile'], 'usage': usage,
        'credits_text': _codex_credits_text(snapshot.get('credits')),
        'status': {'last_success_time': snapshot['updated_at'],
                   'next_poll_time': next_poll_time if next_poll_time is not None else snapshot['next_read'],
                   'error': T[snapshot['error']] if snapshot['error'] else None},
    }


def session_window(resets_at: Any, period: int, now: float) -> tuple[float, float]:
    """Return the ``(start, end)`` Unix times a Claude quota window covers.

    The window ends at the quota's reset and spans its period, which is the
    stretch the bar's percentage describes.  A missing or unreadable reset
    time ends it now, so the detail still covers the last ``period`` seconds.

    Parameters
    ----------
    resets_at : str or None
        The quota's ``resets_at`` as the API reports it.
    period : int
        The window length in seconds.
    now : float
        The current Unix time.
    """
    end = now
    if resets_at:
        try:
            text = resets_at[:-1] + '+00:00' if resets_at.endswith('Z') else resets_at
            end = datetime.fromisoformat(text).timestamp()
        except ValueError:
            end = now

    return end - period, end


def session_detail_to_dict(stats: WindowStats, utilization: Any) -> dict[str, Any]:
    """Format one window's local-transcript totals for the bar's detail panel.

    Parameters
    ----------
    stats : WindowStats
        What ``claude_sessions.usage_in_window()`` counted for the window.
    utilization : float or None
        The quota's reported percentage, for the estimated total.

    Returns
    -------
    dict
        ``{unavailable, tokens, messages, estimated_total, models}``.
        ``tokens``/``messages``/``estimated_total`` are comma-grouped strings
        ready to display, and ``models`` is a list of ``{model, tokens, pct}``
        with ``tokens`` comma-grouped and ``pct`` a string like ``'96.6'``.

        ``estimated_total`` is ``tokens / (utilization / 100)``, included
        only once the utilization is high enough for that division to be
        meaningful, and None otherwise.  It is an extrapolation from the
        API's own reported percentage, not a guess at Anthropic's actual
        limit - the two can disagree since the transcripts and the API may
        not account for tokens identically.
    """
    estimated_total = None
    if isinstance(utilization, (int, float)) and utilization >= _MIN_UTILIZATION_FOR_ESTIMATE and stats.total_tokens > 0:
        estimated_total = format_count(round(stats.total_tokens / (utilization / 100)))

    return {
        'unavailable': False,
        'tokens': format_count(stats.total_tokens),
        'messages': format_count(stats.message_count),
        'estimated_total': estimated_total,
        'models': [
            {'model': model.model, 'tokens': format_count(model.tokens), 'pct': f'{model.fraction * 100:.1f}'}
            for model in stats.models
        ],
    }


def unavailable_session_detail() -> dict[str, Any]:
    """The detail result for a bar with nothing meaningful to show.

    The page renders a fallback message for it rather than a zeroed report,
    which would misleadingly claim confirmed zero usage.
    """
    return {'unavailable': True, 'tokens': None, 'messages': None, 'estimated_total': None, 'models': []}


def _usage_entries(usage: dict[str, Any]) -> list[tuple[str, dict[str, Any] | None, int | None, str]]:
    """Return ``(label, data, period, field)`` tuples from the given usage data.

    The raw *field* name is included so the popup can hide individual bars
    by field name when the pinned compact view is configured.
    """
    fields = expand_popup_fields(POPUP_FIELDS, usage)
    return [(popup_label(key), usage.get(key), field_period(key), key) for key in fields]


def _prepaid_balance_text(prepaid: dict[str, Any] | None) -> str:
    """Return the rendered prepaid-credit balance line, or '' when unavailable."""
    if not prepaid:
        return ''

    amount = prepaid.get('amount_minor')
    if amount is None:
        return ''

    balance = format_credits(amount, prepaid.get('currency'), prepaid.get('decimal_places'))

    return T['extra_usage_balance'].format(balance=balance)


def _codex_credits_text(credits: dict[str, Any] | None) -> str:
    """Render purchased Codex credits as the extra-usage balance line, or '' without any.

    Counted in Codex credits, as Codex itself shows them: the response names
    no exchange rate, so a dollar figure would be invented.
    """
    if not credits:
        return ''
    if credits.get('unlimited'):
        return T['codex_credits_unlimited']

    balance = credits.get('balance')
    if balance is None:
        return ''

    amount = format_count(int(balance)) if float(balance).is_integer() else f'{balance:,.2f}'

    return T['codex_credits_balance'].format(balance=amount)


def _credit_texts(used: float, limit: float, resets_at: str) -> dict[str, str]:
    """Texts for a quota counted in dollars: the amounts replace the percentages.

    The fill still measures the used share, and the reset time is worded as
    an expiry, because what is left of a grant lapses then rather than refills.
    """
    left = max(0.0, limit - used)

    return {
        'pct_text': _dollars(used),
        'left_text': _dollars(left),
        'pace_text': T['credit_remaining'].format(left=_dollars(left), limit=_dollars(limit)),
        'reset_text': time_until(resets_at, expiry=True) if resets_at else '',
    }


def _dollars(amount: float) -> str:
    """Format a dollar amount the API reports in whole units (``limit_dollars``)."""
    return format_credits(round(amount * 100), 'USD', 2)


def _pace_text(pct: float, time_pct: float | None) -> str:
    """Describe consumption relative to the elapsed quota window."""
    if pct >= 100:
        return T['pace_exhausted']
    if time_pct is None:
        return ''

    state = T['pace_ahead'] if pct > time_pct else T['pace_within']
    return T['pace_elapsed'].format(pct=f'{time_pct:.0f}', state=state)
