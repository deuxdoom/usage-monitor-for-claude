"""
Settings Store Tests
======================

Unit tests for writing the tray menu's and popup's choices back to the settings
file: which file is chosen, what is preserved, and what is refused.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ai_agents_usage_monitor.settings_store as store


def _paths(*paths: Path):
    """Patch the candidate list save_setting writes to."""
    return patch.object(store, 'store_paths', return_value=list(paths))


class TestStorePaths(unittest.TestCase):
    """Which file the app's own choices land in."""

    def test_prefers_the_file_the_settings_were_read_from(self):
        """A choice belongs beside the keys the user set by hand, not in a second file."""
        existing = Path('C:/somewhere/config.json')
        with patch.object(store, 'SETTINGS_PATH', existing):
            self.assertEqual(store.store_paths()[0], existing)

    def test_falls_back_to_the_first_search_path_when_no_file_exists(self):
        """With nothing on disk, the writer creates the file the reader looks at first."""
        candidates = [Path('C:/app/config.json'), Path('C:/app/legacy.json'), Path('C:/home/config.json')]
        with patch.object(store, 'SETTINGS_PATH', None), \
             patch.object(store, 'settings_search_paths', return_value=candidates):
            self.assertEqual(store.store_paths()[0], candidates[0])

    def test_offers_the_home_directory_as_a_fallback(self):
        """An app installed somewhere unwritable still has somewhere to store a choice."""
        candidates = [Path('C:/app/config.json'), Path('C:/app/legacy.json'), Path('C:/home/config.json')]
        with patch.object(store, 'SETTINGS_PATH', None), \
             patch.object(store, 'settings_search_paths', return_value=candidates):
            self.assertEqual(store.store_paths(), [candidates[0], candidates[-2]])

    def test_no_duplicate_when_the_two_are_the_same_file(self):
        """Nothing is gained by trying the same path twice."""
        home = Path('C:/home/config.json')
        candidates = [home, Path('C:/home/legacy.json')]
        with patch.object(store, 'SETTINGS_PATH', None), \
             patch.object(store, 'settings_search_paths', return_value=candidates):
            self.assertEqual(store.store_paths(), [home])


class TestSaveSetting(unittest.TestCase):
    """Storing one value without disturbing the rest of the file."""

    def test_creates_the_file_when_none_exists(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            with _paths(target):
                self.assertTrue(store.save_setting('tray_provider', 'codex'))
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'tray_provider': 'codex'})

    def test_keeps_every_hand_written_key(self):
        """The file is the user's; the app only ever adds its own keys to it."""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text(json.dumps({'bg': '#000000', 'alert_thresholds_five_hour': [50, 90]}), encoding='utf-8')
            with _paths(target):
                store.save_setting('popup_font', 'pixel')
            self.assertEqual(
                json.loads(target.read_text(encoding='utf-8')),
                {'bg': '#000000', 'alert_thresholds_five_hour': [50, 90], 'popup_font': 'pixel'},
            )

    def test_replaces_a_previous_value_of_the_same_key(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text(json.dumps({'poll_interval': 60}), encoding='utf-8')
            with _paths(target):
                store.save_setting('poll_interval', 300)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'poll_interval': 300})

    def test_an_unchanged_value_is_not_rewritten(self):
        """Re-picking the current choice must not rewrite the user's file."""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text('{"poll_interval": 60}', encoding='utf-8')
            before = target.stat().st_mtime_ns
            with _paths(target):
                self.assertTrue(store.save_setting('poll_interval', 60))
            self.assertEqual(target.stat().st_mtime_ns, before)
            self.assertEqual(target.read_text(encoding='utf-8'), '{"poll_interval": 60}')

    def test_an_empty_file_is_treated_as_no_settings(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text('   \n', encoding='utf-8')
            with _paths(target):
                self.assertTrue(store.save_setting('popup_view', 'bar'))
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')), {'popup_view': 'bar'})

    def test_a_bom_is_not_mistaken_for_damage(self):
        """Editors write a BOM; settings.py reads through one, so this must too."""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_bytes(b'\xef\xbb\xbf' + json.dumps({'bg': '#123456'}).encode('utf-8'))
            with _paths(target):
                self.assertTrue(store.save_setting('popup_font', 'system'))
            self.assertEqual(
                json.loads(target.read_text(encoding='utf-8')), {'bg': '#123456', 'popup_font': 'system'},
            )

    def test_unicode_is_stored_readably(self):
        """A path or name in the file stays legible after the app rewrites it."""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text(json.dumps({'cli_command': {'왼쪽': ['wsl', 'claude']}}, ensure_ascii=False), encoding='utf-8')
            with _paths(target):
                store.save_setting('popup_view', 'bar')
            self.assertIn('왼쪽', target.read_text(encoding='utf-8'))

    def test_a_key_the_app_does_not_own_is_refused(self):
        """Only the menu's own choices are writable - everything else is read-only."""
        with self.assertRaises(AssertionError):
            store.save_setting('bg', '#000000')


class TestDamagedFile(unittest.TestCase):
    """A file that cannot be parsed is left exactly as it is."""

    def test_invalid_json_is_never_overwritten(self):
        """Rewriting it would throw away whatever the user was in the middle of writing."""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text('{"bg": "#000000",', encoding='utf-8')
            with _paths(target):
                self.assertFalse(store.save_setting('popup_font', 'pixel'))
            self.assertEqual(target.read_text(encoding='utf-8'), '{"bg": "#000000",')

    def test_a_json_array_is_not_a_settings_file(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text('[1, 2, 3]', encoding='utf-8')
            with _paths(target):
                self.assertFalse(store.save_setting('popup_font', 'pixel'))
            self.assertEqual(target.read_text(encoding='utf-8'), '[1, 2, 3]')

    def test_damage_does_not_send_the_choice_to_the_fallback_file(self):
        """Splitting the settings across two files is worse than not storing one choice."""
        with TemporaryDirectory() as tmp:
            damaged = Path(tmp) / 'config.json'
            fallback = Path(tmp) / 'home.json'
            damaged.write_text('not json', encoding='utf-8')
            with _paths(damaged, fallback):
                self.assertFalse(store.save_setting('popup_font', 'pixel'))
            self.assertFalse(fallback.exists())


class TestUnwritableTarget(unittest.TestCase):
    """An install that cannot be written to falls back rather than losing the choice."""

    def test_falls_back_to_the_next_candidate(self):
        with TemporaryDirectory() as tmp:
            blocked = Path(tmp) / 'blocked' / 'config.json'
            fallback = Path(tmp) / 'home' / 'config.json'
            with _paths(blocked, fallback), \
                 patch.object(store, '_write', side_effect=[False, True]) as mock_write:
                self.assertTrue(store.save_setting('popup_view', 'bar'))
            self.assertEqual([call.args[0] for call in mock_write.call_args_list], [blocked, fallback])

    def test_returns_false_when_no_candidate_can_be_written(self):
        with TemporaryDirectory() as tmp:
            first = Path(tmp) / 'a' / 'config.json'
            second = Path(tmp) / 'b' / 'config.json'
            with _paths(first, second), patch.object(store, '_write', return_value=False):
                self.assertFalse(store.save_setting('popup_view', 'bar'))

    def test_a_failed_write_leaves_no_temporary_file_behind(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'config.json'
            target.write_text('{}', encoding='utf-8')
            with patch.object(store.os, 'replace', side_effect=OSError('denied')):
                self.assertFalse(store._write(target, {'popup_view': 'bar'}))
            self.assertEqual([entry.name for entry in Path(tmp).iterdir()], ['config.json'])

    def test_a_missing_directory_is_created(self):
        """The home fallback lands in ~/.claude/, which need not exist yet."""
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / 'claude' / 'config.json'
            with _paths(target):
                self.assertTrue(store.save_setting('popup_font', 'system'))
            self.assertTrue(target.is_file())


class TestStoredKeys(unittest.TestCase):
    """What the app is allowed to write."""

    def test_covers_every_choice_the_menus_offer(self):
        self.assertEqual(
            store.STORED_KEYS,
            frozenset({'poll_interval', 'popup_font', 'popup_view', 'tray_provider'}),
        )

    def test_every_stored_key_is_one_the_reader_understands(self):
        """A key written here that settings.py drops would be stored and then ignored."""
        from ai_agents_usage_monitor import settings

        values = {
            'poll_interval': 180, 'popup_font': 'pixel', 'popup_view': 'bar', 'tray_provider': 'codex',
        }
        for font in settings.POPUP_FONTS:
            with self.subTest(font=font), patch.object(settings, 'ctypes'):
                values['popup_font'] = font
                validated = settings._validate(dict(values), Path('config.json'))
                self.assertEqual(validated, values)


if __name__ == '__main__':
    unittest.main()
