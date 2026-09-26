"""
Build Script
=============

Builds a standalone EXE for AI Agents Usage Monitor using PyInstaller.

Usage:
    python build.py          compile the glass layer, then build the EXE
    python build.py glass    compile only the glass layer, for running from source

Produces:
    ai_agents_usage_monitor/glass_layer.dll
    dist/AIAgentsUsageMonitor.exe
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / 'dist'
SPEC = ROOT / 'ai_agents_usage_monitor.spec'
INIT = ROOT / 'ai_agents_usage_monitor' / '__init__.py'
VERSION_INFO = ROOT / 'version_info.py'
CHANGELOG = ROOT / 'CHANGELOG.md'
GLASS_SOURCE = ROOT / 'ai_agents_usage_monitor' / 'glass_layer.cs'
GLASS_LAYER = ROOT / 'ai_agents_usage_monitor' / 'glass_layer.dll'

# The glass layer builds with the .NET Framework 4 compiler and the Windows
# Runtime metadata that every Windows 10 and 11 installation carries, so
# nothing has to be installed to compile it.
WINDOWS = Path(os.environ.get('SystemRoot', r'C:\Windows'))
CSC = WINDOWS / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
GAC = WINDOWS / 'Microsoft.NET' / 'assembly' / 'GAC_MSIL'
WINMD = WINDOWS / 'System32' / 'WinMetadata'
GLASS_REFERENCES = [
    'System.dll', 'System.Core.dll', 'System.Numerics.dll',
    WINMD / 'Windows.UI.winmd', WINMD / 'Windows.Foundation.winmd', WINMD / 'Windows.Graphics.winmd',
    GAC / 'System.Runtime' / 'v4.0_4.0.0.0__b03f5f7f11d50a3a' / 'System.Runtime.dll',
    GAC / 'System.Runtime.WindowsRuntime' / 'v4.0_4.0.0.0__b77a5c561934e089' / 'System.Runtime.WindowsRuntime.dll',
    GAC / 'System.Numerics.Vectors' / 'v4.0_4.0.0.0__b03f5f7f11d50a3a' / 'System.Numerics.Vectors.dll',
]


def build() -> None:
    """Verify the declared versions agree, compile the glass layer, then run PyInstaller."""
    version = check_versions()
    compile_glass_layer()

    print(f'Starting PyInstaller build (version {version}) ...')
    workpath = Path(tempfile.gettempdir()) / 'ai-agents-usage-monitor-build'
    cmd = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--workpath', str(workpath), str(SPEC)]
    subprocess.check_call(cmd, cwd=str(ROOT))

    exe = DIST / 'AIAgentsUsageMonitor.exe'
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f'\nBuild successful!  {exe}  ({size_mb:.1f} MB)  v{version}')
    else:
        print('\nBuild failed - EXE not found.')
        sys.exit(1)


def compile_glass_layer() -> None:
    """Compile ``glass_layer.cs`` into the library the glass material loads.

    The library is built from the source in this repository on every build
    rather than kept as a binary, so what ships is always the code that can be
    read.  It lands next to ``window_backdrop.py``, where the spec file picks
    it up and a run from source finds it.
    """
    print('Compiling the glass layer ...')
    references = [f'-r:{reference}' for reference in GLASS_REFERENCES]
    cmd = [str(CSC), '-nologo', '-optimize+', '-platform:x64', '-target:library', f'-out:{GLASS_LAYER}', *references, str(GLASS_SOURCE)]
    subprocess.check_call(cmd, cwd=str(ROOT))


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
    if sys.argv[1:] == ['glass']:
        compile_glass_layer()
    else:
        build()
