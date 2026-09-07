"""
Command Tests
===============

Unit tests for the command module: subprocess execution with environment variables.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from ai_agents_usage_monitor.command import _STARTUP_FAILURE_WINDOW, run_event_command


class TestRunEventCommand(unittest.TestCase):
    """Tests for run_event_command() subprocess launching."""

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_command_executed_with_shell(self, mock_popen: MagicMock):
        """Command is passed to Popen with shell=True."""
        run_event_command(['echo hello'], {'USAGE_MONITOR_EVENT': 'reset'})

        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], 'echo hello')
        self.assertTrue(kwargs['shell'])

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_env_vars_merged_into_environment(self, mock_popen: MagicMock):
        """Event-specific variables are merged into the process environment."""
        env_vars = {
            'USAGE_MONITOR_EVENT': 'threshold',
            'USAGE_MONITOR_VARIANT': 'five_hour',
            'USAGE_MONITOR_UTILIZATION': '84.5',
        }
        run_event_command(['notify.bat'], env_vars)

        passed_env = mock_popen.call_args[1]['env']
        for key, value in env_vars.items():
            self.assertEqual(passed_env[key], value)

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_version_env_var_always_present(self, mock_popen: MagicMock):
        """USAGE_MONITOR_VERSION is always set from __version__."""
        run_event_command(['test'], {'USAGE_MONITOR_EVENT': 'reset'})

        passed_env = mock_popen.call_args[1]['env']
        from ai_agents_usage_monitor import __version__
        self.assertEqual(passed_env['USAGE_MONITOR_VERSION'], __version__)

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_existing_env_preserved(self, mock_popen: MagicMock):
        """Existing environment variables are preserved alongside new ones."""
        with patch.dict('os.environ', {'PATH': '/usr/bin', 'HOME': '/home/user'}):
            run_event_command(['test'], {'USAGE_MONITOR_EVENT': 'reset'})

        passed_env = mock_popen.call_args[1]['env']
        self.assertEqual(passed_env['PATH'], '/usr/bin')
        self.assertEqual(passed_env['HOME'], '/home/user')
        self.assertEqual(passed_env['USAGE_MONITOR_EVENT'], 'reset')

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_stdout_stderr_devnull(self, mock_popen: MagicMock):
        """stdout and stderr are redirected to DEVNULL."""
        run_event_command(['test'], {'USAGE_MONITOR_EVENT': 'reset'})

        kwargs = mock_popen.call_args[1]
        self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_create_no_window_flag(self, mock_popen: MagicMock):
        """CREATE_NO_WINDOW flag is set."""
        run_event_command(['test'], {'USAGE_MONITOR_EVENT': 'reset'})

        kwargs = mock_popen.call_args[1]
        self.assertEqual(kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_empty_list_skipped(self, mock_popen: MagicMock):
        """Empty command list does not invoke Popen."""
        run_event_command([], {'USAGE_MONITOR_EVENT': 'reset'})

        mock_popen.assert_not_called()

    @patch('ai_agents_usage_monitor.command.traceback.print_exc')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen', side_effect=OSError('not found'))
    def test_popen_exception_caught(self, mock_popen: MagicMock, mock_print_exc: MagicMock):
        """OSError from Popen is caught and printed to stderr."""
        run_event_command(['nonexistent_command'], {'USAGE_MONITOR_EVENT': 'reset'})

        mock_print_exc.assert_called_once()

    @patch('ai_agents_usage_monitor.command.traceback.print_exc')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen', side_effect=ValueError('bad'))
    def test_unexpected_exception_caught(self, mock_popen: MagicMock, mock_print_exc: MagicMock):
        """Unexpected exceptions from Popen are caught and printed to stderr."""
        run_event_command(['bad_command'], {'USAGE_MONITOR_EVENT': 'reset'})

        mock_print_exc.assert_called_once()

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_popen_not_waited(self, mock_popen: MagicMock):
        """Popen result is not waited on (fire-and-forget)."""
        run_event_command(['long_running'], {'USAGE_MONITOR_EVENT': 'reset'})

        mock_process = mock_popen.return_value
        mock_process.wait.assert_not_called()
        mock_process.communicate.assert_not_called()

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_cwd_set_to_project_root(self, mock_popen: MagicMock):
        """Working directory is set to the project root (non-frozen)."""
        run_event_command(['test'], {'USAGE_MONITOR_EVENT': 'reset'})

        kwargs = mock_popen.call_args[1]
        expected = Path(__file__).resolve().parent.parent
        self.assertEqual(kwargs['cwd'], expected)

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    @patch('ai_agents_usage_monitor.command.sys')
    def test_cwd_set_to_executable_dir_when_frozen(self, mock_sys: MagicMock, mock_popen: MagicMock):
        """Working directory is set to the executable's folder when frozen."""
        mock_sys.frozen = True
        mock_sys.executable = 'C:\\Program Files\\MyApp\\app.exe'

        run_event_command(['test'], {'USAGE_MONITOR_EVENT': 'reset'})

        kwargs = mock_popen.call_args[1]
        self.assertEqual(kwargs['cwd'], Path('C:\\Program Files\\MyApp'))

    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_multiple_commands_all_executed(self, mock_popen: MagicMock):
        """All commands in the list are launched."""
        run_event_command(['cmd1', 'cmd2', 'cmd3'], {'USAGE_MONITOR_EVENT': 'reset'})

        self.assertEqual(mock_popen.call_count, 3)
        executed = [call[0][0] for call in mock_popen.call_args_list]
        self.assertEqual(executed, ['cmd1', 'cmd2', 'cmd3'])

    @patch('ai_agents_usage_monitor.command.traceback.print_exc')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_one_failure_does_not_block_others(self, mock_popen: MagicMock, mock_print_exc: MagicMock):
        """A failing command does not prevent subsequent commands from running."""
        mock_popen.side_effect = [OSError('fail'), MagicMock()]

        run_event_command(['bad', 'good'], {'USAGE_MONITOR_EVENT': 'reset'})

        self.assertEqual(mock_popen.call_count, 2)
        mock_print_exc.assert_called_once()


class TestRunEventCommandCaptureOutput(unittest.TestCase):
    """Tests for the capture_output path used by the 'Test event commands' menu."""

    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_capture_output_uses_pipes(self, mock_popen: MagicMock, _thread: MagicMock):
        """With capture_output, stdout and stderr are captured via PIPE (not DEVNULL)."""
        run_event_command(['echo hi'], {'USAGE_MONITOR_EVENT': 'reset'}, capture_output=True)

        kwargs = mock_popen.call_args[1]
        self.assertEqual(kwargs['stdout'], subprocess.PIPE)
        self.assertEqual(kwargs['stderr'], subprocess.PIPE)
        self.assertTrue(kwargs['text'])
        self.assertEqual(kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)

    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_capture_output_reports_on_background_daemon_thread(self, mock_popen: MagicMock, mock_thread: MagicMock):
        """The wait/report runs on a started daemon thread, so the caller is not blocked."""
        run_event_command(['echo hi'], {'USAGE_MONITOR_EVENT': 'reset'}, capture_output=True)

        self.assertTrue(mock_thread.call_args[1]['daemon'])
        mock_thread.return_value.start.assert_called_once()

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_capture_output_prints_streams_and_exit_code(self, mock_popen: MagicMock, mock_thread: MagicMock, mock_print: MagicMock, _ctypes: MagicMock):
        """Once the command exits, its stdout, stderr, and exit code are printed."""
        mock_popen.return_value.communicate.return_value = ('hello out', 'boom err')
        mock_popen.return_value.returncode = 9

        run_event_command(['bad'], {'USAGE_MONITOR_EVENT': 'reset'}, capture_output=True)

        # Run the report body synchronously (it would otherwise run on the daemon thread).
        mock_thread.call_args[1]['target']()

        printed = '\n'.join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn('hello out', printed)
        self.assertIn('boom err', printed)
        self.assertIn('9', printed)

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_capture_output_reports_empty_streams(self, mock_popen: MagicMock, mock_thread: MagicMock, mock_print: MagicMock, _ctypes: MagicMock):
        """Empty output still reports (no crash), marking streams as empty."""
        mock_popen.return_value.communicate.return_value = ('', '')
        mock_popen.return_value.returncode = 0

        run_event_command(['ok'], {'USAGE_MONITOR_EVENT': 'reset'}, capture_output=True)
        mock_thread.call_args[1]['target']()

        printed = '\n'.join(str(call.args[0]) for call in mock_print.call_args_list)
        self.assertIn('(empty)', printed)

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_capture_output_shows_error_box_on_nonzero_exit(self, mock_popen: MagicMock, mock_thread: MagicMock, mock_print: MagicMock, mock_ctypes: MagicMock):
        """A non-zero exit code raises an error message box containing stderr."""
        mock_popen.return_value.communicate.return_value = ('', 'the failure detail')
        mock_popen.return_value.returncode = 2

        run_event_command(['bad'], {'USAGE_MONITOR_EVENT': 'reset'}, capture_output=True)
        mock_thread.call_args[1]['target']()

        mock_ctypes.windll.user32.MessageBoxW.assert_called_once()
        box_message = mock_ctypes.windll.user32.MessageBoxW.call_args[0][1]
        self.assertIn('the failure detail', box_message)
        self.assertIn('2', box_message)

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_capture_output_no_error_box_on_success(self, mock_popen: MagicMock, mock_thread: MagicMock, mock_print: MagicMock, mock_ctypes: MagicMock):
        """A zero exit code shows no error box."""
        mock_popen.return_value.communicate.return_value = ('done', '')
        mock_popen.return_value.returncode = 0

        run_event_command(['ok'], {'USAGE_MONITOR_EVENT': 'reset'}, capture_output=True)
        mock_thread.call_args[1]['target']()

        mock_ctypes.windll.user32.MessageBoxW.assert_not_called()


class TestLateFailureReporting(unittest.TestCase):
    """Tests that a program launched by the quick action can exit quietly later.

    A quick action usually starts something the user then keeps open. When that
    program exits non-zero hours later - crashed, killed, or replaced by a
    second instance - a dialog has no visible connection to the click that
    started it. A wrong path still fails at once and is still reported.
    """

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    def test_immediate_failure_is_reported_even_when_late_ones_are_not(self, mock_popen, mock_thread, _print, mock_ctypes):
        mock_popen.return_value.communicate.return_value = ('', 'not found')
        mock_popen.return_value.returncode = 1

        run_event_command(['bad.exe'], {}, capture_output=True, report_late_failures=False)
        mock_thread.call_args[1]['target']()

        mock_ctypes.windll.user32.MessageBoxW.assert_called_once()

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    @patch('ai_agents_usage_monitor.command.time.monotonic')
    def test_late_failure_is_silent_when_not_requested(self, mock_clock, mock_popen, mock_thread, _print, mock_ctypes):
        # Launch at 0, exit well past the startup window.
        mock_clock.side_effect = [0.0, _STARTUP_FAILURE_WINDOW + 3600]
        mock_popen.return_value.communicate.return_value = ('', 'closed by user')
        mock_popen.return_value.returncode = 1

        run_event_command(['app.exe'], {}, capture_output=True, report_late_failures=False)
        mock_thread.call_args[1]['target']()

        mock_ctypes.windll.user32.MessageBoxW.assert_not_called()

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    @patch('ai_agents_usage_monitor.command.time.monotonic')
    def test_late_failure_is_reported_by_default(self, mock_clock, mock_popen, mock_thread, _print, mock_ctypes):
        """The 'Test event commands' menu asked for the result, so it always gets it."""
        mock_clock.side_effect = [0.0, _STARTUP_FAILURE_WINDOW + 3600]
        mock_popen.return_value.communicate.return_value = ('', 'boom')
        mock_popen.return_value.returncode = 1

        run_event_command(['app.exe'], {}, capture_output=True)
        mock_thread.call_args[1]['target']()

        mock_ctypes.windll.user32.MessageBoxW.assert_called_once()

    @patch('ai_agents_usage_monitor.command.ctypes')
    @patch('builtins.print')
    @patch('ai_agents_usage_monitor.command.threading.Thread')
    @patch('ai_agents_usage_monitor.command.subprocess.Popen')
    @patch('ai_agents_usage_monitor.command.time.monotonic')
    def test_late_success_is_silent(self, mock_clock, mock_popen, mock_thread, _print, mock_ctypes):
        mock_clock.side_effect = [0.0, _STARTUP_FAILURE_WINDOW + 3600]
        mock_popen.return_value.communicate.return_value = ('bye', '')
        mock_popen.return_value.returncode = 0

        run_event_command(['app.exe'], {}, capture_output=True, report_late_failures=False)
        mock_thread.call_args[1]['target']()

        mock_ctypes.windll.user32.MessageBoxW.assert_not_called()


if __name__ == '__main__':
    unittest.main()
