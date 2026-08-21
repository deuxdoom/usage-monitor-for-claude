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

__all__ = ['LOCALE_DIR', 'detect_lang_code', 'load_translations', 'T']

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


def load_translations() -> dict[str, Any]:
    """Load translations for the configured or detected system language, fallback to English."""
    from .settings import LANGUAGE

    if LANGUAGE:
        lang_file = LOCALE_DIR / f'{LANGUAGE}.json'
        if lang_file.exists():
            return json.loads(lang_file.read_text(encoding='utf-8'))

    lang = locale.getlocale()[0] or ''
    lang_code = detect_lang_code(lang)

    return json.loads((LOCALE_DIR / f'{lang_code}.json').read_text(encoding='utf-8'))


T: dict[str, Any] = load_translations()
