#!/usr/bin/env python3
"""
test_odoo_config.py - Unit tests for the odoo_config.py script.

This test suite ensures that the odoo_config.py script functions as expected,
including setting default values, getting and setting configuration values,
and handling admin password and Redis configuration.

Author: Troy Kelly
Contact: troy@aperim.com

History:
    2024-09-14: Initial creation of comprehensive test suite for updated odoo_config.py.
    2024-09-15: Updated tests to accommodate refactored REDIS_DEFAULTS computation.
"""

import os
import signal
import sys
import unittest
from typing import Dict, Optional
from unittest.mock import MagicMock, mock_open, patch

# Import the module to test
sys.path.append(os.path.abspath('tools/src'))
import odoo_config  # noqa: E402


class TestOdooConfig(unittest.TestCase):
    """Unit tests for odoo_config.py."""

    def setUp(self) -> None:
        """Set up mocks and initial conditions for tests."""
        # Mock the CONFIG_FILE_PATH
        self.config_file_path = '/tmp/odoo.conf'
        odoo_config.CONFIG_FILE_PATH = self.config_file_path
        odoo_config.LOCK_FILE_PATH = self.config_file_path + '.lock'

        # Ensure the config file does not exist before each test
        if os.path.exists(self.config_file_path):
            os.remove(self.config_file_path)
        if os.path.exists(self.config_file_path + '.lock'):
            os.remove(self.config_file_path + '.lock')

        # Mock environment variables
        self.env_patcher = patch.dict('os.environ', {
            'REDIS_PASSWORD': 'redis_pass',
            'ODOO_MASTER_PASSWORD': 'master_pass',
        })
        self.env_patcher.start()

    def tearDown(self) -> None:
        """Clean up after tests."""
        # Stop all patches
        self.env_patcher.stop()

        # Remove the config file after each test
        if os.path.exists(self.config_file_path):
            os.remove(self.config_file_path)

    @patch('os.fsync')
    @patch('fcntl.flock')
    @patch('os.makedirs')
    @patch('os.fdopen')
    @patch('os.open')
    @patch('builtins.open', new_callable=mock_open)
    def test_ensure_config_file_exists_creates_file(self, mock_open_file: MagicMock, mock_os_open: MagicMock, mock_fdopen: MagicMock, mock_makedirs: MagicMock, mock_flock: MagicMock, mock_fsync: MagicMock) -> None:
        """Test that ensure_config_file_exists creates the config file with [options] section when it does not exist."""
        mock_os_open.return_value = 3
        tmp_handle = MagicMock()
        tmp_handle.read.return_value = ''
        mock_fdopen.return_value.__enter__.return_value = tmp_handle

        odoo_config.ensure_config_file_exists()

        mock_open_file.assert_called_with(self.config_file_path + '.lock', 'a', encoding='utf-8')
        mock_os_open.assert_called_with(self.config_file_path, os.O_RDWR | os.O_CREAT)
        mock_fdopen.assert_called_with(3, 'r+', encoding='utf-8')
        tmp_handle.write.assert_called_once_with('[options]\n')
        self.assertEqual(mock_flock.call_count, 2)
        print("Test ensure_config_file_exists_creates_file passed.")

    @patch('os.fsync')
    @patch('fcntl.flock')
    @patch('os.makedirs')
    @patch('os.fdopen')
    @patch('os.open')
    @patch('builtins.open', new_callable=mock_open)
    def test_ensure_config_file_exists_adds_options_section(self, mock_open_file: MagicMock, mock_os_open: MagicMock, mock_fdopen: MagicMock, mock_makedirs: MagicMock, mock_flock: MagicMock, mock_fsync: MagicMock) -> None:
        """Test that ensure_config_file_exists adds [options] section if missing."""
        mock_os_open.return_value = 3
        tmp_handle = MagicMock()
        tmp_handle.read.return_value = '[other_section]\nkey=value\n'
        mock_fdopen.return_value.__enter__.return_value = tmp_handle

        odoo_config.ensure_config_file_exists()

        mock_open_file.assert_called_with(self.config_file_path + '.lock', 'a', encoding='utf-8')
        mock_os_open.assert_called_with(self.config_file_path, os.O_RDWR | os.O_CREAT)
        mock_fdopen.assert_called_with(3, 'r+', encoding='utf-8')
        tmp_handle.seek.assert_any_call(0)
        tmp_handle.write.assert_called_once_with('[options]\n[other_section]\nkey=value\n')
        self.assertEqual(mock_flock.call_count, 2)
        print("Test ensure_config_file_exists_adds_options_section passed.")

    @patch('os.fsync')
    @patch('fcntl.flock')
    @patch('os.makedirs')
    @patch('os.fdopen')
    @patch('os.open')
    @patch('builtins.open', new_callable=mock_open)
    def test_ensure_config_file_exists_no_changes(self, mock_open_file: MagicMock, mock_os_open: MagicMock, mock_fdopen: MagicMock, mock_makedirs: MagicMock, mock_flock: MagicMock, mock_fsync: MagicMock) -> None:
        """Test that ensure_config_file_exists makes no changes if [options] exists."""
        mock_os_open.return_value = 3
        tmp_handle = MagicMock()
        tmp_handle.read.return_value = '[options]\nkey=value\n'
        mock_fdopen.return_value.__enter__.return_value = tmp_handle

        odoo_config.ensure_config_file_exists()

        mock_open_file.assert_called_with(self.config_file_path + '.lock', 'a', encoding='utf-8')
        mock_os_open.assert_called_with(self.config_file_path, os.O_RDWR | os.O_CREAT)
        mock_fdopen.assert_called_with(3, 'r+', encoding='utf-8')
        tmp_handle.write.assert_not_called()
        self.assertEqual(mock_flock.call_count, 2)
        print("Test ensure_config_file_exists_no_changes passed.")

    @patch('fcntl.flock')
    @patch('builtins.open', new_callable=mock_open, read_data='[options]\nkey=value\n')
    def test_read_config_lines(self, mock_file: MagicMock, mock_flock: MagicMock) -> None:
        """Test reading config lines."""
        lines = odoo_config.read_config_lines()
        self.assertEqual(lines, ['[options]\n', 'key=value\n'])
        mock_file.assert_any_call(self.config_file_path + '.lock', 'a', encoding='utf-8')
        mock_file.assert_any_call(self.config_file_path, 'r', encoding='utf-8')
        self.assertEqual(mock_flock.call_count, 2)
        print("Test read_config_lines passed.")

    @patch('os.replace')
    @patch('os.close')
    @patch('os.open')
    @patch('os.fdopen')
    @patch('tempfile.mkstemp')
    @patch('os.fsync')
    @patch('fcntl.flock')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_write_config_lines(self, mock_open_file: MagicMock, mock_makedirs: MagicMock,
                               mock_flock: MagicMock, mock_fsync: MagicMock, mock_mkstemp: MagicMock,
                               mock_fdopen: MagicMock, mock_os_open: MagicMock, mock_close: MagicMock,
                               mock_replace: MagicMock) -> None:
        """Test writing config lines atomically."""
        lines = ['[options]\n', 'key=value\n']
        mock_mkstemp.return_value = (3, '/tmp/tmpfile')
        mock_tmp = MagicMock()
        mock_fdopen.return_value.__enter__.return_value = mock_tmp
        mock_os_open.return_value = 10

        odoo_config.write_config_lines(lines)

        mock_mkstemp.assert_called_once()
        mock_tmp.writelines.assert_called_with(lines)
        mock_replace.assert_called_with('/tmp/tmpfile', self.config_file_path)
        mock_open_file.assert_any_call(self.config_file_path + '.lock', 'a', encoding='utf-8')
        mock_os_open.assert_called_with(os.path.dirname(self.config_file_path), os.O_DIRECTORY)
        mock_close.assert_called_with(10)
        self.assertGreaterEqual(mock_flock.call_count, 2)
        print("Test write_config_lines passed.")

    def test_remove_commented_option(self) -> None:
        """Test that remove_commented_option removes commented out options."""
        lines = [
            '[options]\n',
            '; key = old_value\n',
            '# another_key = another_value\n',
            'key = value\n',
            'normal_line\n'
        ]
        odoo_config.remove_commented_option(lines, 'key')
        self.assertNotIn('; key = old_value\n', lines)
        self.assertIn('key = value\n', lines)
        self.assertEqual(len(lines), 4)
        print("Test remove_commented_option passed.")

    @patch('odoo_config.write_config_lines')
    @patch('odoo_config.read_config_lines')
    def test_set_defaults(self, mock_read: MagicMock, mock_write: MagicMock) -> None:
        """Test setting default values without replacing the entire file."""
        mock_read.return_value = [
            '[options]\n',
            'existing_key = existing_value\n',
            '; addons_path = /old/path\n'
        ]
        odoo_config.set_defaults()
        mock_write.assert_called_once()
        updated_lines = mock_write.call_args[0][0]
        self.assertIn('addons_path = /opt/odoo/community,/opt/odoo/enterprise,/opt/odoo/extras\n', updated_lines)
        self.assertNotIn('; addons_path = /old/path\n', updated_lines)
        print("Test set_defaults passed.")

    @patch('odoo_config.write_config_lines')
    @patch('odoo_config.read_config_lines', return_value=[])
    def test_set_config_new_section(self, mock_read: MagicMock, mock_write: MagicMock) -> None:
        """Test setting a configuration value when the section doesn't exist."""
        odoo_config.set_config('new_section', 'new_key', 'new_value')
        mock_write.assert_called_once()
        updated_lines = mock_write.call_args[0][0]
        self.assertIn('[new_section]\n', updated_lines)
        self.assertIn('new_key = new_value\n', updated_lines)
        print("Test set_config_new_section passed.")

    @patch('odoo_config.write_config_lines')
    @patch('odoo_config.read_config_lines', return_value=['[options]\n'])
    def test_set_config_existing_section(self, mock_read: MagicMock, mock_write: MagicMock) -> None:
        """Test setting a configuration value when the section exists."""
        odoo_config.set_config('options', 'key', 'value')
        mock_write.assert_called_once()
        updated_lines = mock_write.call_args[0][0]
        self.assertIn('[options]\n', updated_lines)
        self.assertIn('key = value\n', updated_lines)
        print("Test set_config_existing_section passed.")

    @patch('odoo_config.write_config_lines')
    @patch('odoo_config.read_config_lines', return_value=[
        '[options]\n',
        'key = old_value\n'
    ])
    def test_set_config_update_existing_key(self, mock_read: MagicMock, mock_write: MagicMock) -> None:
        """Test updating an existing configuration value."""
        odoo_config.set_config('options', 'key', 'new_value')
        mock_write.assert_called_once()
        updated_lines = mock_write.call_args[0][0]
        self.assertIn('key = new_value\n', updated_lines)
        self.assertNotIn('key = old_value\n', updated_lines)
        print("Test set_config_update_existing_key passed.")

    @patch('odoo_config.read_config_lines', return_value=[])
    def test_get_config_missing_key(self, mock_read: MagicMock) -> None:
        """Test getting a configuration value that doesn't exist."""
        with self.assertRaises(SystemExit) as cm:
            odoo_config.get_config('options', 'missing_key')
        self.assertEqual(cm.exception.code, 1)
        print("Test get_config_missing_key passed.")

    @patch('odoo_config.read_config_lines', return_value=[
        '[options]\n',
        'key = value\n'
    ])
    def test_get_config_success(self, mock_read: MagicMock) -> None:
        """Test getting a configuration value successfully."""
        with patch('builtins.print') as mock_print:
            odoo_config.get_config('options', 'key')
            mock_print.assert_called_with('value')
        print("Test get_config_success passed.")

    @patch('odoo_config.set_config')
    def test_set_admin_password(self, mock_set_config: MagicMock) -> None:
        """Test setting the admin password."""
        odoo_config.set_admin_password('admin_pass')
        mock_set_config.assert_called_with('options', 'admin_passwd', 'admin_pass')
        print("Test set_admin_password passed.")

    @patch('odoo_config.set_config')
    @patch('odoo_config.get_redis_defaults')
    def test_set_redis_configuration(self, mock_get_redis_defaults: MagicMock, mock_set_config: MagicMock) -> None:
        """Test setting Redis configuration with mocked defaults."""
        # Mock the redis defaults
        mock_defaults: Dict[str, Optional[str]] = {
            'redis_session': 'true',
            'redis_host': 'redis',
            'redis_port': '6379',
            'redis_expire': '432000',
            'redis_username': 'default',
            'redis_password': 'password',
            'redis_ssl_ca_certs': None
        }
        mock_get_redis_defaults.return_value = mock_defaults

        odoo_config.set_redis_configuration()

        calls = [
            unittest.mock.call('options', key, value)
            for key, value in mock_defaults.items()
            if value is not None
        ]
        mock_set_config.assert_has_calls(calls, any_order=True)
        print("Test set_redis_configuration passed.")

    @patch('os.getenv', return_value='master_pass')
    @patch('odoo_config.set_admin_password')
    def test_main_set_admin_password_from_env(self, mock_set_admin_password: MagicMock, mock_getenv: MagicMock) -> None:
        """Test setting admin password from environment variable."""
        testargs = ['odoo_config.py', '--set-admin-password']
        with patch.object(sys, 'argv', testargs):
            odoo_config.main()
            mock_set_admin_password.assert_called_with('master_pass')
        print("Test main_set_admin_password_from_env passed.")

    @patch('builtins.open', new_callable=mock_open, read_data='[options]\nkey=value\n')
    def test_show_config_file(self, mock_file: MagicMock) -> None:
        """Test displaying the content of the config file."""
        with patch('builtins.print') as mock_print:
            odoo_config.show_config_file()
            mock_print.assert_any_call('## odoo_config: Use --help for usage information\n')
            mock_print.assert_any_call('[options]\nkey=value\n')
        print("Test show_config_file passed.")

    @patch('signal.signal')
    def test_signal_handling_setup(self, mock_signal: MagicMock) -> None:
        """Test that signal handlers are set up correctly in main."""
        with patch.object(sys, 'argv', ['odoo_config.py']):
            with patch('odoo_config.ensure_config_file_exists'):
                with patch('odoo_config.show_config_file'):
                    odoo_config.main()
                    mock_signal.assert_any_call(signal.SIGINT, odoo_config.signal_handler)
                    mock_signal.assert_any_call(signal.SIGTERM, odoo_config.signal_handler)
        print("Test signal_handling_setup passed.")

    @patch('sys.exit')
    def test_signal_handler(self, mock_exit: MagicMock) -> None:
        """Test that signal_handler exits the program."""
        with patch('builtins.print') as mock_print:
            odoo_config.signal_handler(signal.SIGTERM, None)
            mock_print.assert_called_with("Received signal 15, terminating gracefully.", file=sys.stderr)
            mock_exit.assert_called_with(1)
        print("Test signal_handler passed.")


if __name__ == '__main__':
    unittest.main()