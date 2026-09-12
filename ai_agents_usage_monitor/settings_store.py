"""
Settings Store
===============

Write the choices made from the tray menu and the popup back into the settings
file, so the next start opens on the same agent, cadence, typeface and view.

This is the only module in the app that writes a file the user owns, and it is
deliberately conservative about it.  A settings file that cannot be read or
parsed is left untouched rather than replaced: the alternative is discarding
whatever the user wrote there by hand, which costs far more than one lost
menu choice.  Only the keys in ``STORED_KEYS`` are ever written, and every
other key in the file is carried through unchanged.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .settings import SETTINGS_PATH, settings_search_paths

__all__ = ['STORED_KEYS', 'save_setting', 'store_paths']

# The keys the running app writes.  Everything else in the settings file is
# hand-written and only ever read, which is what keeps the file something a
# user can still own after the app has touched it.
STORED_KEYS = frozenset({'poll_interval', 'popup_font', 'popup_view', 'tray_provider'})

# Serializes the read-modify-write cycle.  Choices arrive from the tray menu
# thread and from pywebview's per-call bridge threads, so two saves landing
# together would otherwise each write the file they read before the other.
_write_lock = threading.Lock()


def store_paths() -> list[Path]:
    """Return the files a setting may be written to, in order of preference.

    The file the settings were actually read from comes first, so a choice
    lands beside the keys the user set by hand instead of starting a second
    file that shadows theirs.  The home directory is the fallback for an app
    installed somewhere unwritable (Program Files, a read-only share), where
    the exe-adjacent file cannot be created.

    Returns
    -------
    list[Path]
        One or two absolute paths.  Existence is not checked.
    """
    preferred = SETTINGS_PATH or settings_search_paths()[0]
    fallback = settings_search_paths()[-2]

    return [preferred] if preferred == fallback else [preferred, fallback]


def save_setting(key: str, value: object) -> bool:
    """Store one setting in the settings file, keeping every other key.

    Parameters
    ----------
    key : str
        One of ``STORED_KEYS``.
    value : object
        Any JSON-serializable value the reader in ``settings`` accepts for
        *key*.  A value already stored is a no-op rather than a rewrite.

    Returns
    -------
    bool
        True when the value is stored, False when no candidate file could be
        written or an existing file could not be parsed.  A False is not worth
        interrupting the user for: the choice still applies to the running app,
        it just will not survive a restart.
    """
    assert key in STORED_KEYS, f'{key} is not a stored setting'

    with _write_lock:
        for path in store_paths():
            data = _read(path)
            if data is None:
                return False
            if data.get(key) == value:
                return True
            if _write(path, {**data, key: value}):
                return True

    return False


def _read(path: Path) -> dict | None:
    """Return the file's current contents, ``{}`` when absent, or None on damage."""
    if not path.is_file():
        return {}

    try:
        # utf-8-sig matches how settings.py reads the same file, so a BOM
        # written by an editor does not look like damage here.
        text = path.read_text(encoding='utf-8-sig').strip()
    except OSError:
        return None

    if not text:
        return {}

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    return data if isinstance(data, dict) else None


def _write(path: Path, data: dict) -> bool:
    """Replace *path* with *data* as JSON, atomically where the OS allows it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # The temporary file goes in the target directory because os.replace
        # is only atomic within one volume, and because a directory the app
        # cannot write to must fail here rather than after the original file
        # has already been truncated.
        handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f'{path.name}.', suffix='.tmp')
    except OSError:
        return False

    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write('\n')
        os.replace(temp_name, path)
    except OSError:
        Path(temp_name).unlink(missing_ok=True)
        return False

    return True
