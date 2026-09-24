"""Security and compatibility checks for the optional frozen-app updater."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_agents_usage_monitor import updater


def _release_payload(version: str, data: bytes) -> dict:
    tag = f'v{version}'
    return {
        'tag_name': tag, 'draft': False, 'prerelease': False,
        'assets': [{
            'name': updater.ASSET_NAME,
            'state': 'uploaded',
            'size': len(data),
            'digest': 'sha256:' + hashlib.sha256(data).hexdigest(),
            'browser_download_url': f'{updater.RELEASE_DOWNLOAD_PREFIX}{tag}/{updater.ASSET_NAME}',
        }],
    }


class TestReleaseMetadata(unittest.TestCase):
    def test_accepts_newer_stable_release_with_exact_asset_and_digest(self):
        result = updater._release_info(_release_payload('3.1.0', b'new executable'), '3.0.0')
        self.assertEqual(result.version, '3.1.0')
        self.assertEqual(result.size, len(b'new executable'))

    def test_rejects_pre_release_and_non_newer_release(self):
        payload = _release_payload('3.1.0', b'executable')
        payload['prerelease'] = True
        self.assertIsNone(updater._release_info(payload, '3.0.0'))
        self.assertIsNone(updater._release_info(_release_payload('3.0.0', b'executable'), '3.0.0'))

    def test_rejects_other_download_url_or_missing_digest(self):
        payload = _release_payload('3.1.0', b'executable')
        payload['assets'][0]['browser_download_url'] = 'https://example.com/executable.exe'
        self.assertIsNone(updater._release_info(payload, '3.0.0'))
        payload['assets'][0]['browser_download_url'] = (
            f'{updater.RELEASE_DOWNLOAD_PREFIX}v3.1.0/{updater.ASSET_NAME}'
        )
        payload['assets'][0]['digest'] = None
        self.assertIsNone(updater._release_info(payload, '3.0.0'))

    def test_rejects_malformed_asset_list(self):
        payload = _release_payload('3.1.0', b'executable')
        payload['assets'] = {'name': updater.ASSET_NAME}
        self.assertIsNone(updater._release_info(payload, '3.0.0'))

    def test_only_https_github_release_and_asset_redirects_are_allowed(self):
        self.assertTrue(updater._allowed_download_url(
            f'{updater.RELEASE_DOWNLOAD_PREFIX}v3.1.0/{updater.ASSET_NAME}', first_hop=True,
        ))
        self.assertTrue(updater._allowed_download_url('https://release-assets.githubusercontent.com/file'))
        for url in ('http://github.com/file', 'https://evil.example/file',
                    'https://github.com.evil.example/file', 'https://github.com:443/file'):
            self.assertFalse(updater._allowed_download_url(url))


class TestDownload(unittest.TestCase):
    def _response(self, data: bytes) -> MagicMock:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.iter_content.return_value = [data]
        return response

    def test_verified_download_is_written_beside_target(self):
        data = b'MZ\x00test-executable'
        release = updater._release_info(_release_payload('3.1.0', data), '3.0.0')
        with tempfile.TemporaryDirectory() as directory, patch.object(
            updater.requests, 'get', return_value=self._response(data),
        ):
            progress = []
            path = updater._download_asset(release, Path(directory), progress.append)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(path.parent, Path(directory))
            self.assertEqual(progress[-1], 90)

    def test_digest_mismatch_removes_temporary_download(self):
        release = updater._release_info(_release_payload('3.1.0', b'expected'), '3.0.0')
        with tempfile.TemporaryDirectory() as directory, patch.object(
            updater.requests, 'get', return_value=self._response(b'tampered'),
        ):
            with self.assertRaises(ValueError):
                updater._download_asset(release, Path(directory), lambda _value: None)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_redirect_to_untrusted_host_is_rejected_and_cleans_up(self):
        release = updater._release_info(_release_payload('3.1.0', b'expected'), '3.0.0')
        response = self._response(b'')
        response.status_code = 302
        response.headers = {'Location': 'https://evil.example/asset.exe'}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            updater.requests, 'get', return_value=response,
        ) as get:
            with self.assertRaisesRegex(ValueError, 'Unexpected download destination'):
                updater._download_asset(release, Path(directory), lambda _value: None)
            get.assert_called_once()
            self.assertEqual(list(Path(directory).iterdir()), [])


class TestUpdateFlow(unittest.TestCase):
    def test_startup_consent_launches_helper_before_stopping_app(self):
        release = updater.ReleaseInfo('3.1.0', 'https://github.com/asset', '0' * 64, 100)
        monitor = MagicMock(running=True)
        native_ui = MagicMock()
        native_ui.windll.user32.MessageBoxW.return_value = 6
        with patch.object(updater.sys, 'frozen', True, create=True), patch.object(
            updater, 'check_latest_release', return_value=release,
        ), patch.object(updater, 'launch_update_helper') as launch, patch.object(
            updater, 'ctypes', native_ui,
        ):
            updater.check_and_offer_update(monitor)
        launch.assert_called_once()
        monitor.on_quit.assert_called_once()

    def test_refusing_prompt_keeps_app_running(self):
        release = updater.ReleaseInfo('3.1.0', 'https://github.com/asset', '0' * 64, 100)
        monitor = MagicMock(running=True)
        native_ui = MagicMock()
        native_ui.windll.user32.MessageBoxW.return_value = 7
        with patch.object(updater.sys, 'frozen', True, create=True), patch.object(
            updater, 'check_latest_release', return_value=release,
        ), patch.object(updater, 'launch_update_helper') as launch, patch.object(
            updater, 'ctypes', native_ui,
        ):
            updater.check_and_offer_update(monitor)
        launch.assert_not_called()
        monitor.on_quit.assert_not_called()

    def test_helper_launch_failure_keeps_app_running(self):
        release = updater.ReleaseInfo('3.1.0', 'https://github.com/asset', '0' * 64, 100)
        monitor = MagicMock(running=True)
        native_ui = MagicMock()
        native_ui.windll.user32.MessageBoxW.return_value = 6
        with patch.object(updater.sys, 'frozen', True, create=True), patch.object(
            updater, 'check_latest_release', return_value=release,
        ), patch.object(updater, 'launch_update_helper', side_effect=OSError('launch failed')), patch.object(
            updater, 'ctypes', native_ui,
        ):
            updater.check_and_offer_update(monitor)
        monitor.on_quit.assert_not_called()
        self.assertEqual(native_ui.windll.user32.MessageBoxW.call_count, 2)

    def test_verified_file_replaces_target(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            target = folder / updater.ASSET_NAME
            download = folder / '.verified.download'
            target.write_bytes(b'old')
            download.write_bytes(b'new')
            updater._replace_executable(download, target)
            self.assertEqual(target.read_bytes(), b'new')
            self.assertFalse(download.exists())

    def test_failed_replacement_preserves_original_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            target = folder / updater.ASSET_NAME
            download = folder / '.verified.download'
            target.write_bytes(b'old')
            download.write_bytes(b'new')
            with patch.object(updater.os, 'replace', side_effect=PermissionError('in use')), patch.object(
                updater.time, 'sleep', return_value=None,
            ):
                with self.assertRaises(PermissionError):
                    updater._replace_executable(download, target)
            self.assertEqual(target.read_bytes(), b'old')
            self.assertEqual(download.read_bytes(), b'new')


if __name__ == '__main__':
    unittest.main()
