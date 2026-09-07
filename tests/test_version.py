"""
Version Tests
==============

Guards the one invariant that no other test can observe: every place the
project writes its version down says the same thing.

The EXE is stamped from ``version_info.py`` while the app reports
``__version__``, and the release being prepared is named by the newest
``CHANGELOG.md`` heading.  A value left behind in any one of them ships a
binary that names the wrong release, and nothing about the build output or
the running app makes that visible until the file is already in someone's
hands.
"""
from __future__ import annotations

import unittest

from build import CHANGELOG, INIT, VERSION_INFO, read, tuple_version
from ai_agents_usage_monitor import __version__


class TestVersionSources(unittest.TestCase):
    """Tests that __version__, version_info.py and CHANGELOG.md agree."""

    def test_every_source_file_exists(self):
        for path in (INIT, VERSION_INFO, CHANGELOG):
            self.assertTrue(path.is_file(), path)

    def test_init_matches_the_imported_version(self):
        self.assertEqual(read(INIT, r"^__version__ = '([^']+)'"), __version__)

    def test_version_info_fields_match(self):
        """All four Windows resource fields carry __version__ with a trailing .0."""
        expected = f'{__version__}.0'
        self.assertEqual(tuple_version('filevers'), expected)
        self.assertEqual(tuple_version('prodvers'), expected)
        self.assertEqual(read(VERSION_INFO, r"StringStruct\('FileVersion', '([^']+)'\)"), expected)
        self.assertEqual(read(VERSION_INFO, r"StringStruct\('ProductVersion', '([^']+)'\)"), expected)

    def test_newest_changelog_heading_matches(self):
        """The version being prepared is bumped when its heading is opened, not at release.

        Waiting until the release to bump leaves every build made during the
        pending period stamped with the previous version.
        """
        self.assertEqual(read(CHANGELOG, r'^## \[([0-9][^\]]*)\]'), __version__)


if __name__ == '__main__':
    unittest.main()
