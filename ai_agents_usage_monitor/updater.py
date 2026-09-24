"""
App Updater
===========

Checks GitHub for a newer stable release at startup and, when there is one,
hands the whole update to a helper: a copy of this EXE in a temporary
folder, because a running file cannot replace itself.  The helper shows a
single frameless window from start to finish - what changed, the five
steps, the progress and the result.  The app keeps running until the new
EXE is downloaded and verified; only then does the helper ask it to quit,
replace the file and start the new version with the original arguments.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import functools
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests
import truststore

from . import __version__

__all__ = ['check_and_offer_update', 'release_highlights', 'run_update_helper']

logger = logging.getLogger(__name__)

RELEASE_API_URL = 'https://api.github.com/repos/deuxdoom/usage-monitor-for-claude/releases/latest'
RELEASE_DOWNLOAD_PREFIX = 'https://github.com/deuxdoom/usage-monitor-for-claude/releases/download/'
RELEASES_PAGE_URL = 'https://github.com/deuxdoom/usage-monitor-for-claude/releases/latest'
ASSET_NAME = 'AIAgentsUsageMonitor.exe'
HELPER_NAME = 'AIAgentsUsageMonitor-Updater.exe'
MAX_ASSET_SIZE = 200 * 1024 * 1024
MAX_NOTE_ITEMS = 8
_HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'AI-Agents-Usage-Monitor'}
_VERSION_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')
_DIGEST_RE = re.compile(r'^sha256:([0-9a-fA-F]{64})$')
_ALLOWED_ASSET_HOSTS = frozenset({'release-assets.githubusercontent.com', 'objects.githubusercontent.com'})
_UI_PATH = Path(__file__).parent / 'popup' / 'updater.html'
_WINDOW_SIZE = (460, 640)
_WINDOW_BACKGROUND = '#101316'
# Named per app process, so a helper can only ever ask its own parent to quit.
_QUIT_EVENT_PREFIX = 'Local\\AIAgentsUsageMonitor-UpdateQuit-'
_PARENT_EXIT_TIMEOUT_MS = 30000
# The new version must still be running this long after it was started, or
# the helper puts the previous EXE back.
_START_CONFIRM_SECONDS = 3.0
_DISK_HEADROOM = 10 * 1024 * 1024
_MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
_SYNCHRONIZE = 0x00100000
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x102
_IMAGE_SUBSYSTEM_WINDOWS_GUI = 2
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_MONITOR_DEFAULTTOPRIMARY = 1
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_MARKDOWN_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]*\)')
_BOLD_LEAD_RE = re.compile(r'^\*\*(.+?)\*\*\s*(.*)$')

# Overall progress at the start of each step; the download fills the first span.
_STEP_PERCENT = {'download': 0, 'verify': 72, 'close': 80, 'install': 90, 'restart': 95}
_DOWNLOAD_SPAN = 70


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    sha256: str
    size: int
    notes: str = ''


class VerificationError(ValueError):
    """The downloaded file is not the release's EXE."""


class _StepFailed(Exception):
    """An update step failed.

    ``outcome`` says where that left the user, so the window can say it:
    ``still_running`` (the app was never asked to quit), ``restored`` (the
    previous version is back and running) or ``start_manually`` (the app is
    not running and could not be started).
    """

    def __init__(self, step: str, cause: Exception, outcome: str) -> None:
        super().__init__(str(cause))
        self.step = step
        self.cause = cause
        self.outcome = outcome


# ---------------------------------------------------------------------------
# Release metadata
# ---------------------------------------------------------------------------

def _version_parts(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.fullmatch(value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _release_info(payload: dict[str, Any], current_version: str) -> ReleaseInfo | None:
    tag = payload.get('tag_name')
    if not isinstance(tag, str) or payload.get('draft') or payload.get('prerelease'):
        return None

    latest = _version_parts(tag)
    current = _version_parts(current_version)
    if latest is None or current is None or latest <= current:
        return None

    assets = payload.get('assets')
    if not isinstance(assets, list):
        return None

    version = '.'.join(str(part) for part in latest)
    expected_url = f'{RELEASE_DOWNLOAD_PREFIX}{tag}/{ASSET_NAME}'
    notes = payload.get('body') if isinstance(payload.get('body'), str) else ''
    for asset in assets:
        if not isinstance(asset, dict) or asset.get('name') != ASSET_NAME or asset.get('state') != 'uploaded':
            continue
        size = asset.get('size')
        digest = asset.get('digest')
        url = asset.get('browser_download_url')
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_ASSET_SIZE:
            continue
        if not isinstance(digest, str) or not (match := _DIGEST_RE.fullmatch(digest)):
            continue
        if url != expected_url:
            continue
        return ReleaseInfo(version, url, match.group(1).lower(), size, notes)

    return None


def check_latest_release(current_version: str) -> ReleaseInfo | None:
    """Return the newer stable release only when its EXE has a SHA-256 digest."""
    truststore.inject_into_ssl()
    response = requests.get(RELEASE_API_URL, headers=_HEADERS, timeout=(5, 10), allow_redirects=False)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError('Unexpected GitHub release response')
    return _release_info(payload, current_version)


def release_highlights(body: str) -> dict[str, Any]:
    """Reduce a release's Markdown notes to the short list the update window shows.

    The notes follow ``RELEASE.md``: an optional bold one-line summary, then
    ``###`` sections of ``- **Label:** text`` bullets.  Sections without
    bullets (the file-hash table, the changelog link) drop out, links keep
    only their text, and at most ``MAX_NOTE_ITEMS`` bullets are kept - the
    rest are counted so the window can point to the full notes.

    Parameters
    ----------
    body : str
        The release body as GitHub returns it.

    Returns
    -------
    dict
        ``{'summary': str, 'sections': [{'title': str, 'items': [{'label': str, 'text': str}]}], 'more': int}``.
    """
    summary = ''
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    kept = 0
    more = 0

    for raw_line in (body or '').splitlines():
        line = raw_line.strip()
        if line.startswith('### '):
            current = {'title': _plain(line[4:]), 'items': []}
            sections.append(current)
            continue
        if line.startswith(('- ', '* ')):
            if kept >= MAX_NOTE_ITEMS:
                more += 1
                continue
            if current is None:
                current = {'title': '', 'items': []}
                sections.append(current)
            current['items'].append(_note_item(line[2:]))
            kept += 1
            continue
        if not summary and not sections and line.startswith('**') and line.endswith('**') and len(line) > 4:
            summary = _plain(line)

    return {
        'summary': summary,
        'sections': [section for section in sections if section['items']],
        'more': more,
    }


def _note_item(text: str) -> dict[str, str]:
    text = _MARKDOWN_LINK_RE.sub(r'\1', text.strip())
    match = _BOLD_LEAD_RE.match(text)
    if not match:
        return {'label': '', 'text': _plain(text)}
    return {'label': _plain(match.group(1)).rstrip(':').strip(), 'text': _plain(match.group(2))}


def _plain(text: str) -> str:
    return _MARKDOWN_LINK_RE.sub(r'\1', text).replace('**', '').replace('`', '').strip()


# ---------------------------------------------------------------------------
# App side: offer the update
# ---------------------------------------------------------------------------

def check_and_offer_update(monitor: Any) -> None:
    """Check once after startup and open the update window when a newer release exists.

    Runs on its own thread, so it never delays the tray or usage polling.
    Nothing is shown when the check fails or there is nothing newer: a
    background check must not raise a dialog.
    """
    if not getattr(sys, 'frozen', False):
        return

    from .i18n import LANG_CODE

    try:
        release = check_latest_release(__version__)
    except (requests.RequestException, ValueError) as exc:
        logger.info('Update check unavailable: %s', exc)
        return
    if release is None or not monitor.running:
        return

    try:
        helper, quit_event, staging_dir = launch_update_helper(release.version, LANG_CODE, sys.argv[1:])
    except OSError as exc:
        logger.info('Update window unavailable: %s', exc)
        return
    _quit_when_helper_asks(monitor, helper, quit_event, staging_dir)


def launch_update_helper(version: str, language: str, relaunch_args: list[str]) -> tuple[subprocess.Popen, int, Path]:
    """Copy this frozen EXE to temporary storage and start it as the update window.

    Parameters
    ----------
    version : str
        The release the window offers.
    language : str
        The app's language code, so the window speaks it too.
    relaunch_args : list[str]
        This process's own arguments, which the new version is started with.

    Returns
    -------
    tuple
        The helper process, the event it sets to ask this app to quit, and
        the staging folder to remove if the user declines.
    """
    if not getattr(sys, 'frozen', False):
        raise OSError('Automatic replacement requires a frozen EXE')

    source = Path(sys.executable).resolve(strict=True)
    if source.name != ASSET_NAME:
        raise OSError(f'Unexpected executable name: {source.name}')

    staging_dir = Path(tempfile.mkdtemp(prefix='ai-agents-updater-'))
    helper = staging_dir / HELPER_NAME
    try:
        quit_event = _create_quit_event(os.getpid())
    except OSError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    try:
        shutil.copy2(source, helper)
        process = _spawn([str(helper), '--apply-update', str(source), version, str(os.getpid()), language, *relaunch_args], staging_dir)
    except OSError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        _kernel32().CloseHandle(quit_event)
        raise
    return process, quit_event, staging_dir


def _quit_when_helper_asks(monitor: Any, helper: subprocess.Popen, quit_event: int, staging_dir: Path) -> None:
    """Quit the app once the helper holds a verified download; tidy up if it never asks.

    The helper sets the event only after the new EXE is downloaded and
    verified, so the app keeps running through the whole offer and download.
    A helper that exits without asking was declined or failed early; its
    copy of the EXE is then removed here rather than left until a reboot.
    """
    asked = False
    try:
        while helper.poll() is None and monitor.running:
            if _wait_signaled(quit_event, 500):
                asked = True
                monitor.on_quit()
                return
    finally:
        _kernel32().CloseHandle(quit_event)
        if not asked and helper.poll() is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)


def _create_quit_event(pid: int) -> int:
    handle = _kernel32().CreateEventW(None, True, False, f'{_QUIT_EVENT_PREFIX}{pid}')
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _wait_signaled(handle: int, timeout_ms: int) -> bool:
    return _kernel32().WaitForSingleObject(handle, timeout_ms) == _WAIT_OBJECT_0


# ---------------------------------------------------------------------------
# Helper side: the update window
# ---------------------------------------------------------------------------

class _UpdateApi:
    """The page's bridge.  Private state is underscored so pywebview does not expose it."""

    def __init__(self) -> None:
        self._window: Any = None
        self._lock = threading.Lock()
        self._ready = False
        self._busy = False
        self._started = threading.Event()

    def start(self) -> bool:
        with self._lock:
            if not self._ready or self._busy:
                return False
            self._busy = True
        self._started.set()
        return True

    def close(self) -> bool:
        if self._busy:
            return False
        self._window.destroy()
        return True

    def open_notes(self) -> None:
        webbrowser.open(RELEASES_PAGE_URL)


def run_update_helper(target_arg: str, expected_version: str, parent_pid_arg: str, language: str, *relaunch_args: str) -> int:
    """Show the update window in this separate process and run the update from it.

    Parameters
    ----------
    target_arg : str
        The installed EXE to replace.
    expected_version : str
        The release the app offered; a different latest release aborts.
    parent_pid_arg : str
        The running app, which is asked to quit once the download is verified.
    language : str
        Language code for the window's labels.
    *relaunch_args : str
        Arguments the app was started with, passed on to the new version.

    Returns
    -------
    int
        0 when the new version was installed and started, 1 otherwise, 2 for
        invalid arguments.
    """
    if not getattr(sys, 'frozen', False) or _version_parts(expected_version) is None:
        return 2
    try:
        target = Path(target_arg).resolve(strict=True)
        parent_pid = int(parent_pid_arg)
        if target.name != ASSET_NAME or parent_pid <= 0:
            return 2
        labels = _labels(language)
    except (OSError, ValueError):
        return 2

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_ssize_t(-4))
    except AttributeError:
        pass

    import webview  # type: ignore[import-untyped]  # no type stubs available

    api = _UpdateApi()
    width, height = _WINDOW_SIZE
    window = webview.create_window(
        labels['update_title'], url=str(_UI_PATH), js_api=api,
        width=width, height=height, resizable=False,
        frameless=True, easy_drag=False, shadow=True, on_top=True, hidden=True,
        background_color=_WINDOW_BACKGROUND,
    )
    api._window = window
    # Alt+F4 and the taskbar close go through here too: while files are being
    # swapped, closing the window would strand the user without an app.
    window.events.closing += lambda: not api._busy

    result = {'code': 1}
    started = threading.Event()

    def on_loaded() -> None:
        if started.is_set():
            return
        started.set()
        _round_corners(window)
        _center_on_primary(window)
        _push(window, 'init', {
            'labels': _page_labels(labels), 'lang': language,
            'current': __version__, 'latest': expected_version,
        })
        _push(window, 'setState', {'phase': 'loading', 'step': None, 'percent': 0, 'message': labels['update_checking']})
        window.show()
        worker = threading.Thread(
            target=_update_worker, args=(window, api, labels, target, expected_version, parent_pid, list(relaunch_args), result),
            daemon=True,
        )
        worker.start()

    window.events.loaded += on_loaded
    try:
        webview.start()
    finally:
        _schedule_helper_cleanup()
    return result['code']


def _update_worker(window: Any, api: _UpdateApi, labels: dict[str, str], target: Path, expected_version: str,
                   parent_pid: int, relaunch_args: list[str], result: dict[str, int]) -> None:
    """Offer the release, then download, verify, swap and restart on request."""
    try:
        release = check_latest_release('0.0.0')
    except (requests.RequestException, ValueError) as exc:
        _fail(window, api, labels, None, labels['update_check_failed'], str(exc))
        return
    if release is None or release.version != expected_version:
        _fail(window, api, labels, None, labels['update_release_changed'], '')
        return

    _push(window, 'setNotes', release_highlights(release.notes))
    with api._lock:
        api._ready = True
    _push(window, 'setState', {'phase': 'offer', 'step': None, 'percent': 0, 'message': labels['update_ready']})
    api._started.wait()

    try:
        _install(window, labels, release, target, parent_pid, relaunch_args)
    except _StepFailed as failure:
        logger.exception('Automatic update failed in %s', failure.step)
        _fail(window, api, labels, failure.step, labels[f'update_failed_{failure.step}'], str(failure.cause), failure.outcome)
        return

    result['code'] = 0
    api._busy = False
    _push(window, 'setState', {
        'phase': 'done', 'step': None, 'percent': 100, 'message': labels['update_complete'].format(version=release.version),
    })


def _install(window: Any, labels: dict[str, str], release: ReleaseInfo, target: Path, parent_pid: int, relaunch_args: list[str]) -> None:
    """Run the five steps, or raise ``_StepFailed`` naming the step that went wrong.

    Nothing touches the installed EXE until the new one is downloaded and
    verified and the app has exited.  A copy of the installed EXE is kept
    until the new version is confirmed running; if it does not start, the
    copy goes back and is started instead.
    """
    download: Path | None = None
    backup: Path | None = None
    quit_requested = False
    app_stopped = False
    replaced = False
    confirmed = False
    step = 'download'
    try:
        _state(window, step, 0, labels['update_downloading'])
        _require_disk_space(target, release.size)
        last_percent = -1

        def on_progress(received: int) -> None:
            nonlocal last_percent
            percent = _DOWNLOAD_SPAN * received // release.size
            if percent != last_percent:
                last_percent = percent
                detail = f'{received / 1_048_576:.1f} / {release.size / 1_048_576:.1f} MB'
                _state(window, 'download', percent, labels['update_downloading'], detail)

        try:
            download = _download_asset(release, target.parent, on_progress)
        except VerificationError:
            step = 'verify'
            raise

        step = 'verify'
        _state(window, step, _STEP_PERCENT[step], labels['update_verifying'])
        _verify_executable(download)

        step = 'close'
        _state(window, step, _STEP_PERCENT[step], labels['update_waiting'])
        backup = _backup_executable(target)
        _request_parent_quit(parent_pid)
        quit_requested = True
        _wait_for_parent(parent_pid)
        app_stopped = True

        step = 'install'
        _state(window, step, _STEP_PERCENT[step], labels['update_installing'])
        _replace_executable(download, target)
        download = None
        replaced = True

        step = 'restart'
        _state(window, step, _STEP_PERCENT[step], labels['update_restarting'])
        if not _start_and_confirm(target, relaunch_args):
            raise RuntimeError('The new version exited right after starting')
        confirmed = True
    except Exception as exc:
        if app_stopped:
            outcome = 'restored' if _restore_previous(target, backup if replaced else None, relaunch_args) else 'start_manually'
        else:
            # Asked to quit but not confirmed gone: starting another copy now
            # would only meet the single-instance check of the one still exiting.
            outcome = 'start_manually' if quit_requested else 'still_running'
        raise _StepFailed(step, exc, outcome) from exc
    finally:
        if download is not None:
            download.unlink(missing_ok=True)
        # After a failed swap-back the copy is the only intact previous
        # version, so it stays; otherwise it is either redundant or moved back.
        if backup is not None and (confirmed or not replaced):
            backup.unlink(missing_ok=True)


def _restore_previous(target: Path, backup: Path | None, relaunch_args: list[str]) -> bool:
    """Put ``backup`` back over ``target`` when given, then start it.

    Returns whether the previous version is running again, so the user is
    told whether they have to start it themselves.
    """
    try:
        if backup is not None:
            _replace_executable(backup, target)
        return _start_and_confirm(target, relaunch_args)
    except OSError:
        logger.exception('Could not restore the previous version')
        return False


def _fail(window: Any, api: _UpdateApi, labels: dict[str, str], step: str | None, message: str, detail: str,
          outcome: str | None = None) -> None:
    api._busy = False
    if outcome:
        message = f"{message} {labels[f'update_{outcome}']}"
    percent = _STEP_PERCENT[step] if step else 0
    _push(window, 'setState', {'phase': 'failed', 'step': step, 'percent': percent, 'message': message, 'detail': detail})


def _state(window: Any, step: str, percent: int, message: str, detail: str = '') -> None:
    _push(window, 'setState', {'phase': 'running', 'step': step, 'percent': percent, 'message': message, 'detail': detail})


def _push(window: Any, function: str, payload: Any) -> None:
    window.evaluate_js(f'{function}({json.dumps(payload, ensure_ascii=False)})')


def _page_labels(labels: dict[str, str]) -> dict[str, Any]:
    return {
        'notes': labels['update_notes'], 'notes_loading': labels['update_notes_loading'],
        'notes_empty': labels['update_notes_empty'], 'notes_unavailable': labels['update_notes_unavailable'],
        'notes_more': labels['update_notes_more'],
        'full_notes': labels['update_full_notes'], 'later': labels['update_later'],
        'update_now': labels['update_now'], 'close': labels['update_close'],
        'headings': {
            'loading': labels['update_heading_available'], 'offer': labels['update_heading_available'],
            'running': labels['update_heading_running'], 'done': labels['update_heading_done'],
            'failed': labels['update_heading_failed'],
        },
        'steps': {step: labels[f'update_step_{step}'] for step in _STEP_PERCENT},
    }


def _labels(language: str) -> dict[str, str]:
    code = language if language in {'en', 'ja', 'ko'} else 'en'
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return json.loads((base / 'locale' / f'{code}.json').read_text(encoding='utf-8'))


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('rcMonitor', ctypes.wintypes.RECT),
        ('rcWork', ctypes.wintypes.RECT),
        ('dwFlags', ctypes.wintypes.DWORD),
    ]


def _center_on_primary(window: Any) -> None:
    """Size the hidden window exactly and put it in the middle of the primary monitor's work area.

    WinForms neither centres the window nor sizes it to the requested
    logical pixels under the per-monitor DPI mode set above - it opened near
    the top-left corner, a little too small.  pywebview's own ``resize()``
    shows the window as it resizes, so size and position are set here in
    one physical-pixel call while it is still hidden.
    """
    user32 = _user32()
    hwnd = window.native.Handle.ToInt32()
    scale = (user32.GetDpiForWindow(hwnd) or 96) / 96
    width, height = (round(side * scale) for side in _WINDOW_SIZE)

    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    monitor = user32.MonitorFromPoint(ctypes.wintypes.POINT(0, 0), _MONITOR_DEFAULTTOPRIMARY)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return
    work = info.rcWork
    x = work.left + max(0, (work.right - work.left - width) // 2)
    y = work.top + max(0, (work.bottom - work.top - height) // 2)
    user32.SetWindowPos(hwnd, None, x, y, width, height, _SWP_NOZORDER | _SWP_NOACTIVATE)


def _round_corners(window: Any) -> None:
    """Ask Windows 11 for rounded corners; earlier versions ignore the attribute."""
    try:
        hwnd = window.native.Handle.ToInt32()
        preference = ctypes.c_int(_DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(preference), ctypes.sizeof(preference))
    except (AttributeError, OSError):
        logger.debug('Rounded corners unavailable', exc_info=True)


# ---------------------------------------------------------------------------
# Helper side: files and processes
# ---------------------------------------------------------------------------

def _allowed_download_url(url: str, first_hop: bool = False) -> bool:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != 'https' or parsed.username or parsed.password or port:
        return False
    if first_hop:
        return url.startswith(RELEASE_DOWNLOAD_PREFIX) and parsed.hostname == 'github.com'
    return parsed.hostname in _ALLOWED_ASSET_HOSTS or parsed.hostname == 'github.com'


def _download_asset(release: ReleaseInfo, target_dir: Path, progress: Callable[[int], None]) -> Path:
    """Stream to a same-directory temporary file and verify size and SHA-256.

    ``progress`` receives the number of bytes written so far.  A size or
    digest mismatch raises ``VerificationError``; every failure removes the
    partial file.
    """
    descriptor, path = tempfile.mkstemp(prefix='.ai-agents-update-', suffix='.download', dir=target_dir)
    download = Path(path)
    url = release.url
    received = 0
    digest = hashlib.sha256()

    try:
        with os.fdopen(descriptor, 'wb') as output:
            for hop in range(5):
                if not _allowed_download_url(url, first_hop=hop == 0):
                    raise ValueError('Unexpected download destination')
                with requests.get(url, headers=_HEADERS, timeout=(5, 30), stream=True, allow_redirects=False) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get('Location')
                        if not location:
                            raise ValueError('GitHub download redirect has no destination')
                        url = urljoin(url, location)
                        continue
                    response.raise_for_status()
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        received += len(chunk)
                        if received > release.size:
                            raise VerificationError('Downloaded file exceeds GitHub release size')
                        output.write(chunk)
                        digest.update(chunk)
                        progress(received)
                    break
            else:
                raise ValueError('Too many GitHub download redirects')

        if received != release.size or digest.hexdigest() != release.sha256:
            raise VerificationError('Downloaded EXE failed size or SHA-256 verification')
        return download
    except Exception:
        download.unlink(missing_ok=True)
        raise


def _verify_executable(path: Path) -> None:
    """Refuse anything but a windowed Windows executable, whatever its digest says."""
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise VerificationError('Downloaded file is not a Windows executable')
        offset = struct.unpack_from('<I', header, 60)[0]
        stream.seek(offset)
        pe = stream.read(96)
    if len(pe) != 96 or pe[:4] != b'PE\0\0' or struct.unpack_from('<H', pe, 92)[0] != _IMAGE_SUBSYSTEM_WINDOWS_GUI:
        raise VerificationError('Downloaded file is not a windowed Windows executable')


def _require_disk_space(target: Path, download_size: int) -> None:
    needed = download_size + target.stat().st_size + _DISK_HEADROOM
    if shutil.disk_usage(target.parent).free < needed:
        raise OSError('Not enough free disk space for the download and a backup')


def _backup_executable(target: Path) -> Path:
    """Copy the installed EXE aside so a failed start can be rolled back."""
    descriptor, path = tempfile.mkstemp(prefix='.ai-agents-update-', suffix='.previous', dir=target.parent)
    os.close(descriptor)
    backup = Path(path)
    try:
        shutil.copy2(target, backup)
    except OSError:
        backup.unlink(missing_ok=True)
        raise
    return backup


def _request_parent_quit(pid: int) -> None:
    """Set the parent's quit event; a parent that is already gone has nothing to hear it."""
    kernel32 = _kernel32()
    handle = kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, f'{_QUIT_EVENT_PREFIX}{pid}')
    if not handle:
        return
    try:
        kernel32.SetEvent(handle)
    finally:
        kernel32.CloseHandle(handle)


def _wait_for_parent(pid: int) -> None:
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        return
    try:
        result = kernel32.WaitForSingleObject(handle, _PARENT_EXIT_TIMEOUT_MS)
        if result == _WAIT_TIMEOUT:
            raise TimeoutError('The running app did not exit within 30 seconds')
        if result != _WAIT_OBJECT_0:
            raise OSError('Could not wait for the running app to exit')
    finally:
        kernel32.CloseHandle(handle)


def _replace_executable(download: Path, target: Path) -> None:
    """Swap the file in, retrying while the old process's loader still holds it."""
    for attempt in range(50):
        try:
            os.replace(download, target)
            return
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.2)


def _start_and_confirm(target: Path, relaunch_args: list[str]) -> bool:
    """Start ``target`` and report whether it is still running a moment later."""
    process = _spawn([str(target), *relaunch_args], target.parent)
    deadline = time.monotonic() + _START_CONFIRM_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        time.sleep(0.1)
    return True


def _spawn(command: list[str], cwd: Path) -> subprocess.Popen:
    """Start another copy of this app as an independent process.

    A PyInstaller one-file build tells the programs it starts where its
    unpacked files live, through ``_PYI_*`` variables and the DLL directory.
    Another copy of the app that inherits those would share this process's
    temporary folder - which is deleted the moment this process exits, taking
    the new instance down with it.  That is why an update used to install but
    never come back up.  ``PYINSTALLER_RESET_ENVIRONMENT`` makes the child
    unpack its own copy instead.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith('_PYI_') and key != '_MEIPASS2'}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    bundle_dir = getattr(sys, '_MEIPASS', None)
    if bundle_dir:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        return subprocess.Popen(
            command, cwd=str(cwd), env=env, close_fds=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    finally:
        if bundle_dir:
            ctypes.windll.kernel32.SetDllDirectoryW(bundle_dir)


def _schedule_helper_cleanup() -> None:
    helper = Path(sys.executable)
    if helper.name != HELPER_NAME:
        return
    kernel32 = ctypes.windll.kernel32
    kernel32.MoveFileExW(str(helper), None, _MOVEFILE_DELAY_UNTIL_REBOOT)
    kernel32.MoveFileExW(str(helper.parent), None, _MOVEFILE_DELAY_UNTIL_REBOOT)


@functools.cache
def _user32() -> Any:
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetDpiForWindow.argtypes = [ctypes.wintypes.HWND]
    user32.GetDpiForWindow.restype = ctypes.wintypes.UINT
    user32.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.wintypes.DWORD]
    user32.MonitorFromPoint.restype = ctypes.wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [ctypes.wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
    user32.GetMonitorInfoW.restype = ctypes.wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        ctypes.wintypes.HWND, ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.wintypes.UINT,
    ]
    user32.SetWindowPos.restype = ctypes.wintypes.BOOL
    return user32


@functools.cache
def _kernel32() -> Any:
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = ctypes.wintypes.HANDLE
    kernel32.OpenEventW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = ctypes.wintypes.HANDLE
    kernel32.SetEvent.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.SetEvent.restype = ctypes.wintypes.BOOL
    kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = ctypes.wintypes.DWORD
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
    return kernel32
