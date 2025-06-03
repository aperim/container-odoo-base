import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import signal

sys.path.append(os.path.abspath('.'))

# Import functions from addon_updater module
from tools.src.addon_updater import (
    is_symlink_to,
    ensure_directory_exists,
    copy_addon,
    dirs_are_same,
    compare_and_update_addons,
    signal_handler,
    main,
)


class TestAddonUpdater(unittest.TestCase):
    """Unit tests for addon_updater.py."""

    @patch('tools.src.addon_updater.os.path.islink')
    @patch('tools.src.addon_updater.os.path.realpath')
    def test_is_symlink_to_true(self, mock_realpath: MagicMock, mock_islink: MagicMock) -> None:
        """Test is_symlink_to returns True when target is a symlink to source."""
        mock_islink.return_value = True

        source = '/source/path'
        target = '/target/path'

        # Mock realpath to return the same real path for both source and target
        def realpath_side_effect(path):
            if path == target or path == source:
                return '/realpath/common_path'
            else:
                return '/realpath/' + path.strip('/')

        mock_realpath.side_effect = realpath_side_effect

        result = is_symlink_to(source, target)
        self.assertTrue(result)

        mock_islink.assert_called_with(target)
        mock_realpath.assert_any_call(target)
        mock_realpath.assert_any_call(source)

    @patch('tools.src.addon_updater.os.path.islink')
    @patch('tools.src.addon_updater.os.path.realpath')
    def test_is_symlink_to_false(self, mock_realpath: MagicMock, mock_islink: MagicMock) -> None:
        """Test is_symlink_to returns False when target is not a symlink to source."""
        mock_islink.return_value = False
        source = '/source/path'
        target = '/target/path'

        result = is_symlink_to(source, target)
        self.assertFalse(result)
        mock_islink.assert_called_with(target)

    @patch('tools.src.addon_updater.os.makedirs')
    @patch('tools.src.addon_updater.os.path.exists')
    def test_ensure_directory_exists(self, mock_exists: MagicMock, mock_makedirs: MagicMock) -> None:
        """Test ensuring that directories are created if they do not exist."""
        mock_exists.return_value = False
        ensure_directory_exists("/fake/path")
        mock_makedirs.assert_called_once_with("/fake/path", exist_ok=True)

    @patch('tools.src.addon_updater.shutil.copytree')
    @patch('tools.src.addon_updater.shutil.rmtree')
    @patch('tools.src.addon_updater.os.path.exists')
    def test_copy_addon(self, mock_exists: MagicMock, mock_rmtree: MagicMock, mock_copytree: MagicMock) -> None:
        """Test copying an addon from source to target directory."""
        mock_exists.return_value = True
        copy_addon("/fake/source", "/fake/destination")
        mock_rmtree.assert_called_once_with("/fake/destination")
        mock_copytree.assert_called_once_with("/fake/source", "/fake/destination")

    @patch('tools.src.addon_updater.os.path.isdir')
    @patch('tools.src.addon_updater.os.listdir')
    @patch('tools.src.addon_updater.copy_addon')
    @patch('tools.src.addon_updater.dirs_are_same', return_value=False)
    @patch('tools.src.addon_updater.ensure_directory_exists')
    @patch('tools.src.addon_updater.os.system')
    def test_compare_and_update_addons(self, mock_system: MagicMock, mock_ensure_dir: MagicMock,
                                       mock_dirs_are_same: MagicMock, mock_copy_addon: MagicMock,
                                       mock_listdir: MagicMock, mock_isdir: MagicMock) -> None:
        """Test updating addons from source to target directory."""
        mock_listdir.side_effect = [['addon1', 'addon2'], ['addon1']]
        mock_isdir.return_value = True

        compare_and_update_addons("/fake/source", "/fake/target")

        self.assertEqual(mock_copy_addon.call_count, 2)
        mock_copy_addon.assert_any_call("/fake/source/addon1", "/fake/target/addon1")
        mock_copy_addon.assert_any_call("/fake/source/addon2", "/fake/target/addon2")
        mock_system.assert_called_once()

    @patch('tools.src.addon_updater.filecmp.dircmp')
    def test_dirs_are_same(self, mock_dircmp: MagicMock) -> None:
        """Test dirs_are_same returns True when directories are the same."""
        comparison_mock = MagicMock()
        comparison_mock.left_only = []
        comparison_mock.right_only = []
        comparison_mock.diff_files = []
        comparison_mock.funny_files = []
        comparison_mock.common_dirs = []
        mock_dircmp.return_value = comparison_mock

        result = dirs_are_same("/dir1", "/dir2")
        self.assertTrue(result)

    @patch('tools.src.addon_updater.filecmp.dircmp')
    def test_dirs_are_not_same(self, mock_dircmp: MagicMock) -> None:
        """Test dirs_are_same returns False when directories differ."""
        comparison_mock = MagicMock()
        comparison_mock.left_only = ['file1']
        comparison_mock.right_only = []
        comparison_mock.diff_files = []
        comparison_mock.funny_files = []
        comparison_mock.common_dirs = []
        mock_dircmp.return_value = comparison_mock

        result = dirs_are_same("/dir1", "/dir2")
        self.assertFalse(result)

    @patch('tools.src.addon_updater.clean_up', side_effect=SystemExit)
    @patch('tools.src.addon_updater.compare_and_update_addons')
    @patch('tools.src.addon_updater.is_symlink_to', return_value=False)
    @patch('tools.src.addon_updater.signal.signal')
    def test_main(self, mock_signal: MagicMock, mock_is_symlink: MagicMock,
                  mock_compare: MagicMock, mock_clean_up: MagicMock) -> None:
        """Test the main function."""
        with self.assertRaises(SystemExit):
            main()
        self.assertTrue(mock_compare.called)
        self.assertTrue(mock_clean_up.called)
        mock_signal.assert_any_call(signal.SIGINT, signal_handler)
        mock_signal.assert_any_call(signal.SIGTERM, signal_handler)

    @patch('tools.src.addon_updater.clean_up')
    def test_signal_handler(self, mock_clean_up: MagicMock) -> None:
        """Test the signal handler calls clean_up with exit code 1."""
        signal_handler(signal.SIGINT, None)
        mock_clean_up.assert_called_with(1)


if __name__ == '__main__':
    unittest.main()
