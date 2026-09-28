"""
Update Release
==============

Read stable GitHub releases and verify their executable downloads before the
updater asks the running app to quit. This module reads no user settings.
"""
from __future__ import annotations

import hashlib
import os
import re
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests
import truststore

__all__ = [
    'ASSET_NAME', 'RELEASES_PAGE_URL', 'ReleaseInfo', 'VerificationError', 'check_latest_release',
    'download_asset', 'release_highlights', 'verify_executable', 'version_parts',
]

RELEASE_API_URL = 'https://api.github.com/repos/deuxdoom/usage-monitor-for-claude/releases/latest'
RELEASE_DOWNLOAD_PREFIX = 'https://github.com/deuxdoom/usage-monitor-for-claude/releases/download/'
RELEASES_PAGE_URL = 'https://github.com/deuxdoom/usage-monitor-for-claude/releases/latest'
ASSET_NAME = 'AIAgentsUsageMonitor.exe'
MAX_ASSET_SIZE = 200 * 1024 * 1024
MAX_NOTE_ITEMS = 8
_HEADERS = {'Accept': 'application/vnd.github+json', 'User-Agent': 'AI-Agents-Usage-Monitor'}
_VERSION_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)$')
_DIGEST_RE = re.compile(r'^sha256:([0-9a-fA-F]{64})$')
_ALLOWED_ASSET_HOSTS = frozenset({'release-assets.githubusercontent.com', 'objects.githubusercontent.com'})
_IMAGE_SUBSYSTEM_WINDOWS_GUI = 2
_MARKDOWN_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]*\)')
_BOLD_LEAD_RE = re.compile(r'^\*\*(.+?)\*\*\s*(.*)$')


@dataclass(frozen=True)
class ReleaseInfo:
    """The stable release asset and the metadata required to verify it."""

    version: str
    url: str
    sha256: str
    size: int
    notes: str = ''


class VerificationError(ValueError):
    """The downloaded file is not the release's EXE."""


def version_parts(value: str) -> tuple[int, int, int] | None:
    """Parse a stable three-part version, with an optional leading v."""
    match = _VERSION_RE.fullmatch(value)
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def check_latest_release(current_version: str) -> ReleaseInfo | None:
    """Return the newer stable release only when its EXE has a SHA-256 digest."""
    truststore.inject_into_ssl()
    response = requests.get(RELEASE_API_URL, headers=_HEADERS, timeout=(5, 10), allow_redirects=False)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError('Unexpected GitHub release response')
    return _release_info(payload, current_version)


def release_highlights(body: str | None) -> dict[str, Any]:
    """Reduce a release's Markdown notes to the short list the update window shows.

    The notes follow ``RELEASE.md``: an optional bold one-line summary, then
    ``###`` sections of ``- **Label:** text`` bullets.  Sections without
    bullets (the file-hash table, the changelog link) drop out, links keep
    only their text, and at most ``MAX_NOTE_ITEMS`` bullets are kept - the
    rest are counted so the window can point to the full notes.

    Parameters
    ----------
    body : str or None
        The release body as GitHub returns it - null for a release without a description.

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


def download_asset(release: ReleaseInfo, target_dir: Path, progress: Callable[[int], None]) -> Path:
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


def verify_executable(path: Path) -> None:
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


def _release_info(payload: dict[str, Any], current_version: str) -> ReleaseInfo | None:
    tag = payload.get('tag_name')
    if not isinstance(tag, str) or payload.get('draft') or payload.get('prerelease'):
        return None

    latest = version_parts(tag)
    current = version_parts(current_version)
    if latest is None or current is None or latest <= current:
        return None

    assets = payload.get('assets')
    if not isinstance(assets, list):
        return None

    version = '.'.join(str(part) for part in latest)
    expected_url = f'{RELEASE_DOWNLOAD_PREFIX}{tag}/{ASSET_NAME}'
    body = payload.get('body')
    notes = body if isinstance(body, str) else ''
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
        return ReleaseInfo(version, expected_url, match.group(1).lower(), size, notes)

    return None


def _note_item(text: str) -> dict[str, str]:
    text = _MARKDOWN_LINK_RE.sub(r'\1', text.strip())
    match = _BOLD_LEAD_RE.match(text)
    if not match:
        return {'label': '', 'text': _plain(text)}
    return {'label': _plain(match.group(1)).rstrip(':').strip(), 'text': _plain(match.group(2))}


def _plain(text: str) -> str:
    return _MARKDOWN_LINK_RE.sub(r'\1', text).replace('**', '').replace('`', '').strip()


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
