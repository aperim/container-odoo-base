#!/usr/bin/env python3
"""
test_lock_handler.py - Unit tests for the lock_handler.py script with TLS support.

This test suite ensures that the lock_handler.py script functions as expected,
including handling TLS connections to Redis, correctly acquiring and releasing locks,
and handling exceptions and signals appropriately.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-09-14: Updated tests to include TLS support and cover all functionality.
    2024-09-16: Updated tests to reflect changes in wait_for_lock function.
"""

import os
import signal
import ssl
import sys
import unittest
from types import FrameType
from typing import Optional
from unittest.mock import MagicMock, patch

import redis  # Import the redis library to access exceptions

# Import the module functions to be tested
from tools.src.lock_handler import (
    acquire_lock,
    create_redis_client,
    handle_signal,
    main,
    release_lock,
    wait_for_lock,
    wait_for_redis,
)


class TestLockHandler(unittest.TestCase):
    """Unit tests for Redis lock handler with TLS support."""

    @patch.dict(os.environ, {"REDIS_SSL": "false"})
    @patch('tools.src.lock_handler.redis.Redis')
    def test_create_redis_client_no_ssl(self, mock_redis: MagicMock) -> None:
        """Test creating Redis client without SSL."""
        _ = create_redis_client()
        mock_redis.assert_called_with(
            host=unittest.mock.ANY,
            port=unittest.mock.ANY,
            password=unittest.mock.ANY,
            ssl=False,
            ssl_ca_certs=None,
            ssl_certfile=None,
            ssl_keyfile=None,
            ssl_check_hostname=False,
            ssl_cert_reqs=ssl.CERT_REQUIRED
        )

    @patch.dict(os.environ, {"REDIS_SSL": "true", "REDIS_SSL_CERT_REQS": "required"})
    @patch('tools.src.lock_handler.redis.Redis')
    def test_create_redis_client_with_ssl(self, mock_redis: MagicMock) -> None:
        """Test creating Redis client with SSL."""
        _ = create_redis_client()
        mock_redis.assert_called_with(
            host=unittest.mock.ANY,
            port=unittest.mock.ANY,
            password=unittest.mock.ANY,
            ssl=True,
            ssl_ca_certs=None,
            ssl_certfile=None,
            ssl_keyfile=None,
            ssl_check_hostname=False,
            ssl_cert_reqs=ssl.CERT_REQUIRED
        )

    @patch('tools.src.lock_handler.redis.Redis')
    def test_create_redis_client_exception(self, mock_redis: MagicMock) -> None:
        """Test that create_redis_client handles exceptions correctly."""
        mock_redis.side_effect = Exception("Connection failed")
        with self.assertRaises(SystemExit) as cm, patch('builtins.print') as mock_print:
            _ = create_redis_client()
        self.assertEqual(cm.exception.code, 1)
        mock_print.assert_called_with('Error creating Redis client: Connection failed', file=sys.stderr)

    @patch('tools.src.lock_handler.client')
    def test_acquire_lock_success(self, mock_client: MagicMock) -> None:
        """Test acquiring a lock successfully."""
        mock_client.set.return_value = True
        result = acquire_lock('test_lock')
        self.assertTrue(result)
        mock_client.set.assert_called_with('test_lock', 'locked', nx=True, ex=unittest.mock.ANY)

    @patch('tools.src.lock_handler.client')
    def test_acquire_lock_fail(self, mock_client: MagicMock) -> None:
        """Test failing to acquire a lock."""
        mock_client.set.return_value = False
        result = acquire_lock('test_lock')
        self.assertFalse(result)

    @patch('tools.src.lock_handler.client')
    def test_acquire_lock_exception(self, mock_client: MagicMock) -> None:
        """Test that acquire_lock handles exceptions correctly."""
        mock_client.set.side_effect = Exception("Redis error")
        with patch('builtins.print') as mock_print:
            result = acquire_lock('test_lock')
        self.assertFalse(result)
        mock_print.assert_called_with('Error acquiring lock test_lock: Redis error', file=sys.stderr)

    @patch('tools.src.lock_handler.client')
    def test_release_lock(self, mock_client: MagicMock) -> None:
        """Test releasing a lock."""
        mock_client.delete.return_value = 1  # Indicate that a key was deleted
        with patch('builtins.print') as mock_print:
            release_lock('test_lock')
        mock_client.delete.assert_called_with('test_lock')
        mock_print.assert_called_with('Lock test_lock released', file=sys.stderr)

    @patch('tools.src.lock_handler.client')
    def test_release_lock_nonexistent(self, mock_client: MagicMock) -> None:
        """Test releasing a lock that does not exist."""
        mock_client.delete.return_value = 0  # Indicate no key was deleted
        with patch('builtins.print') as mock_print:
            release_lock('test_lock')
        mock_client.delete.assert_called_with('test_lock')
        mock_print.assert_called_with('Lock test_lock did not exist', file=sys.stderr)

    @patch('tools.src.lock_handler.client')
    def test_release_lock_exception(self, mock_client: MagicMock) -> None:
        """Test that release_lock handles exceptions correctly."""
        mock_client.delete.side_effect = Exception("Redis error")
        with patch('builtins.print') as mock_print:
            release_lock('test_lock')
        mock_print.assert_called_with('Error releasing lock test_lock: Redis error', file=sys.stderr)

    @patch('tools.src.lock_handler.client')
    @patch('time.sleep', return_value=None)
    def test_wait_for_lock_released(self, mock_sleep: MagicMock, mock_client: MagicMock) -> None:
        """Test wait_for_lock when lock is eventually released."""
        mock_client.exists.side_effect = [True, True, False]
        with self.assertRaises(SystemExit) as cm:
            wait_for_lock('test_lock', max_attempts=3, sleep_seconds=0)
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(mock_client.exists.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('tools.src.lock_handler.client')
    @patch('time.sleep', return_value=None)
    def test_wait_for_lock_timeout(self, mock_sleep: MagicMock, mock_client: MagicMock) -> None:
        """Test wait_for_lock when lock is not released before timeout."""
        mock_client.exists.return_value = True
        with self.assertRaises(SystemExit) as cm:
            wait_for_lock('test_lock', max_attempts=3, sleep_seconds=0)
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(mock_client.exists.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 3)

    @patch('tools.src.lock_handler.client')
    @patch('time.sleep', return_value=None)
    def test_wait_for_redis(self, mock_sleep: MagicMock, mock_client: MagicMock) -> None:
        """Test waiting for Redis to become available."""
        mock_client.ping.side_effect = [redis.ConnectionError, redis.TimeoutError, True]
        wait_for_redis(max_attempts=3, sleep_seconds=0)
        self.assertEqual(mock_client.ping.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('tools.src.lock_handler.client')
    @patch('time.sleep', return_value=None)
    def test_wait_for_redis_failure(self, mock_sleep: MagicMock, mock_client: MagicMock) -> None:
        """Test wait_for_redis when Redis is never available."""
        mock_client.ping.side_effect = redis.ConnectionError("Cannot connect")
        with self.assertRaises(SystemExit) as cm, patch('builtins.print'):
            wait_for_redis(max_attempts=3, sleep_seconds=0)
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(mock_client.ping.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 3)

    def test_handle_signal(self) -> None:
        """Test handle_signal function exits the program."""
        with self.assertRaises(SystemExit) as cm, patch('builtins.print'):
            handle_signal(signal.SIGINT, None)
        self.assertEqual(cm.exception.code, 1)

    @patch('sys.exit')
    @patch('builtins.print')
    @patch('tools.src.lock_handler.acquire_lock')
    def test_main_acquire_lock_exception(self, mock_acquire_lock: MagicMock, mock_print: MagicMock, mock_exit: MagicMock) -> None:
        """Test main function acquire command exception."""
        mock_acquire_lock.side_effect = Exception("Error")
        with patch.object(sys, 'argv', ['lock_handler.py', 'acquire', 'test_lock']):
            main()
        mock_print.assert_called_with('An error occurred: Error', file=sys.stderr)
        mock_exit.assert_called_with(1)

    @patch('sys.exit')
    def test_main_invalid_command(self, mock_exit: MagicMock) -> None:
        """Test main function with invalid command."""
        with patch.object(sys, 'argv', ['lock_handler.py', 'invalid', 'lock_name']), \
                patch('builtins.print') as mock_print:
            main()
        mock_print.assert_called_with('Unknown command or missing lock name: invalid lock_name', file=sys.stderr)
        mock_exit.assert_called_with(1)

    @patch('sys.exit')
    def test_main_missing_lock_name(self, mock_exit: MagicMock) -> None:
        """Test main function with missing lock name."""
        with patch.object(sys, 'argv', ['lock_handler.py', 'acquire']), \
                patch('builtins.print') as mock_print:
            main()
        mock_print.assert_called_with('Unknown command or missing lock name: acquire None', file=sys.stderr)
        mock_exit.assert_called_with(1)

    @patch('tools.src.lock_handler.client.delete')
    @patch('builtins.print')
    def test_main_release_lock(self, mock_print: MagicMock, mock_client_delete: MagicMock) -> None:
        """Test main function release command."""
        mock_client_delete.return_value = 1
        with patch.object(sys, 'argv', ['lock_handler.py', 'release', 'test_lock']):
            main()
        mock_client_delete.assert_called_with('test_lock')
        mock_print.assert_called_with('Lock test_lock released', file=sys.stderr)

    @patch('tools.src.lock_handler.wait_for_lock')
    def test_main_wait_for_lock(self, mock_wait_for_lock: MagicMock) -> None:
        """Test main function wait command with lock name."""
        with patch.object(sys, 'argv', ['lock_handler.py', 'wait', 'test_lock']):
            main()
        mock_wait_for_lock.assert_called_with('test_lock')

    @patch('tools.src.lock_handler.wait_for_redis')
    def test_main_wait_for_redis(self, mock_wait_for_redis: MagicMock) -> None:
        """Test main function wait command without lock name."""
        with patch.object(sys, 'argv', ['lock_handler.py', 'wait']):
            main()
        mock_wait_for_redis.assert_called_once()

    @patch('tools.src.lock_handler.wait_for_redis')
    def test_main_no_args(self, mock_wait_for_redis: MagicMock) -> None:
        """Test main function with no arguments."""
        with patch.object(sys, 'argv', ['lock_handler.py']):
            main()
        mock_wait_for_redis.assert_called_once()

    @patch('tools.src.lock_handler.sys.exit')
    @patch('tools.src.lock_handler.wait_for_redis')
    def test_main_no_args_exit(self, mock_wait_for_redis: MagicMock, mock_exit: MagicMock) -> None:
        """Test main function exits correctly when no arguments are provided."""
        with patch.object(sys, 'argv', ['lock_handler.py']):
            main()
        mock_wait_for_redis.assert_called_once()
        mock_exit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
