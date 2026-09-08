"""
Codex Installations
====================

Discover native Codex binaries and read CLI and IDE extension versions.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

__all__ = ['CODEX_CHANGELOG_URL', 'CodexInstallations', 'find_binary']

# The Codex repository keeps no changelog file of its own and points readers at
# the release notes instead, so that page is what the popup's link opens.
CODEX_CHANGELOG_URL = 'https://github.com/openai/codex/releases'
_EDITORS = (('VS Code', '.vscode'), ('VS Code Insiders', '.vscode-insiders'), ('Cursor', '.cursor'), ('Windsurf', '.windsurf'))


class CodexInstallations:
    """Read installed versions, caching successful CLI probes by binary mtime."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._versions: dict[tuple[Path, int], str] = {}

    def read(self) -> list[dict[str, str]]:
        """Return available CLI and Codex extension versions for the popup.

        Returns
        -------
        list of dict
            Display names and parsed versions. Unreadable installations are omitted.
        """
        with self._lock:
            installations = []
            try:
                binary = find_binary()
                version = self._version(binary) if binary else ''
                if version:
                    installations.append({'name': 'Codex CLI', 'version': version})
            except OSError:
                pass
            for name, folder in _EDITORS:
                versions = []
                for manifest in (Path.home() / folder / 'extensions').glob('openai.chatgpt-*/package.json'):
                    try:
                        data = json.loads(manifest.read_text(encoding='utf-8'))
                        version = _parse_version(data.get('version')) if isinstance(data, dict) else ''
                        if version:
                            versions.append(version)
                    except (OSError, ValueError):
                        continue
                if versions:
                    version = max(versions, key=lambda value: tuple(int(part) for part in value.split('-', 1)[0].split('.')))
                    installations.append({'name': name + ' (Codex)', 'version': version})
            return installations

    def _version(self, binary: Path) -> str:
        """Probe only native executables and do not cache failed version reads."""
        key = (binary, binary.stat().st_mtime_ns)
        if key in self._versions:
            return self._versions[key]
        try:
            result = subprocess.run([str(binary), '--version'], capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            return ''
        version = _parse_version(result.stdout.removeprefix('codex-cli ').strip()) if result.returncode == 0 else ''
        if version:
            self._versions[key] = version
        return version


def find_binary() -> Path | None:
    """Find a native CLI or IDE binary without executing shell shims.

    Returns
    -------
    Path or None
        Native Windows executable used for account reads and version display.
    """
    found = shutil.which('codex')
    if found and Path(found).suffix.lower() == '.exe':
        return Path(found)
    native = Path.home() / '.local' / 'bin' / 'codex.exe'
    if native.is_file():
        return native
    for name, folder in _EDITORS:
        root = Path.home() / folder / 'extensions'
        candidates = list(root.glob('openai.chatgpt-*/bin/windows-*/codex.exe'))
        if candidates:
            return max(candidates, key=lambda path: path.stat().st_mtime)
    npm = Path(os.environ.get('APPDATA') or Path.home()) / 'npm' / 'node_modules' / '@openai'
    for path in npm.glob('codex*/**/codex.exe'):
        return path
    return None


def _parse_version(value: object) -> str:
    if isinstance(value, str) and re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', value):
        return value
    return ''
