"""
Build Script
=============

Builds a standalone EXE for AI Agents Usage Monitor using PyInstaller.

Usage:
    python build.py          compile the glass layer, build the EXE, then run its self-test
    python build.py glass    compile only the glass layer, for running from source

Produces:
    ai_agents_usage_monitor/glass_layer.dll
    dist/AIAgentsUsageMonitor.exe
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ai_agents_usage_monitor.self_test import SELF_TEST_FLAG

ROOT = Path(__file__).parent
DIST = ROOT / 'dist'
SPEC = ROOT / 'ai_agents_usage_monitor.spec'
INIT = ROOT / 'ai_agents_usage_monitor' / '__init__.py'
VERSION_INFO = ROOT / 'version_info.py'
CHANGELOG = ROOT / 'CHANGELOG.md'
GLASS_SOURCE = ROOT / 'ai_agents_usage_monitor' / 'glass_layer.cs'
GLASS_LAYER = ROOT / 'ai_agents_usage_monitor' / 'glass_layer.dll'
EXE = DIST / 'AIAgentsUsageMonitor.exe'
SELF_TEST_TIMEOUT = 120

# Everything that reaches the pixels of screenshot.png, screenshot2.png and screenshot3.png: the version in
# the footer, the theme, the pages and their scripts, the font and the Korean labels. The owner asked on
# 2026-09-27 that any change to them retakes all three, so the pipeline stamps this fingerprint after a retake
# and both the suite (TestScreenshotsAreCurrent) and build() refuse a stale stamp.
SCREENSHOT_INPUTS = [
    'ai_agents_usage_monitor/__init__.py',
    'ai_agents_usage_monitor/theme.json',
    'ai_agents_usage_monitor/popup.py',
    'ai_agents_usage_monitor/popup_data.py',
    'ai_agents_usage_monitor/formatting.py',
    'ai_agents_usage_monitor/updater.py',
    'ai_agents_usage_monitor/update_release.py',
    'ai_agents_usage_monitor/popup/popup.html',
    'ai_agents_usage_monitor/popup/popup.css',
    'ai_agents_usage_monitor/popup/matte.css',
    'ai_agents_usage_monitor/popup/glass.css',
    'ai_agents_usage_monitor/popup/popup.js',
    'ai_agents_usage_monitor/popup/usage-cards.js',
    'ai_agents_usage_monitor/popup/bar-view.js',
    'ai_agents_usage_monitor/popup/updater.html',
    'ai_agents_usage_monitor/popup/Pretendard-Regular.woff2',
    'locale/ko.json',
]
SCREENSHOT_STAMP = ROOT / 'screenshots.sha256'
# Where the three screenshots live, beside the icon and the social preview card; README.md and index.html link them here.
SCREENSHOT_DIR = ROOT / 'assets' / 'images'

# The glass layer builds with the .NET Framework 4 compiler and the Windows
# Runtime metadata that every Windows 10 and 11 installation carries, so
# nothing has to be installed to compile it.
WINDOWS = Path(os.environ.get('SystemRoot', r'C:\Windows'))
CSC = WINDOWS / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
GAC = WINDOWS / 'Microsoft.NET' / 'assembly' / 'GAC_MSIL'
WINMD = WINDOWS / 'System32' / 'WinMetadata'
GLASS_REFERENCES = [
    'System.dll', 'System.Core.dll', 'System.Numerics.dll', 'System.Windows.Forms.dll',
    WINMD / 'Windows.UI.winmd', WINMD / 'Windows.Foundation.winmd', WINMD / 'Windows.Graphics.winmd',
    GAC / 'System.Runtime' / 'v4.0_4.0.0.0__b03f5f7f11d50a3a' / 'System.Runtime.dll',
    GAC / 'System.Runtime.WindowsRuntime' / 'v4.0_4.0.0.0__b77a5c561934e089' / 'System.Runtime.WindowsRuntime.dll',
    GAC / 'System.Numerics.Vectors' / 'v4.0_4.0.0.0__b03f5f7f11d50a3a' / 'System.Numerics.Vectors.dll',
]


def build() -> None:
    """Verify the declared versions agree, compile the glass layer, run PyInstaller, then self-test the EXE."""
    version = check_versions()
    check_screenshots()
    compile_glass_layer()

    print(f'Starting PyInstaller build (version {version}) ...')
    workpath = Path(tempfile.gettempdir()) / 'ai-agents-usage-monitor-build'
    cmd = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--workpath', str(workpath), str(SPEC)]
    subprocess.check_call(cmd, cwd=str(ROOT))

    if not EXE.exists():
        print('\nBuild failed - EXE not found.')
        sys.exit(1)

    self_test(EXE)
    size_mb = EXE.stat().st_size / (1024 * 1024)
    print(f'\nBuild successful!  {EXE}  ({size_mb:.1f} MB)  v{version}')


def self_test(exe: Path) -> None:
    """Start the built EXE in self-test mode and fail the build unless it exits cleanly.

    The unit tests see the source tree; only the EXE shows what PyInstaller
    left out.  A failure before the self-test is reached makes the EXE show
    its error dialog instead of exiting, so a timeout counts as a failure and
    the whole process tree is ended - the one-file bootloader and the Python
    process it started.
    """
    print('Running the built EXE self-test ...')
    process = subprocess.Popen([str(exe), SELF_TEST_FLAG], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        output, errors = process.communicate(timeout=SELF_TEST_TIMEOUT)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], capture_output=True)
        process.communicate()
        print(f'\nBuild failed - the EXE self-test did not finish within {SELF_TEST_TIMEOUT} s; it most likely stopped at an error dialog.')
        sys.exit(1)

    report = (errors or output or '').strip()
    if process.returncode != 0:
        print(report or f'(no output, exit code {process.returncode})')
        print('\nBuild failed - the built EXE did not pass its self-test.')
        sys.exit(1)

    print(report or 'self-test passed')


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


def check_screenshots() -> None:
    """Refuse to build while the screenshots show an app that no longer exists."""
    stamp = SCREENSHOT_STAMP.read_text(encoding='utf-8').strip() if SCREENSHOT_STAMP.is_file() else ''
    if stamp != screenshot_fingerprint():
        print(
            'Build refused - screenshot.png, screenshot2.png and screenshot3.png are older than their inputs.'
            '\nRetake all three with the screenshot pipeline (tests\\screenshots\\make_shots.py),'
            '\nwhich also restamps screenshots.sha256 - see the Versioning section of .claude/CLAUDE.md.'
        )
        sys.exit(1)


def screenshot_fingerprint() -> str:
    """SHA-256 over every screenshot input, with CRLF read as LF so a checkout's line endings are no change."""
    digest = hashlib.sha256()
    for name in SCREENSHOT_INPUTS:
        content = (ROOT / name).read_bytes()
        if not name.endswith('.woff2'):
            content = content.replace(b'\r\n', b'\n')
        digest.update(name.encode('utf-8') + b'\0' + content + b'\0')

    return digest.hexdigest()


if __name__ == '__main__':
    if sys.argv[1:] == ['glass']:
        compile_glass_layer()
    else:
        build()
