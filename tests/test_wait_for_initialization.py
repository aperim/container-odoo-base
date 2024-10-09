import unittest
from unittest.mock import patch, MagicMock
import sys
import signal

from tools.src.wait_for_initialization import (
    wait_for_initialization,
    clean_up,
    main,
    signal_handler,
)


class TestWaitForInitialization(unittest.TestCase):
    """Unit tests for wait_for_initialization.py."""

    @patch("tools.src.wait_for_initialization.os.path.isfile")
    @patch("tools.src.wait_for_initialization.time.sleep", return_value=None)
    @patch("tools.src.wait_for_initialization.clean_up", side_effect=sys.exit)
    def test_initialization_detected(self, mock_clean_up: MagicMock,
                                     mock_sleep: MagicMock, mock_isfile: MagicMock) -> None:
        """Test initialization is detected within the first attempts."""
        mock_isfile.side_effect = [False, False, True]

        with self.assertRaises(SystemExit) as cm:
            wait_for_initialization(max_attempts=3, sleep_seconds=1)
        self.assertEqual(cm.exception.code, 0)
        mock_clean_up.assert_called_with(0)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("tools.src.wait_for_initialization.os.path.isfile")
    @patch("tools.src.wait_for_initialization.time.sleep", return_value=None)
    @patch("tools.src.wait_for_initialization.clean_up", side_effect=sys.exit)
    def test_initialization_timeout(self, mock_clean_up: MagicMock,
                                    mock_sleep: MagicMock, mock_isfile: MagicMock) -> None:
        """Test initialization times out after maximum attempts."""
        mock_isfile.side_effect = [False] * 4

        with self.assertRaises(SystemExit) as cm:
            wait_for_initialization(max_attempts=3, sleep_seconds=1)
        self.assertEqual(cm.exception.code, 1)
        mock_clean_up.assert_called_with(1)
        self.assertEqual(mock_sleep.call_count, 3)

    def test_clean_up(self) -> None:
        """Test the clean_up function."""
        with self.assertRaises(SystemExit) as cm:
            clean_up(0)
        self.assertEqual(cm.exception.code, 0)

    @patch('signal.signal')
    @patch('tools.src.wait_for_initialization.wait_for_initialization')
    def test_main(self, mock_wait_for_initialization: MagicMock, mock_signal: MagicMock) -> None:
        """Test the main function."""
        main()
        mock_wait_for_initialization.assert_called_once()
        mock_signal.assert_any_call(signal.SIGINT, signal_handler)
        mock_signal.assert_any_call(signal.SIGTERM, signal_handler)

    @patch("tools.src.wait_for_initialization.clean_up", side_effect=sys.exit)
    def test_signal_handler(self, mock_clean_up: MagicMock) -> None:
        """Test signal handler for SystemExit."""
        with self.assertRaises(SystemExit) as cm:
            signal_handler(signal.SIGINT, None)
        self.assertEqual(cm.exception.code, 1)
        mock_clean_up.assert_called_with(1)


if __name__ == "__main__":
    unittest.main()
