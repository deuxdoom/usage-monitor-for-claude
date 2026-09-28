"""
Color Theme
===========

Loads ``theme.json``, the one file that holds every default color of the app:
the popup and bar palette, the agents' signature colors, the update window's
own surfaces and the tray icon.

``settings.py`` lays the user's overrides over the popup palette and the tray
colors; ``popup_data.py`` assembles the signature colors with the rest of
the palette, and ``updater.py`` builds the update window from the same file.
No other module, stylesheet or page writes a color of its own, so a theme
change is an edit to ``theme.json`` alone.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ['POPUP_COLORS', 'SIGNATURE_COLORS', 'TRAY_ICON_COLORS', 'UPDATER_COLORS']

_THEME: dict[str, Any] = json.loads(Path(__file__).with_name('theme.json').read_text(encoding='utf-8'))

# Defaults of the user-overridable popup colors (``bg``, ``fg``, ``bar_fg``, ...).
POPUP_COLORS: dict[str, str] = _THEME['popup']

# Each agent's color, sent to the page as --claude-signature and --codex-signature.
SIGNATURE_COLORS: dict[str, str] = _THEME['signature']

# What the update window draws beyond the popup palette.
UPDATER_COLORS: dict[str, str] = _THEME['updater']


def _rgba_tuples(colors: dict[str, list[int]]) -> dict[str, tuple[int, ...]]:
    return {name: tuple(rgba) for name, rgba in colors.items()}


# Tray icon defaults as RGBA tuples, keyed 'icon_light' (dark taskbar) and 'icon_dark' (light taskbar).
TRAY_ICON_COLORS: dict[str, dict[str, tuple[int, ...]]] = {
    variant: _rgba_tuples(colors) for variant, colors in _THEME['tray_icon'].items()
}
