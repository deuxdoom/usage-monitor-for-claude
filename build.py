"""
Build Script
=============

Builds a standalone EXE for AI Agents Usage Monitor using PyInstaller.

Usage:
    python build.py

Produces:
    dist/AIAgentsUsageMonitor.exe
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / 'dist'
SPEC = ROOT / 'ai_agents_usage_monitor.spec'
INIT = ROOT / 'ai_agents_usage_monitor' / '__init__.py'
VERSION_INFO = ROOT / 'version_info.py'
CHANGELOG = ROOT / 'CHANGELOG.md'


def build() -> None:
    """Verify the declared versions agree, then run PyInstaller."""
    version = check_versions()

    print(f'Starting PyInstaller build (version {version}) ...')
    cmd = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', str(SPEC)]
    subprocess.check_call(cmd, cwd=str(ROOT))

    exe = DIST / 'AIAgentsUsageMonitor.exe'
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f'\nBuild successful!  {exe}  ({size_mb:.1f} MB)  v{version}')
    else:
        print('\nBuild failed - EXE not found.')
        sys.exit(1)


def check_versions() -> str:
    """Return the project version, or exit when the sources disagree.

    Windows stamps the EXE with whatever ``version_info.py`` states, and the
    app reports ``__version__``, so a value left behind in either one ships a
    binary that names the previous release.  Nothing in the build output
    reveals that, which is why it is checked here instead: the mismatch has to
    stop the build rather than travel out in a file.

    Returns
    -------
    str
        The agreed version, e.g. ``'1.80.0'``.
    """
    version = read(INIT, r"^__version__ = '([^']+)'")
    if version is None:
        sys.exit(f'Cannot read __version__ from {INIT.name} - nothing to check the build against.')

    expected_four = f'{version}.0'
    declared = {
        'version_info.py  filevers': tuple_version('filevers'),
        'version_info.py  prodvers': tuple_version('prodvers'),
        'version_info.py  FileVersion': read(VERSION_INFO, r"StringStruct\('FileVersion', '([^']+)'\)"),
        'version_info.py  ProductVersion': read(VERSION_INFO, r"StringStruct\('ProductVersion', '([^']+)'\)"),
    }
    mismatches = [(source, found, expected_four) for source, found in declared.items() if found != expected_four]

    heading = read(CHANGELOG, r'^## \[([0-9][^\]]*)\]')
    if heading != version:
        mismatches.append(('CHANGELOG.md  newest heading', heading, version))

    if mismatches:
        print(f'Version mismatch - refusing to build.\n\n  ai_agents_usage_monitor/__init__.py  __version__  {version}\n')
        for source, found, expected in mismatches:
            print(f'  {source}  {found}  <- expected {expected}')
        print(
            '\nEvery source states the version of the release being prepared, including'
            '\nwhile its CHANGELOG.md heading is still pending. Bring them into line and'
            '\nbuild again - see the Versioning section of .claude/CLAUDE.md.'
        )
        sys.exit(1)

    return version


def read(path: Path, pattern: str) -> str | None:
    """Return the first capture of *pattern* in *path*, or None when absent."""
    match = re.search(pattern, path.read_text(encoding='utf-8'), re.MULTILINE)

    return match.group(1) if match else None


def tuple_version(field: str) -> str | None:
    """Return a ``filevers``/``prodvers`` tuple as a dotted string, or None."""
    raw = read(VERSION_INFO, rf'{field}=\(([^)]*)\)')
    if raw is None:
        return None

    return '.'.join(part.strip() for part in raw.split(','))


if __name__ == '__main__':
    build()
