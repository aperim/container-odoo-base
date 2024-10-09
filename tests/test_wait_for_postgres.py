#!/usr/bin/env python3
"""
test_wait_for_postgres.py - Unit tests for wait_for_postgres.py script.

This test suite ensures that the wait_for_postgres.py script functions as expected,
including handling SSL options, exceptions, and signals appropriately.
It aims to provide complete coverage of all functionalities without making real database connections.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-09-16: All new test suite for complete coverage, following code requirements.
    2024-09-17: Adjusted tests to match updated script behavior and removed unnecessary password hashing.
"""

import os
import signal
import sys
import unittest
from unittest.mock import MagicMock, patch
from typing import Any, List, Optional

import psycopg2

# Import the module under test
from wait_for_postgres import (
    wait_for_postgres,
    wait_for_pgbouncer,
    main,
    clean_up,
    signal_handler,
)


class TestWaitForPostgres(unittest.TestCase):
    """Unit tests for wait_for_postgres.py."""

    def test_wait_for_postgres_immediate_availability(self) -> None:
        """Test wait_for_postgres when PostgreSQL is immediately available."""
        with patch('psycopg2.connect') as mock_connect:
            mock_connect.return_value = MagicMock()

            # Call the function and ensure no exception is raised
            try:
                wait_for_postgres(
                    user='testuser',
                    password='testpass',
                    host='localhost',
                    port=5432,
                    dbname='testdb',
                    ssl_mode='disable',
                    max_attempts=1,
                    sleep_seconds=0
                )
                mock_connect.assert_called_once()
            except Exception as e:
                self.fail(f"wait_for_postgres raised an exception unexpectedly: {e}")

    def test_wait_for_postgres_with_ssl_options(self) -> None:
        """Test wait_for_postgres passing SSL options."""
        with patch('psycopg2.connect') as mock_connect:
            mock_connect.return_value = MagicMock()

            try:
                wait_for_postgres(
                    user='testuser',
                    password='testpass',
                    host='localhost',
                    port=5432,
                    dbname='testdb',
                    ssl_mode='require',
                    ssl_cert='/path/to/cert.pem',
                    ssl_key='/path/to/key.pem',
                    ssl_root_cert='/path/to/root_cert.pem',
                    ssl_crl='/path/to/crl.pem',
                    max_attempts=1,
                    sleep_seconds=0
                )
                mock_connect.assert_called_once()
                _, kwargs = mock_connect.call_args
                expected_dsn = 'dbname=testdb user=testuser password=testpass host=localhost port=5432 sslmode=require'
                self.assertEqual(kwargs.get('dsn'), expected_dsn)
                self.assertEqual(kwargs.get('sslcert'), '/path/to/cert.pem')
                self.assertEqual(kwargs.get('sslkey'), '/path/to/key.pem')
                self.assertEqual(kwargs.get('sslrootcert'), '/path/to/root_cert.pem')
                self.assertEqual(kwargs.get('sslcrl'), '/path/to/crl.pem')
            except Exception as e:
                self.fail(f"wait_for_postgres raised an exception unexpectedly: {e}")

    def test_wait_for_postgres_becomes_available_after_attempts(self) -> None:
        """Test wait_for_postgres when PostgreSQL becomes available after some attempts."""
        connection_attempts: List[Any] = [psycopg2.OperationalError("Connection refused")] * 2 + [MagicMock()]
        with patch('psycopg2.connect', side_effect=connection_attempts) as mock_connect, \
                patch('time.sleep', return_value=None) as mock_sleep:

            try:
                wait_for_postgres(
                    user='testuser',
                    password='testpass',
                    host='localhost',
                    port=5432,
                    dbname='testdb',
                    ssl_mode='disable',
                    max_attempts=5,
                    sleep_seconds=0
                )
                self.assertEqual(mock_connect.call_count, 3)
                self.assertEqual(mock_sleep.call_count, 2)
            except Exception as e:
                self.fail(f"wait_for_postgres raised an exception unexpectedly: {e}")

    def test_wait_for_postgres_never_available(self) -> None:
        """Test wait_for_postgres when PostgreSQL is never available."""
        with patch('psycopg2.connect', side_effect=psycopg2.OperationalError("Connection refused")), \
                patch('time.sleep', return_value=None) as mock_sleep:
            with self.assertRaises(SystemExit) as cm:
                wait_for_postgres(
                    user='testuser',
                    password='testpass',
                    host='localhost',
                    port=5432,
                    dbname='testdb',
                    ssl_mode='disable',
                    max_attempts=3,
                    sleep_seconds=0
                )
            self.assertEqual(cm.exception.code, 1)
            self.assertEqual(mock_sleep.call_count, 2)  # max_attempts - 1

    def test_wait_for_pgbouncer_immediate_availability(self) -> None:
        """Test wait_for_pgbouncer when PGBouncer is immediately available."""
        with patch('psycopg2.connect') as mock_connect:
            mock_connect.return_value = MagicMock()

            try:
                wait_for_pgbouncer(
                    user='testuser',
                    password='testpass',
                    host='localhost',
                    port=6432,
                    dbname='pgbouncer',
                    ssl_mode='disable',
                    max_attempts=1,
                    sleep_seconds=0
                )
                mock_connect.assert_called_once()
            except Exception as e:
                self.fail(f"wait_for_pgbouncer raised an exception unexpectedly: {e}")

    def test_wait_for_pgbouncer_becomes_available_after_attempts(self) -> None:
        """Test wait_for_pgbouncer when PGBouncer becomes available after some attempts."""
        connection_attempts: List[Any] = [psycopg2.OperationalError("Connection refused")] * 2 + [MagicMock()]
        with patch('psycopg2.connect', side_effect=connection_attempts) as mock_connect, \
                patch('time.sleep', return_value=None) as mock_sleep:

            try:
                wait_for_pgbouncer(
                    user='testuser',
                    password='testpass',
                    host='localhost',
                    port=6432,
                    dbname='pgbouncer',
                    ssl_mode='disable',
                    max_attempts=5,
                    sleep_seconds=0
                )
                self.assertEqual(mock_connect.call_count, 3)
                self.assertEqual(mock_sleep.call_count, 2)
            except Exception as e:
                self.fail(f"wait_for_pgbouncer raised an exception unexpectedly: {e}")

    def test_wait_for_pgbouncer_never_available(self) -> None:
        """Test wait_for_pgbouncer when PGBouncer is never available."""
        with patch('psycopg2.connect', side_effect=psycopg2.OperationalError("Connection refused")), \
                patch('time.sleep', return_value=None) as mock_sleep:
            with self.assertRaises(SystemExit) as cm:
                wait_for_pgbouncer(
                    user='testuser',
                    password='testpass',
                    host='localhost',
                    port=6432,
                    dbname='pgbouncer',
                    ssl_mode='disable',
                    max_attempts=3,
                    sleep_seconds=0
                )
            self.assertEqual(cm.exception.code, 1)
            self.assertEqual(mock_sleep.call_count, 2)  # max_attempts - 1

    def test_clean_up(self) -> None:
        """Test the clean_up function exits with the given code."""
        with self.assertRaises(SystemExit) as cm:
            clean_up(0)
        self.assertEqual(cm.exception.code, 0)

    def test_signal_handler(self) -> None:
        """Test the signal_handler function calls clean_up with code 1."""
        with patch('wait_for_postgres.clean_up') as mock_clean_up:
            signal_handler(signal.SIGINT, None)
            mock_clean_up.assert_called_once_with(1)

    def test_main_missing_env_vars(self) -> None:
        """Test main function when required environment variables are missing."""
        with patch.dict(os.environ, {}, clear=True), \
                patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)
            mock_print.assert_any_call('Required environment variables for PostgreSQL are missing.', file=sys.stderr)

    def test_main_postgres_never_available(self) -> None:
        """Test main function when PostgreSQL is never available."""
        env_vars = {
            'POSTGRES_USER': 'testuser',
            'POSTGRES_PASSWORD': 'testpass',
            'POSTGRES_HOST': 'localhost',
            'POSTGRES_DB': 'testdb',
            'POSTGRES_SSL_MODE': 'disable',
            'MAX_ATTEMPTS': '3',
            'SLEEP_SECONDS': '0',
        }
        with patch.dict(os.environ, env_vars, clear=True), \
                patch('psycopg2.connect', side_effect=psycopg2.OperationalError("Connection refused")), \
                patch('time.sleep', return_value=None) as mock_sleep, \
                patch('builtins.print'):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)
            self.assertEqual(mock_sleep.call_count, 2)  # max_attempts -1

    def test_main_with_pgbouncer(self) -> None:
        """Test main function when PGBouncer is configured."""
        env_vars = {
            'POSTGRES_USER': 'two',
            'POSTGRES_PASSWORD': 'password',
            'POSTGRES_HOST': 'postgres.example.com',
            'POSTGRES_PORT': '5432',
            'POSTGRES_DB': 'two',
            'POSTGRES_SSL_MODE': 'prefer',
            'PGBOUNCER_HOST': 'localhost',
            'PGBOUNCER_PORT': '6432',
            'PGBOUNCER_SSL_MODE': 'require',
            'MAX_ATTEMPTS': '3',
            'SLEEP_SECONDS': '0',
        }
        with patch.dict(os.environ, env_vars, clear=True), \
                patch('wait_for_postgres.wait_for_postgres') as mock_wait_for_postgres, \
                patch('wait_for_postgres.wait_for_pgbouncer') as mock_wait_for_pgbouncer, \
                patch('psycopg2.connect') as mock_connect, \
                patch('time.sleep', return_value=None):
            mock_connect.return_value = MagicMock()
            main()

            password = 'password'

            mock_wait_for_postgres.assert_called_once_with(
                user='two',
                password=password,
                host='postgres.example.com',
                port=5432,
                dbname='two',
                ssl_mode='prefer',
                ssl_cert=None,
                ssl_key=None,
                ssl_root_cert=None,
                ssl_crl=None,
                max_attempts=3,
                sleep_seconds=0
            )
            mock_wait_for_pgbouncer.assert_called_once_with(
                user='two',
                password=password,
                host='localhost',
                port=6432,
                dbname='two',
                ssl_mode='require',
                max_attempts=3,
                sleep_seconds=0
            )

    def test_main_signal_handlers(self) -> None:
        """Test that main function sets up signal handlers."""
        env_vars = {
            'POSTGRES_USER': 'testuser',
            'POSTGRES_PASSWORD': 'testpass',
            'POSTGRES_HOST': 'localhost',
            'POSTGRES_DB': 'testdb',
            'POSTGRES_SSL_MODE': 'disable',
        }
        with patch.dict(os.environ, env_vars, clear=True), \
                patch('wait_for_postgres.signal.signal') as mock_signal, \
                patch('wait_for_postgres.wait_for_postgres'), \
                patch('wait_for_postgres.wait_for_pgbouncer'):
            main()
            mock_signal.assert_any_call(signal.SIGINT, signal_handler)
            mock_signal.assert_any_call(signal.SIGTERM, signal_handler)


if __name__ == '__main__':
    unittest.main()
