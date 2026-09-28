"""
Codex API Client
=================

Read account and quota data through the installed Codex app-server protocol.
Authentication is owned by Codex; this module never reads credentials.
"""
from __future__ import annotations

import json
import math
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .codex_cli import find_binary as _find_binary
from .settings import MAX_BACKOFF

__all__ = ['CodexAccount']

_TIMEOUT = 20
# Bound stalled requests, including reads from older app-servers that do not
# honor excludeResetCreditDetails, then retry in a fresh app-server.
_REQUEST_TIMEOUT = 10
_ATTEMPTS = 2


class CodexAccount:
    """Keep account snapshots and retry deadlines across popup lifetimes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_read: float | None = None
        self._failures = 0
        self._snapshot: dict[str, Any] = {}

    @property
    def cached(self) -> dict[str, Any]:
        """The last snapshot, without starting a read.

        Deliberately takes no lock: the attribute is only ever rebound to a
        finished dict, so a reader sees either the previous snapshot or the
        new one.  Waiting on the lock would block the caller for as long as a
        running app-server read takes, which is the opposite of what a
        cache-only accessor is for.
        """
        return self._snapshot

    def snapshot(self, interval: int) -> dict[str, Any]:
        """Fetch at most once per ``interval``, backing off after failed requests.

        The cadence is the caller's to decide - it is the refresh interval the
        user chose - so this module holds no interval of its own.  The wait is
        measured from the last read rather than stored as a deadline, which is
        what lets a shortened interval apply on the next call instead of only
        after the previous, longer wait has run out.

        Parameters
        ----------
        interval : int
            Seconds between successful reads.

        Returns
        -------
        dict
            Account, quota windows, purchased credits, timestamps and a
            translatable error key.  Failed reads clear prior values to avoid
            presenting a stale account.
        """
        with self._lock:
            if self._last_read is not None:
                remaining = self._delay(interval) - (time.monotonic() - self._last_read)
                if remaining > 0:
                    # Recompute the deadline against the interval in force now.
                    # Handing back the stored one reports a moment the previous,
                    # longer interval implied; once that moment is past, the popup
                    # has nothing left to count down to and freezes on
                    # "updated N minutes ago" until the next read lands.
                    return {**self._snapshot, 'next_read': time.time() + remaining}
            error = None
            account = None
            windows = []
            credits = None
            try:
                binary = _find_binary()
                if binary is None:
                    raise _ReadError('codex_cli_missing')
                account, windows, credits = _fetch_with_retry(binary)
                if not windows:
                    error = 'codex_limits_unavailable'
            except _ReadError as exc:
                error = exc.key
            except (OSError, ValueError, subprocess.SubprocessError):
                error = 'codex_account_error'
            self._last_read = time.monotonic()
            self._failures = min(self._failures + 1, 4) if error else 0
            now = time.time()
            self._snapshot = {'profile': account, 'windows': windows, 'credits': credits, 'error': error,
                              'updated_at': now, 'next_read': now + self._delay(interval)}
            return self._snapshot

    def _delay(self, interval: int) -> int:
        """Seconds to wait before the next read, doubling per consecutive failure."""
        return min(interval * 2 ** self._failures, MAX_BACKOFF)


class _ReadError(Exception):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


def _fetch_with_retry(binary: Path) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, Any] | None]:
    """Read again in a fresh app-server when a read fails for a reason that is not the account's.

    Only ``codex_account_error`` is retried: a stalled or failed request says
    nothing about the account, while a missing login or an API-key login
    would fail the same way twice.
    """
    for _ in range(_ATTEMPTS - 1):
        try:
            return _fetch(binary)
        except _ReadError as exc:
            if exc.key != 'codex_account_error':
                raise

    return _fetch(binary)


def _fetch(binary: Path) -> tuple[dict[str, str], list[dict[str, Any]], dict[str, Any] | None]:
    """Read identity, quotas and purchased credits within one short-lived app-server connection."""
    process = subprocess.Popen(
        [str(binary), 'app-server', '-c', 'analytics.enabled=false', '-c', 'otel.exporter="none"'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    stdin, stdout = process.stdin, process.stdout
    assert stdin is not None and stdout is not None  # both were requested as pipes
    responses: queue.Queue = queue.Queue()
    reader = threading.Thread(target=_read_responses, args=(stdout, responses), daemon=True)
    reader.start()
    deadline = time.monotonic() + _TIMEOUT
    try:
        _request(process, responses, deadline, 1, 'initialize', {
            'clientInfo': {'name': 'usage_monitor', 'version': '1.0.0'},
            'capabilities': {'experimentalApi': False},
        })
        stdin.write(b'{"method":"initialized"}\n')
        stdin.flush()
        result = _request(process, responses, deadline, 2, 'account/read', {'refreshToken': False})
        account = result.get('account')
        if not isinstance(account, dict):
            raise _ReadError('codex_login_required')
        if account.get('type') != 'chatgpt':
            raise _ReadError('codex_chatgpt_required')
        # Background polls need quota windows and purchased credits, not the
        # separate earned-reset detail lookup that can stall at exhaustion.
        limits = _request(process, responses, deadline, 3, 'account/rateLimits/read', {'excludeResetCreditDetails': True})
        confirmed = _request(process, responses, deadline, 4, 'account/read', {'refreshToken': False})
        if confirmed.get('account') != account:
            raise _ReadError('codex_account_error')
        windows = _windows(limits)
        email = account.get('email')
        return {
            'email': email if isinstance(email, str) else '',
            'name': '',
            'plan': _plan_label(account.get('planType')),
        }, windows, _credits(limits)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        reader.join(timeout=1)
        stdin.close()
        stdout.close()


def _plan_label(plan_type: Any) -> str:
    """Name the ChatGPT plan a Codex account is on.

    The app-server reports the bare tier - ``free``, ``go``, ``plus``, ``pro``,
    ``business``, ``enterprise`` - which reads as a fragment next to the Claude
    view's plan, so the product name goes in front of it.  One rule covers every
    tier instead of a lookup table, so a tier OpenAI adds later is labeled right
    without a code change.

    Parameters
    ----------
    plan_type : Any
        The response's ``planType``; anything but a non-empty string yields ''.
    """
    if not isinstance(plan_type, str):
        return ''

    tier = plan_type.replace('_', ' ').strip()
    # A value that already names the product must not become "ChatGPT ChatGPT Plus".
    if tier.lower().startswith('chatgpt'):
        tier = tier[len('chatgpt'):].strip()
    if not tier:
        return ''

    return f'ChatGPT {tier.title()}'


def _read_responses(stream: Any, responses: queue.Queue) -> None:
    """Forward protocol responses without retaining notification payloads."""
    try:
        for line in stream:
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if isinstance(record, dict) and 'id' in record:
                responses.put(record)
    finally:
        responses.put(None)


def _request(process: Any, responses: queue.Queue, deadline: float, request_id: int, method: str, params: dict) -> dict:
    """Match response IDs and bound each read by its own timeout and the connection's deadline."""
    request_deadline = min(deadline, time.monotonic() + _REQUEST_TIMEOUT)
    process.stdin.write((json.dumps({'id': request_id, 'method': method, 'params': params}) + '\n').encode('utf-8'))
    process.stdin.flush()
    while True:
        try:
            record = responses.get(timeout=max(0, request_deadline - time.monotonic()))
        except queue.Empty:
            raise _ReadError('codex_account_error') from None
        if record is None:
            raise _ReadError('codex_account_error')
        if record.get('id') != request_id:
            continue
        if 'error' in record or not isinstance(record.get('result'), dict):
            raise _ReadError('codex_account_error')
        return record['result']


def _codex_bucket(result: dict) -> dict | None:
    """The Codex rate-limit bucket: the per-limit entry when present, else the legacy one."""
    buckets = result.get('rateLimitsByLimitId')
    bucket = buckets.get('codex') if isinstance(buckets, dict) else None
    if not isinstance(bucket, dict):
        bucket = result.get('rateLimits')

    return bucket if isinstance(bucket, dict) else None


def _credits(result: dict) -> dict[str, Any] | None:
    """Read the credits bought for Codex usage beyond the plan's limits.

    The balance is counted in Codex credits, not in money - the response
    names no rate between the two, so it is never shown as dollars.  None
    unless the account holds credits or has unlimited ones, so a plan without
    any shows nothing rather than a zero balance.

    Parameters
    ----------
    result : dict
        The ``account/rateLimits/read`` result.
    """
    bucket = _codex_bucket(result)
    credits = bucket.get('credits') if bucket is not None else None
    if not isinstance(credits, dict):
        return None
    if credits.get('unlimited') is True:
        return {'unlimited': True, 'balance': None}
    if credits.get('hasCredits') is not True:
        return None

    balance_text = credits.get('balance')
    if not isinstance(balance_text, str):
        return None
    try:
        balance = float(balance_text)
    except ValueError:
        return None
    if not math.isfinite(balance) or balance < 0:
        return None

    return {'unlimited': False, 'balance': balance}


def _windows(result: dict) -> list[dict[str, Any]]:
    """Validate server windows without assuming which period is primary."""
    bucket = _codex_bucket(result)
    if bucket is None:
        return []
    windows = []
    for key, value in bucket.items():
        if not isinstance(value, dict):
            continue
        used = value.get('usedPercent')
        minutes = value.get('windowDurationMins')
        reset = value.get('resetsAt')
        if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used) or used < 0:
            continue
        if type(minutes) is not int or not 0 < minutes <= 525600:
            continue
        if reset is not None and (isinstance(reset, bool) or not isinstance(reset, (int, float))
                                  or not math.isfinite(reset) or not 0 < reset < 253402300800):
            continue
        windows.append({'key': 'codex_' + key, 'used': used, 'seconds': minutes * 60, 'resets_at': reset})
    return sorted(windows, key=lambda window: window['seconds'])
