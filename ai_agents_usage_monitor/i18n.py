"""
Internationalization
=====================

Loads translations for the detected system language with English fallback.
"""
from __future__ import annotations

import json
import locale
from pathlib import Path
from typing import Any

__all__ = ['LANG_CODE', 'LOCALE_DIR', 'active_lang_code', 'detect_lang_code', 'load_translations', 'T']

LOCALE_DIR = Path(__file__).parent.parent / 'locale'


def detect_lang_code(lang: str) -> str:
    """Detect locale file code from system locale string using convention-based lookup.

    Lookup chain: ``{lang}.json`` → ``en.json``.  No mapping table - the
    locale directory *is* the configuration, so a system language without a
    shipped file (anything but Japanese and Korean) lands on English.

    Parameters
    ----------
    lang : str
        System locale string, e.g. ``'ko_KR'`` or ``'Korean_Korea'``.

    Returns
    -------
    str
        Locale file code (without ``.json``).
    """
    normalized = locale.normalize(lang).split('.')[0]
    parts = normalized.split('_', 1)
    base = parts[0].lower()

    # On Windows, os.getlocale() returns e.g. 'Korean_Korea', and locale.normalize() fails to rewrite it to an ISO code,
    # so base becomes 'korean'. Re-split using 'korean' to hopefully trigger a match.
    if len(base) > 3:
        base = locale.normalize(parts[0]).split('.')[0].split('_')[0].lower()

    if (LOCALE_DIR / f'{base}.json').exists():
        return base

    return 'en'


def active_lang_code() -> str:
    """Return the locale code the translations are loaded from.

    The popup's clock formats its date and time against this code rather than
    the system locale, so a user who overrode ``language`` reads the clock in
    the same language as the rest of the window.

    Returns
    -------
    str
        A code with a shipped locale file, e.g. ``'ko'``.
    """
    from .settings import LANGUAGE

    if LANGUAGE and (LOCALE_DIR / f'{LANGUAGE}.json').exists():
        return LANGUAGE

    return detect_lang_code(locale.getlocale()[0] or '')


def load_translations() -> dict[str, Any]:
    """Load translations for the configured or detected system language, fallback to English."""
    return json.loads((LOCALE_DIR / f'{active_lang_code()}.json').read_text(encoding='utf-8'))


LANG_CODE: str = active_lang_code()
T: dict[str, Any] = load_translations()
