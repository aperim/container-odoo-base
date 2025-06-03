import unittest
from unittest.mock import patch, MagicMock
import os

import sys
sys.path.append(os.path.abspath('.'))

from tools.src.replace_odoo_addons_path import replace_odoo_addons_path


class TestReplaceOdooAddonsPath(unittest.TestCase):
    """Unit tests for replace_odoo_addons_path.py."""

    @patch('tools.src.replace_odoo_addons_path.os.path.exists')
    @patch('tools.src.replace_odoo_addons_path.os.path.islink')
    @patch('tools.src.replace_odoo_addons_path.os.unlink')
    @patch('tools.src.replace_odoo_addons_path.shutil.rmtree')
    @patch('tools.src.replace_odoo_addons_path.os.symlink')
    def test_replace_symlink(self, mock_symlink: MagicMock, mock_rmtree: MagicMock, mock_unlink: MagicMock, mock_islink: MagicMock, mock_path_exists: MagicMock) -> None:
        """Test replacing the addons path with a symlink."""
        mock_path_exists.side_effect = [
            True, True]  # Source exists, Target exists
        mock_islink.return_value = True  # Target is a symlink

        source_dir = "/fake/source"
        target_dir = "/fake/target"

        replace_odoo_addons_path(source_dir, target_dir)

        mock_islink.assert_called_once_with(target_dir)
        mock_unlink.assert_called_once_with(target_dir)
        mock_symlink.assert_called_once_with(source_dir, target_dir)

    @patch('tools.src.replace_odoo_addons_path.os.path.exists')
    def test_replace_addons_path_source_not_exists(self, mock_path_exists: MagicMock) -> None:
        """Test when the source directory does not exist."""
        mock_path_exists.side_effect = [False]

        source_dir = "/fake/source"
        target_dir = "/fake/target"

        with self.assertRaises(Exception):
            replace_odoo_addons_path(source_dir, target_dir)

    @patch('tools.src.replace_odoo_addons_path.os.path.exists')
    @patch('tools.src.replace_odoo_addons_path.os.path.islink')
    @patch('tools.src.replace_odoo_addons_path.os.unlink')
    @patch('tools.src.replace_odoo_addons_path.shutil.rmtree')
    @patch('tools.src.replace_odoo_addons_path.os.symlink')
    def test_replace_addons_path_target_exists_dir(self, mock_symlink: MagicMock, mock_rmtree: MagicMock, mock_unlink: MagicMock, mock_islink: MagicMock, mock_path_exists: MagicMock) -> None:
        """Test replacing the addons path when the target is a directory."""
        mock_path_exists.side_effect = [
            True, True]  # Source exists, Target exists
        mock_islink.side_effect = [False]  # Target is not a symlink

        source_dir = "/fake/source"
        target_dir = "/fake/target"

        replace_odoo_addons_path(source_dir, target_dir)

        mock_rmtree.assert_called_once_with(target_dir)
        mock_symlink.assert_called_once_with(source_dir, target_dir)


if __name__ == '__main__':
    unittest.main()
