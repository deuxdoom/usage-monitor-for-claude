"""
Build Self-Test
===============

Load, inside the built EXE, everything the app needs before its first window.

The unit tests run against the source tree, where every file of every
installed package is on disk.  The EXE carries only what PyInstaller's
analysis found minus what the spec excludes, so a file the analysis misses or
an exclusion that goes too far breaks the frozen app alone - which is how an
EXE that could not start passed the whole suite during 3.5.0 development
(pywebview looks up the WebView2 loader folders of all three architectures on
import, and two of them had been excluded).  ``build.py`` therefore starts
``AIAgentsUsageMonitor.exe --self-test`` after every build and fails the build
when it does not exit cleanly.

This entry point ships in the application package because it runs inside the
frozen EXE. Its unit tests live in tests/test_self_test.py outside the bundle.

The check opens no window, starts no tray icon, makes no network request and
writes nothing: no settings, no registry, no credentials.
"""
from __future__ import annotations

import io
import json
import re
import sys
import traceback
from pathlib import Path

__all__ = ['SELF_TEST_FLAG', 'run_self_test']

SELF_TEST_FLAG = '--self-test'

_POPUP_DIR = Path(__file__).parent / 'popup'
_PAGES = ('popup.html', 'updater.html')
# Local files a page or stylesheet loads; URLs, data: URIs and fragments carry ':' or '#'.
_REFERENCE = re.compile(r'''(?:href|src)="([^":#]+)"|url\('([^':#]+)'\)''')


def run_self_test() -> int:
    """Run every check and report the outcome on stderr.

    Returns
    -------
    int
        0 when everything loaded, 1 at the first failure.
    """
    try:
        _check_imports()
        _check_page_files()
        _check_locales()
        _check_tray_image()
    except Exception:
        _report(traceback.format_exc())
        return 1

    _report('self-test passed')
    return 0


def _check_imports() -> None:
    """Import the app and the GUI backend ``webview.start()`` picks on Windows, then load the glass layer."""
    import webview.platforms.winforms  # noqa: F401  # pythonnet, WinForms, the WebView2 SDK and its loaders

    from . import app, popup, updater  # noqa: F401
    from . import window_backdrop

    # Private on purpose: this is the load set_glass() performs on first use.
    window_backdrop._glass_layer()


def _check_page_files() -> None:
    """Every local file the popup and updater pages reference, followed through their stylesheets, was bundled."""
    pending = list(_PAGES)
    checked: set[str] = set()
    while pending:
        name = pending.pop()
        if name in checked:
            continue
        checked.add(name)
        path = _POPUP_DIR / name
        if not path.is_file():
            raise FileNotFoundError(f'popup/{name} is not bundled')
        if path.suffix not in ('.html', '.css'):
            continue
        for groups in _REFERENCE.findall(path.read_text(encoding='utf-8')):
            pending.extend(reference for reference in groups if reference)


def _check_locales() -> None:
    """Every bundled translation parses and carries the English keys."""
    from .i18n import LOCALE_DIR

    english = json.loads((LOCALE_DIR / 'en.json').read_text(encoding='utf-8'))
    for path in sorted(LOCALE_DIR.glob('*.json')):
        translation = json.loads(path.read_text(encoding='utf-8'))
        missing = set(english) - set(translation)
        if missing:
            raise KeyError(f'{path.name} lacks {sorted(missing)}')


def _check_tray_image() -> None:
    """Draw a tray icon and encode it as ICO, the format pystray hands to Windows."""
    from .tray_icon import create_icon_image, create_status_image

    for image in (create_icon_image(42, 88, time_pct_top=50), create_status_image('...')):
        image.save(io.BytesIO(), format='ICO')


def _report(text: str) -> None:
    # A windowed EXE started without redirected handles has no stderr.
    if sys.stderr is not None:
        sys.stderr.write(text + '\n')
        sys.stderr.flush()
