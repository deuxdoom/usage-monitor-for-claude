"""Codex Installation Tests
========================

Verify version discovery without network access or shell shims.
"""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from ai_agents_usage_monitor.codex_cli import CodexInstallations, _parse_version, find_binary


class TestCodexInstallations(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / 'codex.exe'
        self.binary.touch()
        self.reader = CodexInstallations()
        patch('ai_agents_usage_monitor.codex_cli.Path.home', return_value=self.root).start()
        self.addCleanup(patch.stopall)

    def test_cli_version_cache_tracks_mtime(self):
        with patch('ai_agents_usage_monitor.codex_cli.find_binary', return_value=self.binary):
            with patch('ai_agents_usage_monitor.codex_cli.subprocess.run', return_value=Mock(returncode=0, stdout='codex-cli 0.153.0\n')) as run:
                self.assertEqual(self.reader.read(), [{'name': 'Codex CLI', 'version': '0.153.0'}])
                self.reader.read()
                run.assert_called_once()
                stat = self.binary.stat()
                os.utime(self.binary, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
                self.reader.read()
                self.assertEqual(run.call_count, 2)

    def test_failed_version_is_retried(self):
        with patch('ai_agents_usage_monitor.codex_cli.find_binary', return_value=self.binary):
            with patch('ai_agents_usage_monitor.codex_cli.subprocess.run', side_effect=[subprocess.TimeoutExpired('codex', 5), Mock(returncode=0, stdout='codex-cli 0.153.0')]):
                self.assertEqual(self.reader.read(), [])
                self.assertTrue(self.reader.read())

    def test_extensions_use_manifest_versions_not_directory_names(self):
        for name, version in (('old', '26.9.1'), ('new', '26.10.1'), ('broken', 'not a version')):
            folder = self.root / '.vscode' / 'extensions' / ('openai.chatgpt-' + name)
            folder.mkdir(parents=True)
            (folder / 'package.json').write_text(json.dumps({'version': version}), encoding='utf-8')
        with patch('ai_agents_usage_monitor.codex_cli.find_binary', return_value=None):
            self.assertEqual(self.reader.read(), [{'name': 'VS Code (Codex)', 'version': '26.10.1'}])

    def test_only_native_binary_is_selected(self):
        native = self.root / '.local' / 'bin' / 'codex.exe'
        native.parent.mkdir(parents=True)
        native.touch()
        with patch('ai_agents_usage_monitor.codex_cli.shutil.which', return_value='codex.cmd'):
            self.assertEqual(find_binary(), native)

    def test_version_parser_rejects_arbitrary_output(self):
        for value in (None, [], 'failed 0.153.0', '0.153.0\nsecret'):
            self.assertEqual(_parse_version(value), '')
        self.assertEqual(_parse_version('0.153.0-alpha.1'), '0.153.0-alpha.1')
