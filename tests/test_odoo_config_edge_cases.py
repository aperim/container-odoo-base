import os
import errno
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

sys.path.append(os.path.abspath('tools/src'))
import odoo_config  # noqa: E402


class TestOdooConfigEdgeCases(unittest.TestCase):
    def setUp(self) -> None:
        self.config_path = '/tmp/odoo.conf'
        odoo_config.CONFIG_FILE_PATH = self.config_path
        odoo_config.LOCK_FILE_PATH = self.config_path + '.lock'

    @patch('sys.exit')
    @patch('fcntl.flock', side_effect=OSError(errno.ENOLCK, 'No locks'))
    @patch('builtins.open', new_callable=mock_open)
    def test_read_config_lines_lock_failure(self, mock_open_file: MagicMock, mock_flock: MagicMock, mock_exit: MagicMock) -> None:
        """read_config_lines should exit if locking fails."""
        odoo_config.read_config_lines()
        mock_exit.assert_called_with(1)
        mock_open_file.assert_called_with(self.config_path + '.lock', 'a', encoding='utf-8')

    @patch('sys.exit')
    @patch('fcntl.flock', side_effect=OSError(errno.ENOLCK, 'No locks'))
    @patch('os.open')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_ensure_config_file_exists_lock_failure(self, mock_open_file: MagicMock, mock_makedirs: MagicMock, mock_os_open: MagicMock, mock_flock: MagicMock, mock_exit: MagicMock) -> None:
        """ensure_config_file_exists should exit on lock failure."""
        mock_os_open.return_value = 3
        handle = MagicMock()
        handle.read.return_value = ''
        with patch('os.fdopen') as mock_fdopen:
            mock_fdopen.return_value.__enter__.return_value = handle
            odoo_config.ensure_config_file_exists()
        mock_exit.assert_called_with(1)

    @patch('sys.exit')
    @patch('fcntl.flock', side_effect=OSError(errno.ENOLCK, 'No locks'))
    @patch('tempfile.mkstemp', return_value=(3, '/tmp/tmpfile'))
    @patch('os.fdopen')
    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_write_config_lines_lock_failure(self, mock_open_file: MagicMock, mock_makedirs: MagicMock, mock_fdopen: MagicMock, mock_mkstemp: MagicMock, mock_flock: MagicMock, mock_exit: MagicMock) -> None:
        """write_config_lines should exit if lock acquisition fails."""
        handle = MagicMock()
        handle.fileno.return_value = 3
        mock_fdopen.return_value.__enter__.return_value = handle
        odoo_config.write_config_lines(['[options]\n'])
        mock_exit.assert_called_with(1)


if __name__ == '__main__':
    unittest.main()
