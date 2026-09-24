"""Check GitHub releases and replace a frozen EXE from a separate process."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests
import truststore

from . import __version__

__all__ = ['check_and_offer_update', 'run_update_helper']

logger = logging.getLogger(__name__)

RELEASE_API_URL = 'https://api.github.com/repos/deuxdoom/usage-monitor-for-claude/releases/latest'
RELEASE_DOWNLOAD_PREFIX = 'https://github.com/deuxdoom/usage-monitor-for-claude/releases/download/'
ASSET_NAME = 'AIAgentsUsageMonitor.exe'
MAX_ASSET_SIZE = 200 * 1024 * 1024
_HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'AI-Agents-Usage-Monitor'}
_VERSION_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')
_DIGEST_RE = re.compile(r'^sha256:([0-9a-fA-F]{64})$')
_ALLOWED_ASSET_HOSTS = frozenset({'release-assets.githubusercontent.com', 'objects.githubusercontent.com'})
_MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 0x102


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    sha256: str
    size: int


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
        return ReleaseInfo(version, url, match.group(1).lower(), size)

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


def check_and_offer_update(monitor: Any) -> None:
    """Check once after startup without delaying the tray or usage polling."""
    if not getattr(sys, 'frozen', False):
        return

    from .i18n import LANG_CODE, T

    try:
        release = check_latest_release(__version__)
    except (requests.RequestException, ValueError) as exc:
        logger.info('Update check unavailable: %s', exc)
        return
    if release is None or not monitor.running:
        return

    message = T['update_available'].format(current=__version__, latest=release.version)
    choice = ctypes.windll.user32.MessageBoxW(0, message, T['update_title'], 0x24)
    if choice != 6 or not monitor.running:
        return

    try:
        launch_update_helper(release.version, LANG_CODE)
    except OSError as exc:
        ctypes.windll.user32.MessageBoxW(0, T['update_start_failed'].format(reason=str(exc)), T['update_title'], 0x10)
        return
    monitor.on_quit()


def launch_update_helper(version: str, language: str) -> None:
    """Copy this frozen EXE to temporary storage, then start its helper mode."""
    if not getattr(sys, 'frozen', False):
        raise OSError('Automatic replacement requires a frozen EXE')

    source = Path(sys.executable).resolve(strict=True)
    if source.name != ASSET_NAME:
        raise OSError(f'Unexpected executable name: {source.name}')

    staging_dir = Path(tempfile.mkdtemp(prefix='ai-agents-updater-'))
    helper = staging_dir / 'AIAgentsUsageMonitor-Updater.exe'
    try:
        shutil.copy2(source, helper)
        subprocess.Popen(
            [str(helper), '--apply-update', str(source), version, str(os.getpid()), language],
            close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        shutil.rmtree(staging_dir)
        raise


def _labels(language: str) -> dict[str, str]:
    code = language if language in {'en', 'ja', 'ko'} else 'en'
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return json.loads((base / 'locale' / f'{code}.json').read_text(encoding='utf-8'))


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
    """Stream to a same-directory temporary file and verify size and SHA-256."""
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
                            raise ValueError('Downloaded file exceeds GitHub release size')
                        output.write(chunk)
                        digest.update(chunk)
                        progress(min(90, 10 + 80 * received // release.size))
                    break
            else:
                raise ValueError('Too many GitHub download redirects')

        if received != release.size or digest.hexdigest() != release.sha256:
            raise ValueError('Downloaded EXE failed size or SHA-256 verification')
        return download
    except Exception:
        download.unlink(missing_ok=True)
        raise


def _wait_for_parent(pid: int) -> None:
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = ctypes.wintypes.DWORD
    kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

    handle = kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        return
    try:
        result = kernel32.WaitForSingleObject(handle, 30000)
        if result == _WAIT_TIMEOUT:
            raise TimeoutError('The running app did not exit within 30 seconds')
        if result != _WAIT_OBJECT_0:
            raise OSError('Could not wait for the running app to exit')
    finally:
        kernel32.CloseHandle(handle)


def _replace_executable(download: Path, target: Path) -> None:
    for attempt in range(50):
        try:
            os.replace(download, target)
            return
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.2)


_UPDATER_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><style>
*{box-sizing:border-box}body{margin:0;padding:30px;background:#101316;color:#f3f5f2;
font:14px/1.5 'Segoe UI','Malgun Gothic',system-ui,sans-serif}
.card{background:#1e2528;border:1px solid #394447;border-radius:14px;padding:23px;min-height:200px}
.eyebrow{color:#80d4ae;font-size:11px;font-weight:700;letter-spacing:.12em}
h1{font-size:21px;line-height:1.3;margin:12px 0 17px}p{margin:0 0 17px;color:#a2b1b1;min-height:42px}
.track{height:9px;border-radius:9px;background:#30393b;overflow:hidden}
.fill{height:100%;width:0;background:#72d2af;transition:width .2s}
.foot{display:flex;align-items:center;justify-content:space-between;margin-top:17px;color:#a2b1b1;font-size:12px}
button{border:0;border-radius:8px;background:#8be0b7;color:#10241d;font:inherit;font-weight:700;padding:8px 17px;cursor:pointer}
button[hidden]{display:none}body.error .fill{background:#ef8177}
</style></head><body><div class="card"><div class="eyebrow">AI AGENTS USAGE MONITOR</div>
<h1 id="title"></h1><p id="status"></p><div class="track"><div class="fill" id="fill"></div></div>
<div class="foot"><span id="percent">0%</span><button type="button" id="close" hidden></button></div></div>
<script>window.setUpdateState=function(state){document.getElementById('title').textContent=state.title;
document.getElementById('status').textContent=state.message;
document.getElementById('percent').textContent=state.percent+'%';
document.getElementById('fill').style.width=state.percent+'%';
document.body.classList.toggle('error',state.error);
const close=document.getElementById('close');close.textContent=state.close;close.hidden=!state.done;};
document.getElementById('close').addEventListener('click',()=>pywebview.api.close());</script></body></html>"""


def _show_state(window: Any, labels: dict[str, str], message: str, percent: int, done: bool = False, error: bool = False) -> None:
    state = {
        'title': labels['update_window_title'], 'message': message, 'percent': percent,
        'done': done, 'error': error, 'close': labels['update_close'],
    }
    window.evaluate_js(f'window.setUpdateState({json.dumps(state, ensure_ascii=False)})')


def _schedule_helper_cleanup() -> None:
    helper = Path(sys.executable)
    if helper.name != 'AIAgentsUsageMonitor-Updater.exe':
        return
    kernel32 = ctypes.windll.kernel32
    kernel32.MoveFileExW(str(helper), None, _MOVEFILE_DELAY_UNTIL_REBOOT)
    kernel32.MoveFileExW(str(helper.parent), None, _MOVEFILE_DELAY_UNTIL_REBOOT)


def run_update_helper(target_arg: str, expected_version: str, parent_pid_arg: str, language: str) -> int:
    """Show progress in this separate process, then replace the closed app."""
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

    result = 1

    class _CloseApi:
        window: Any = None

        def close(self) -> None:
            self.window.destroy()

    close_api = _CloseApi()
    window = webview.create_window(
        labels['update_window_title'], html=_UPDATER_HTML,
        width=440, height=300, resizable=False, on_top=True,
        background_color='#101316',
        js_api=close_api,
    )
    close_api.window = window

    def worker() -> None:
        nonlocal result
        download: Path | None = None
        try:
            _show_state(window, labels, labels['update_preparing'], 0)
            release = check_latest_release('0.0.0')
            if release is None or release.version != expected_version:
                raise ValueError('The selected GitHub release changed; restart the app to check again')
            _show_state(window, labels, labels['update_downloading'], 10)
            download = _download_asset(release, target.parent, lambda percent: _show_state(window, labels, labels['update_downloading'], percent))
            _show_state(window, labels, labels['update_verifying'], 92)
            _show_state(window, labels, labels['update_waiting'], 95)
            _wait_for_parent(parent_pid)
            _show_state(window, labels, labels['update_installing'], 98)
            _replace_executable(download, target)
            download = None
            result = 0
            _show_state(window, labels, labels['update_complete'].format(version=expected_version), 100, done=True)
        except Exception as exc:
            logger.exception('Automatic update failed')
            _show_state(window, labels, labels['update_failed'].format(reason=str(exc)), 0, done=True, error=True)
        finally:
            if download is not None:
                download.unlink(missing_ok=True)

    window.events.loaded += lambda: threading.Thread(target=worker, daemon=True).start()
    try:
        webview.start()
    finally:
        _schedule_helper_cleanup()
    return result
