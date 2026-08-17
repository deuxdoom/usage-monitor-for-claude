"""
Formatting
===========

Pure functions for formatting usage data: time-until-reset strings,
elapsed period percentages, credit amounts, status lines, and tooltip text.
"""
from __future__ import annotations

import locale as _locale
from datetime import datetime, timedelta, timezone
from typing import Any

from .i18n import T
from .settings import (
    CURRENCY_SYMBOL, POPUP_HIDE_FIELDS, POPUP_HIDE_INACTIVE, TIME_FORMAT, TOOLTIP_FIELDS,
    _SYSTEM_CURRENCY_SYMBOL,
)

__all__ = [
    'divider_positions', 'elapsed_pct', 'expand_popup_fields', 'field_countdown_only', 'field_hidden',
    'field_inactive', 'field_period', 'format_count', 'format_credits', 'format_tooltip',
    'parse_field_name', 'popup_label', 'time_until', 'tooltip_label',
]

PERIOD_5H = 5 * 3600
PERIOD_7D = 7 * 24 * 3600

_NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
    'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12,
}
_UNIT_SUFFIXES = {'hour': 'h', 'day': 'd'}
_TITLE_CASE_EXCEPTIONS = {'oauth': 'OAuth', 'api': 'API', 'ai': 'AI'}
_CURRENCY_SYMBOLS = {
    'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 'CNY': '¥',
    'INR': '₹', 'KRW': '₩', 'BRL': 'R$', 'CAD': 'CA$', 'AUD': 'A$', 'CHF': 'CHF',
}


def parse_field_name(field: str) -> tuple[int, str, str | None] | None:
    """Parse an API field name into its numeric, unit, and variant components.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.

    Returns
    -------
    tuple or None
        ``(number, unit, variant)`` where *number* is the parsed digit,
        *unit* is the raw unit word (e.g. ``'hour'``, ``'day'``), and
        *variant* is the remaining suffix or ``None``.
        Returns ``None`` if the number word or unit is not recognized.
    """
    parts = field.split('_', 2)
    if len(parts) < 2:
        return None

    number = _NUMBER_WORDS.get(parts[0])
    unit = parts[1]
    if number is None or unit not in _UNIT_SUFFIXES:
        return None

    variant = parts[2] if len(parts) > 2 else None
    return (number, unit, variant)


def _title_case_variant(text: str) -> str:
    """Title-case a variant string, respecting abbreviation exceptions."""
    return ' '.join(_TITLE_CASE_EXCEPTIONS.get(w.lower(), w.title()) for w in text.split('_'))


def tooltip_label(field: str) -> str:
    """Generate a short tooltip label from an API field name.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.

    Returns
    -------
    str
        Short label like ``'5h'``, ``'7d'``, or ``'7d Sonnet'``.
        Falls back to title case of the full field name if unparseable.
    """
    parsed = parse_field_name(field)
    if parsed is None:
        return _title_case_variant(field)

    number, unit, variant = parsed
    label = f'{number}{_UNIT_SUFFIXES[unit]}'
    if variant:
        label += f' {_title_case_variant(variant)}'
    return label


def popup_label(field: str) -> str:
    """Generate a popup bar label from an API field name using i18n templates.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.

    Returns
    -------
    str
        Localized label like ``'Session (5hr)'`` or ``'Weekly (Sonnet)'``.
        Falls back to title case with abbreviation exceptions if unparseable.
    """
    parsed = parse_field_name(field)
    if parsed is None:
        return _title_case_variant(field)

    number, unit, variant = parsed
    if variant:
        suffix = _title_case_variant(variant)
    else:
        suffix = T['unit_hours' if unit == 'hour' else 'unit_days'].format(n=number)

    template_key = 'session_label' if unit == 'hour' else 'weekly_label'
    return T[template_key].format(suffix=suffix)


def field_period(field: str) -> int | None:
    """Return the period duration in seconds for a field, or None if unknown.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.
    """
    parsed = parse_field_name(field)
    if parsed is None:
        return None

    number, unit, _ = parsed
    if unit == 'hour':
        return number * 3600
    if unit == 'day':
        return number * 24 * 3600
    return None


def field_countdown_only(field: str) -> bool:
    """Return whether a field's reset line should always show the time remaining.

    Hour-scoped quotas (the rolling session window) are short enough that
    "how much is left" is the only useful reading.  A window ending after
    midnight would otherwise render as a bare calendar time ("Resets
    tomorrow, 01:00"), hiding that the session has, say, 40 minutes left.
    Day-scoped quotas keep the calendar form, where a weekday and date say
    more than a three-digit hour count.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'five_hour'``, ``'seven_day_sonnet'``.
    """
    parsed = parse_field_name(field)
    if parsed is None:
        return False

    _, unit, _ = parsed
    return unit == 'hour'


def _slug(text: str) -> str:
    """Normalize a field name or label to a comparable slug.

    Lowercases and reduces every run of non-alphanumeric characters to a
    single underscore, so ``'Nimbus Quill'``, ``'nimbus-quill'`` and
    ``'nimbus_quill'`` all compare equal.
    """
    cleaned = ''.join(char if char.isalnum() else ' ' for char in text.lower())
    return '_'.join(cleaned.split())


def field_hidden(field: str, patterns: list[str] | None = None) -> bool:
    """Return whether a usage field is suppressed by ``popup_hide_fields``.

    A pattern matches when it equals the field name, the field's variant
    suffix, or the field's rendered popup label - so the same entry works
    whether the API exposes a quota as a top-level field (``nimbus_quill``)
    or as a model-scoped one (``seven_day_nimbus_quill``), and whether the
    user copies the raw name or the text shown in the popup.  Matching is
    case-insensitive and ignores spaces, hyphens and underscores.

    Parameters
    ----------
    field : str
        API field name, e.g. ``'seven_day_opus'``.
    patterns : list[str] or None
        Patterns to match against; defaults to the ``popup_hide_fields``
        setting.

    Returns
    -------
    bool
        True if the field must not be displayed.
    """
    if patterns is None:
        patterns = POPUP_HIDE_FIELDS
    if not patterns:
        return False

    parsed = parse_field_name(field)
    candidates = {_slug(field), _slug(popup_label(field))}
    if parsed is not None and parsed[2]:
        candidates.add(_slug(parsed[2]))

    return any(_slug(pattern) in candidates for pattern in patterns if pattern)


# The two account-wide quotas.  Every other field (a model-scoped limit such
# as seven_day_opus, or an unlabeled one like nimbus_quill) is a bonus quota
# that popup_hide_inactive is meant to filter; these two are the ones people
# open the popup to check and must never disappear just because the current
# period has not been touched yet.
_ALWAYS_SHOWN_FIELDS = frozenset({'five_hour', 'seven_day'})


def format_count(n: int) -> str:
    """Format an integer count with thousands separators.

    Uses a plain comma rather than the system locale's grouping - unlike
    :func:`format_credits`, which must render a legible amount of money,
    this covers supplementary counts (tokens, messages) where a comma is
    a widely understood grouping mark and matching every locale's exact
    convention is not worth threading ``LC_NUMERIC`` through for.
    """
    return f'{n:,}'


def field_inactive(entry: dict[str, Any] | None, field: str | None = None) -> bool:
    """Return whether a quota has never been used.

    True when the API reports no reset window (the quota has no active
    period) and nothing consumed.  Such a quota renders as a permanently
    empty bar with no countdown, which is only useful as an advance notice
    that the limit exists - hence the ``popup_hide_inactive`` setting.

    Parameters
    ----------
    entry : dict or None
        A single quota object from the usage API response.
    field : str or None
        The field's API name.  ``five_hour`` and ``seven_day`` are exempt:
        a fresh account or one that has not touched a period yet reports
        them the same way as a scoped quota nobody has ever used, but they
        are core limits and must stay visible regardless.
    """
    if field in _ALWAYS_SHOWN_FIELDS:
        return False
    if not isinstance(entry, dict):
        return False

    utilization = entry.get('utilization')
    return not entry.get('resets_at') and utilization is not None and utilization <= 0


def _field_sort_key(field: str) -> tuple[int, int, int, str]:
    """Sort key for default field ordering: shorter periods first, base before variants."""
    parsed = parse_field_name(field)
    if parsed is None:
        return (2, 0, 0, field)

    number, unit, variant = parsed
    unit_order = 0 if unit == 'hour' else 1
    variant_order = 0 if variant is None else 1
    return (unit_order, number, variant_order, variant or '')


def expand_popup_fields(popup_fields: list[str], usage_data: dict[str, Any]) -> list[str]:
    """Expand a popup_fields setting into concrete field names based on API data.

    Parameters
    ----------
    popup_fields : list[str]
        User-configured field list, possibly containing ``'*'`` wildcard.
    usage_data : dict
        Raw API response dict.

    Returns
    -------
    list[str]
        Ordered list of field names to display, with null/missing fields
        and fields suppressed by ``popup_hide_fields`` removed.  When
        ``popup_hide_inactive`` is set, never-used quotas are also dropped
        from the wildcard expansion.
    """
    available = {
        key for key, value in usage_data.items()
        if isinstance(value, dict) and 'utilization' in value and 'resets_at' in value
        and value.get('utilization') is not None
        and not field_hidden(key)
    }

    result: list[str] = []
    seen: set[str] = set()

    for field in popup_fields:
        if field == '*':
            # Unused quotas are dropped from the wildcard only - listing one
            # explicitly is taken as "show it anyway".
            remaining = sorted(
                (
                    f for f in available
                    if f not in seen and not (POPUP_HIDE_INACTIVE and field_inactive(usage_data.get(f), f))
                ),
                key=_field_sort_key,
            )
            for f in remaining:
                seen.add(f)
                result.append(f)
        elif field in available and field not in seen:
            seen.add(field)
            result.append(field)

    return result


def elapsed_pct(resets_at: str, period_seconds: int) -> float | None:
    """Return elapsed percentage of a usage period, or None if not calculable.

    Parameters
    ----------
    resets_at : str
        ISO 8601 timestamp when the limit resets.
    period_seconds : int
        Total duration of the period in seconds (e.g. 18000 for 5h).

    Returns
    -------
    float or None
        Percentage of the period that has already elapsed (0-100),
        or None if the value cannot be determined.
    """
    if not resets_at or period_seconds <= 0:
        return None

    try:
        reset = datetime.fromisoformat(resets_at)
        now = datetime.now(timezone.utc)
        remaining = (reset - now).total_seconds()
        elapsed = period_seconds - remaining

        return max(0.0, min(100.0, elapsed / period_seconds * 100))
    except Exception:
        return None


def divider_positions(resets_at: str, period_seconds: int) -> list[float]:
    """Return relative positions (0.0-1.0) of divider marks within a usage period.

    Five-hour periods are split into five equal hour sections, independent
    of clock alignment.  Periods of a day or longer are subdivided at local
    midnight boundaries (e.g. seven day marks on a weekly bar).  Other
    sub-day periods have no dividers - their subdivision is a deliberate
    design decision for if and when such quota types exist.

    Parameters
    ----------
    resets_at : str
        ISO 8601 timestamp when the limit resets.
    period_seconds : int
        Total duration of the period in seconds.

    Returns
    -------
    list[float]
        Divider positions within the period, each in the range (0.0, 1.0)
        exclusive.  Positions that would round to 0px at typical bar
        widths are omitted.
    """
    if not resets_at or period_seconds <= 0:
        return []

    try:
        reset_utc = datetime.fromisoformat(resets_at)

        if period_seconds < 24 * 3600:
            if period_seconds != PERIOD_5H:
                return []
            return [i / 5 for i in range(1, 5)]

        start_utc = reset_utc - timedelta(seconds=period_seconds)

        start_local = start_utc.astimezone()
        end_local = reset_utc.astimezone()

        # Walk local calendar days and convert each naive midnight separately:
        # astimezone() re-evaluates the UTC offset per date, so a DST
        # changeover inside the period keeps every divider on a true local
        # midnight (adding timedeltas would carry the period-start offset).
        day = start_local.date() + timedelta(days=1)

        positions = []
        while True:
            midnight = datetime(day.year, day.month, day.day).astimezone()
            if midnight >= end_local:
                break
            elapsed = (midnight - start_local).total_seconds()
            rel = elapsed / period_seconds
            if rel > 0.003:
                positions.append(rel)
            day += timedelta(days=1)

        return positions
    except Exception:
        return []


def _format_clock(when: datetime, clock_24h: bool) -> str:
    """Format a local time as a 24-hour ('14:30') or 12-hour ('2:30 PM') clock string."""
    if clock_24h:
        return when.strftime('%H:%M')

    # %I is zero-padded (e.g. '02:30 PM'); strip the single leading zero for '2:30 PM'.
    return when.strftime('%I:%M %p').lstrip('0')


def time_until(iso_str: str, clock_24h: bool | None = None, countdown_only: bool = False) -> str:
    """Return human-readable reset time.

    Same day:  "Resets in 2h 20m (14:30)"
    Tomorrow:  "Resets tomorrow, 12:00"
    Later:     "Resets on Sat 1/18, 12:00"

    Parameters
    ----------
    iso_str : str
        ISO 8601 timestamp when the limit resets.
    clock_24h : bool or None
        Format the clock time in 24-hour (True) or 12-hour (False) style.
        ``None`` falls back to the ``time_format`` setting.
    countdown_only : bool
        Always use the "Resets in ..." form, even when the reset falls on a
        later calendar day.  Set for short rolling windows, where the time
        remaining is the point (see ``field_countdown_only``).
    """
    if clock_24h is None:
        clock_24h = TIME_FORMAT == '24h'

    try:
        reset = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        diff = reset - now
        total_seconds = diff.total_seconds()

        # Within the last minute before the reset (or the first moments after,
        # while the server-side reset propagates), show an imminent marker
        # instead of hiding the line - mirrors the native UI. Clearly-stale
        # timestamps (far in the past) still collapse to empty so we do not lie.
        if total_seconds < 60:
            return T['resets_imminent'] if total_seconds > -60 else ''

        total_min = int(total_seconds / 60)
        reset_local = reset.astimezone()
        today = datetime.now().date()
        if reset_local.second >= 30:
            reset_local = reset_local.replace(second=0) + timedelta(minutes=1)
        else:
            reset_local = reset_local.replace(second=0)
        reset_date = reset_local.date()
        time_str = _format_clock(reset_local, clock_24h)

        if countdown_only or reset_date == today:
            if total_min >= 60:
                duration = T['duration_hm'].format(h=total_min // 60, m=total_min % 60)
            else:
                duration = T['duration_m'].format(m=total_min)
            return T['resets_in'].format(duration=duration, clock=time_str)

        if reset_date == today + timedelta(days=1):
            return T['resets_tomorrow'].format(clock=time_str)

        # Beyond tomorrow the weekday alone is ambiguous (it repeats every
        # week), so the calendar date is shown alongside it.
        weekday = T['weekdays'][reset_local.weekday()]
        date_str = T['date_month_day'].format(m=reset_local.month, d=reset_local.day)
        return T['resets_weekday'].format(day=weekday, date=date_str, clock=time_str)
    except Exception:
        return ''


def _target_currency_symbol(currency: str | None) -> str:
    """Return the symbol to display for a currency amount.

    Precedence: an explicit ``currency_symbol`` user override (``None``
    means unset; an empty override means "no symbol"), then the billing
    currency reported by the API (its known symbol, or the ISO code itself
    as a fallback), then the system locale symbol.

    Parameters
    ----------
    currency : str or None
        ISO 4217 currency code from the API (e.g. ``'EUR'``), or None.
    """
    if CURRENCY_SYMBOL is not None:
        return CURRENCY_SYMBOL

    if currency:
        return _CURRENCY_SYMBOLS.get(currency.upper(), currency.upper())

    return _SYSTEM_CURRENCY_SYMBOL


def format_credits(minor_units: float, currency: str | None = None, decimal_places: int | None = None) -> str:
    """Format a minor-unit amount as a localized currency string.

    Uses the system locale for number formatting (decimal separator, symbol
    placement, grouping).  The displayed symbol follows the billing currency
    reported by the API when it differs from the system locale, so an account
    billed in a currency other than the system's still shows correctly.

    Parameters
    ----------
    minor_units : float
        Amount in the currency's minor units (e.g. 420.0 for 4.20 at two
        decimal places).
    currency : str or None
        ISO 4217 currency code from the API (e.g. ``'EUR'``).
    decimal_places : int or None
        Number of minor-unit decimal places reported by the API; defaults to
        two when not provided.
    """
    places = decimal_places if decimal_places is not None else 2
    amount = minor_units / (10 ** places)
    symbol = _target_currency_symbol(currency)

    try:
        formatted = _locale.currency(amount, grouping=True)

        # An empty symbol (explicit "no symbol" override) removes the system
        # symbol instead of leaving it in place.
        if symbol != _SYSTEM_CURRENCY_SYMBOL and _SYSTEM_CURRENCY_SYMBOL:
            formatted = formatted.replace(_SYSTEM_CURRENCY_SYMBOL, symbol).strip()

        return formatted
    except (ValueError, _locale.Error):
        if symbol:
            return f'{symbol}\u00a0{amount:.{places}f}'
        return f'{amount:.{places}f}'


def format_tooltip(data: dict[str, Any]) -> str:
    """Format usage data as short tooltip text."""
    if 'error' in data:
        if data.get('auth_error'):
            return f"{T['auth_expired_label']}\n{T['auth_expired_short']}"
        error = data['error']
        server_msg = data.get('server_message')
        if server_msg:
            error += f' {server_msg}'
        return f"{T['error_label']}\n{error[:80]}"

    lines = [T['tooltip_title']]
    for key in TOOLTIP_FIELDS:
        entry = data.get(key)
        if isinstance(entry, dict) and entry.get('utilization') is not None:
            short = tooltip_label(key)
            pct = f"{entry['utilization']:.0f}%"
            reset = time_until(entry.get('resets_at', ''), countdown_only=field_countdown_only(key))
            line = f'{short}: {pct}'
            if reset:
                line += f' ({reset})'
            lines.append(line)

    return '\n'.join(lines)
