"""Codex Account
=============

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

__all__ = ['CodexAccount']

_TIMEOUT = 20
_INTERVAL = 60


class CodexAccount:
    """Keep account snapshots and retry deadlines across popup lifetimes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_read = 0.0
        self._failures = 0
        self._snapshot: dict[str, Any] = {}

    def snapshot(self) -> dict[str, Any]:
        """Fetch at most once per minute, backing off after failed requests.

        Returns
        -------
        dict
            Account, quota windows, timestamps and a translatable error key.
            Failed reads clear prior values to avoid presenting a stale account.
        """
        with self._lock:
            if time.monotonic() < self._next_read:
                return self._snapshot
            error = None
            account = None
            windows = []
            try:
                binary = _find_binary()
                if binary is None:
                    raise _ReadError('codex_cli_missing')
                account, windows = _fetch(binary)
                if not windows:
                    error = 'codex_limits_unavailable'
            except _ReadError as exc:
                error = exc.key
            except (OSError, ValueError, subprocess.SubprocessError):
                error = 'codex_account_error'
            self._failures = min(self._failures + 1, 4) if error else 0
            delay = min(_INTERVAL * 2 ** self._failures, 900)
            now = time.time()
            self._next_read = time.monotonic() + delay
            self._snapshot = {'profile': account, 'windows': windows, 'error': error,
                              'updated_at': now, 'next_read': now + delay}
            return self._snapshot


class _ReadError(Exception):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


def _fetch(binary: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Read identity and quotas within one short-lived app-server connection."""
    process = subprocess.Popen(
        [str(binary), 'app-server', '-c', 'analytics.enabled=false', '-c', 'otel.exporter="none"'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    responses: queue.Queue = queue.Queue()
    reader = threading.Thread(target=_read_responses, args=(process.stdout, responses), daemon=True)
    reader.start()
    deadline = time.monotonic() + _TIMEOUT
    try:
        _request(process, responses, deadline, 1, 'initialize', {
            'clientInfo': {'name': 'usage_monitor', 'version': '1.0.0'},
            'capabilities': {'experimentalApi': False},
        })
        process.stdin.write(b'{"method":"initialized"}\n')
        process.stdin.flush()
        result = _request(process, responses, deadline, 2, 'account/read', {'refreshToken': False})
        account = result.get('account')
        if not isinstance(account, dict):
            raise _ReadError('codex_login_required')
        if account.get('type') != 'chatgpt':
            raise _ReadError('codex_chatgpt_required')
        limits = _request(process, responses, deadline, 3, 'account/rateLimits/read', {})
        confirmed = _request(process, responses, deadline, 4, 'account/read', {'refreshToken': False})
        if confirmed.get('account') != account:
            raise _ReadError('codex_account_error')
        windows = _windows(limits)
        return {
            'email': account.get('email') if isinstance(account.get('email'), str) else '',
            'name': '',
            'plan': _plan_label(account.get('planType')),
        }, windows
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        reader.join(timeout=1)
        process.stdin.close()
        process.stdout.close()


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
    """Match response IDs and bound all reads by the connection's deadline."""
    process.stdin.write((json.dumps({'id': request_id, 'method': method, 'params': params}) + '\n').encode('utf-8'))
    process.stdin.flush()
    while True:
        try:
            record = responses.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty:
            raise _ReadError('codex_account_error') from None
        if record is None:
            raise _ReadError('codex_account_error')
        if record.get('id') != request_id:
            continue
        if 'error' in record or not isinstance(record.get('result'), dict):
            raise _ReadError('codex_account_error')
        return record['result']


def _windows(result: dict) -> list[dict[str, Any]]:
    """Validate server windows without assuming which period is primary."""
    buckets = result.get('rateLimitsByLimitId')
    bucket = buckets.get('codex') if isinstance(buckets, dict) else None
    if not isinstance(bucket, dict):
        bucket = result.get('rateLimits')
    if not isinstance(bucket, dict):
        return []
    windows = []
    for key, value in bucket.items():
        if not isinstance(value, dict):
            continue
        used = value.get('usedPercent')
        minutes = value.get('windowDurationMins')
        reset = value.get('resetsAt')
        if type(used) not in (int, float) or not math.isfinite(used) or used < 0:
            continue
        if type(minutes) is not int or not 0 < minutes <= 525600:
            continue
        if reset is not None and (type(reset) not in (int, float) or not math.isfinite(reset) or not 0 < reset < 253402300800):
            continue
        windows.append({'key': 'codex_' + key, 'used': used, 'seconds': minutes * 60, 'resets_at': reset})
    return sorted(windows, key=lambda window: window['seconds'])
