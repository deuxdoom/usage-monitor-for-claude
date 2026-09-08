"""
Poll Scheduling
================

Work out when the next poll should land.  Every function here is pure: the
cadence values and the clock are passed in, so the rules that keep a fetch out
of the danger window before a quota reset can be read - and tested - without an
app around them.

The danger window is the last ``poll_fast - reset_buffer`` seconds before a
reset.  A fetch there consumes the cache cooldown, which forces the poll that
should confirm the reset to overshoot it by up to a full cooldown.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

__all__ = [
    'RESET_BUFFER', 'align_to_reset', 'clamp_to_reset', 'earliest_reset',
    'reset_aligned_target', 'tracked_reset_times',
]

# Seconds after a reset at which to place the confirming poll.  A small buffer
# absorbs minor timing differences (clocks, caches, server-side propagation).
RESET_BUFFER = 5


def align_to_reset(interval: int, next_reset: float | None, poll_fast: int, reset_buffer: int) -> tuple[int, bool]:
    """Shift the next poll so the confirming poll lands just after the reset.

    Every returned interval stays at or above ``poll_fast`` (the cache
    cooldown), so the reset is caught without polling faster.  The poll before
    the reset is pulled forward to ``poll_fast - reset_buffer`` seconds before
    it (the danger-window start); from there the confirming poll lands
    ``reset_buffer`` seconds after the reset.  When the current poll is already
    too close to pull the previous one forward without breaking the cooldown,
    the confirming poll is committed directly.

    Parameters
    ----------
    interval : int
        The normal cadence interval before reset alignment.
    next_reset : float or None
        Seconds until the nearest upcoming reset, or None.
    poll_fast : int
        The cache cooldown, and the floor for every returned interval.
    reset_buffer : int
        Seconds after the reset at which to place the confirming poll.

    Returns
    -------
    tuple[int, bool]
        The (possibly adjusted) interval and whether alignment engaged.
    """
    if next_reset is None or next_reset <= 0:
        return interval, False

    danger = poll_fast - reset_buffer          # last window where a poll can no longer be exact
    post = int(next_reset) + reset_buffer      # offset that lands the poll just after the reset

    if next_reset <= danger:
        # Already inside that last window: the confirming poll can only land
        # poll_fast after this one (small, unavoidable overshoot).
        return poll_fast, True

    if post <= interval * 1.5:
        # Reset near enough: commit the confirming poll to just after it.
        return post, True

    if next_reset < interval + danger:
        # A normal interval would drop the next poll into that last window,
        # from where the confirming poll would overshoot.  Pull it forward to
        # the window start (poll_fast - reset_buffer before the reset); if
        # that is too close to keep poll_fast spacing, commit to the
        # confirming poll directly.
        pre = int(next_reset) - danger
        return (pre if pre >= poll_fast else post), True

    return interval, False                     # reset still far - keep the normal cadence


def tracked_reset_times(usage: dict[str, Any], codex_windows: list[dict[str, Any]] | None,
                        codex_reset_iso: Any) -> list[str]:
    """ISO reset times of every quota the poll actually fetches.

    The Claude fields always.  The Codex windows only when the caller passes
    them, which it does while the tray follows Codex, because ``update()``
    reads those on the same beat.  A reset the poll does not fetch is left out
    on purpose: aligning the cadence to it would spend a poll on data that
    cannot have moved.

    Parameters
    ----------
    usage : dict
        The most recent usage response.
    codex_windows : list of dict or None
        Cached Codex quota windows, or None when Codex is not being polled.
    codex_reset_iso : callable
        Converts a Codex epoch reset time to the ISO form used here.
    """
    times = [entry['resets_at'] for entry in usage.values()
             if isinstance(entry, dict) and entry.get('resets_at')]
    for window in codex_windows or []:
        resets_at = codex_reset_iso(window.get('resets_at'))
        if resets_at:
            times.append(resets_at)

    return times


def earliest_reset(reset_times: list[str], now: datetime) -> float | None:
    """Seconds until the soonest of the given reset times, or None.

    Unparsable and already-past times are skipped rather than raising, so one
    malformed field cannot stop the scheduler from aligning to the others.

    Parameters
    ----------
    reset_times : list of str
        ISO 8601 reset times.
    now : datetime
        Timezone-aware current time.
    """
    earliest = None
    for resets_at in reset_times:
        try:
            seconds = (datetime.fromisoformat(resets_at) - now).total_seconds()
        except Exception:
            continue
        if seconds > 0 and (earliest is None or seconds < earliest):
            earliest = seconds

    return earliest


def reset_aligned_target(next_reset: float, last_success: float | None, now: float,
                         poll_fast: int, reset_buffer: int) -> float:
    """Absolute time for a poll landing just after a reset.

    Clamped to the cache cooldown (``last_success + poll_fast``) so the
    confirming poll never fires before a fresh fetch is permitted.

    Parameters
    ----------
    next_reset : float
        Seconds until the upcoming reset.
    last_success : float or None
        Epoch time of the last successful fetch, or None if there is none yet.
    now : float
        Current epoch time.
    poll_fast : int
        The cache cooldown.
    reset_buffer : int
        Seconds after the reset at which to place the confirming poll.
    """
    target = now + next_reset + reset_buffer
    if last_success is not None:
        target = max(target, last_success + poll_fast)

    return target


def clamp_to_reset(target: float, next_reset: float | None, last_success: float | None, now: float,
                   poll_fast: int, reset_buffer: int) -> float:
    """Pull a poll target back to the reset-aligned slot when it would overshoot.

    Keeps a scheduled poll out of the danger window, where a fetch consumes the
    cooldown and forces the confirming poll to overshoot the reset.

    Parameters
    ----------
    target : float
        Absolute time the poll is currently scheduled for.
    next_reset : float or None
        Seconds until the upcoming reset, or None when none is known.
    last_success : float or None
        Epoch time of the last successful fetch.
    now : float
        Current epoch time.
    poll_fast : int
        The cache cooldown.
    reset_buffer : int
        Seconds after the reset at which the confirming poll belongs.

    Returns
    -------
    float
        The target unchanged, or the reset-aligned slot when the target would
        land past it or inside the danger window.
    """
    if next_reset is None:
        return target

    reset_epoch = now + next_reset
    aligned = reset_aligned_target(next_reset, last_success, now, poll_fast, reset_buffer)
    if target > aligned or reset_epoch - (poll_fast - reset_buffer) < target < reset_epoch:
        return aligned

    return target
