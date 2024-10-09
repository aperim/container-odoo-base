#!/usr/bin/env python3
"""
wait_for_postgres.py - Wait for PostgreSQL and PGBouncer to become available.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-09-12: Initial creation
    2024-09-13: Added TLS support
    2024-09-16: Added support for PGBOUNCER variables and improved validation
    2024-09-17: Refactored to read environment variables at runtime for testing
    2024-09-16: Fixed type annotations for compatibility with Python versions earlier than 3.10
"""

import os
import signal
import sys
import time
from typing import Optional, Dict

import psycopg2
from psycopg2 import OperationalError

# Default constants for script
DEFAULT_MAX_ATTEMPTS: int = 1080
DEFAULT_SLEEP_SECONDS: int = 5


def wait_for_postgres(
    user: str,
    password: str,
    host: str,
    port: int,
    dbname: str,
    ssl_mode: str,
    ssl_cert: Optional[str] = None,
    ssl_key: Optional[str] = None,
    ssl_root_cert: Optional[str] = None,
    ssl_crl: Optional[str] = None,
    max_attempts: Optional[int] = None,
    sleep_seconds: Optional[int] = None
) -> None:
    """Wait for PostgreSQL to become available.

    Args:
        user (str): The database user.
        password (str): The database password.
        host (str): The database host.
        port (int): The database port.
        dbname (str): The database name.
        ssl_mode (str): The SSL mode.
        ssl_cert (Optional[str]): Path to client SSL certificate.
        ssl_key (Optional[str]): Path to client SSL key.
        ssl_root_cert (Optional[str]): Path to SSL root certificate.
        ssl_crl (Optional[str]): Path to SSL certificate revocation list.
        max_attempts (Optional[int]): Maximum number of attempts. Defaults to DEFAULT_MAX_ATTEMPTS.
        sleep_seconds (Optional[int]): Seconds to sleep between attempts. Defaults to DEFAULT_SLEEP_SECONDS.

    Raises:
        SystemExit: If PostgreSQL is not available after the maximum attempts.
    """
    if max_attempts is None:
        max_attempts = DEFAULT_MAX_ATTEMPTS
    if sleep_seconds is None:
        sleep_seconds = DEFAULT_SLEEP_SECONDS

    # Build the DSN (Data Source Name) for PostgreSQL connection
    dsn: str = (
        f"dbname={dbname} user={user} password={password} "
        f"host={host} port={port} sslmode={ssl_mode}"
    )
    ssl_options: Dict[str, str] = {}
    if ssl_cert:
        ssl_options["sslcert"] = ssl_cert
    if ssl_key:
        ssl_options["sslkey"] = ssl_key
    if ssl_root_cert:
        ssl_options["sslrootcert"] = ssl_root_cert
    if ssl_crl:
        ssl_options["sslcrl"] = ssl_crl

    attempt: int = 0
    while attempt < max_attempts:
        try:
            with psycopg2.connect(dsn=dsn, **ssl_options):
                print(f"PostgreSQL is ready on {host}:{port}.", file=sys.stderr)
                break
        except OperationalError as e:
            attempt += 1
            if attempt >= max_attempts:
                print(
                    f"PostgreSQL is not up after {max_attempts} attempts, aborting. Last error: {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(
                f"Attempt {attempt} of {max_attempts}: PostgreSQL is not up yet, waiting... Error: {e}",
                file=sys.stderr,
            )
            time.sleep(sleep_seconds)


def wait_for_pgbouncer(
    user: str,
    password: str,
    host: str,
    port: int,
    dbname: str,
    ssl_mode: str,
    max_attempts: Optional[int] = None,
    sleep_seconds: Optional[int] = None
) -> None:
    """Wait for PGBouncer to become available.

    Args:
        user (str): The database user.
        password (str): The database password.
        host (str): The PGBouncer host.
        port (int): The PGBouncer port.
        dbname (str): The database name.
        ssl_mode (str): The SSL mode.
        max_attempts (Optional[int]): Maximum number of attempts. Defaults to DEFAULT_MAX_ATTEMPTS.
        sleep_seconds (Optional[int]): Seconds to sleep between attempts. Defaults to DEFAULT_SLEEP_SECONDS.

    Raises:
        SystemExit: If PGBouncer is not available after the maximum attempts.
    """
    if max_attempts is None:
        max_attempts = DEFAULT_MAX_ATTEMPTS
    if sleep_seconds is None:
        sleep_seconds = DEFAULT_SLEEP_SECONDS

    # Build the DSN for PGBouncer connection
    dsn: str = (
        f"dbname={dbname} user={user} password={password} "
        f"host={host} port={port} sslmode={ssl_mode}"
    )

    attempt: int = 0
    while attempt < max_attempts:
        try:
            with psycopg2.connect(dsn=dsn):
                print(f"PGBouncer is ready on {host}:{port}.", file=sys.stderr)
                break
        except OperationalError as e:
            attempt += 1
            if attempt >= max_attempts:
                print(
                    f"PGBouncer is not up after {max_attempts} attempts, aborting. Last error: {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(
                f"Attempt {attempt} of {max_attempts}: PGBouncer is not up yet, waiting... Error: {e}",
                file=sys.stderr,
            )
            time.sleep(sleep_seconds)


def clean_up(exit_code: int = 0) -> None:
    """Clean up resources and exit with the given exit code.

    Args:
        exit_code (int): The exit code. Defaults to 0.
    """
    print(f"Exiting with code {exit_code}", file=sys.stderr)
    sys.exit(exit_code)


def signal_handler(signum: int, frame: Optional[str]) -> None:
    """Handle system signals for proper cleanup.

    Args:
        signum (int): The signal number.
        frame (Optional[str]): The current stack frame.
    """
    print(f"Received signal {signum}, initiating cleanup.", file=sys.stderr)
    clean_up(1)


def main() -> None:
    """Main function to wait for PostgreSQL and PGBouncer."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Read environment variables
    postgres_user: str = os.getenv("POSTGRES_USER", "")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")
    postgres_host: str = os.getenv("POSTGRES_HOST", "")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "")
    postgres_ssl_mode: str = os.getenv("POSTGRES_SSL_MODE", "disable")
    postgres_ssl_cert: Optional[str] = os.getenv("POSTGRES_SSL_CERT", "")
    postgres_ssl_key: Optional[str] = os.getenv("POSTGRES_SSL_KEY", "")
    postgres_ssl_root_cert: Optional[str] = os.getenv("POSTGRES_SSL_ROOT_CERT", "")
    postgres_ssl_crl: Optional[str] = os.getenv("POSTGRES_SSL_CRL", "")

    # Environment variables for PGBouncer
    pgbouncer_host: str = os.getenv("PGBOUNCER_HOST", "")
    pgbouncer_port: int = int(os.getenv("PGBOUNCER_PORT", str(postgres_port)))
    pgbouncer_ssl_mode: str = os.getenv("PGBOUNCER_SSL_MODE", "disable")

    if not all([postgres_user, postgres_password, postgres_host, postgres_db]):
        print("Required environment variables for PostgreSQL are missing.", file=sys.stderr)
        sys.exit(1)

    # Read MAX_ATTEMPTS and SLEEP_SECONDS from environment variables
    max_attempts: int = int(os.getenv('MAX_ATTEMPTS', str(DEFAULT_MAX_ATTEMPTS)))
    sleep_seconds: int = int(os.getenv('SLEEP_SECONDS', str(DEFAULT_SLEEP_SECONDS)))

    # Wait for PostgreSQL
    print(
        f"Waiting for PostgreSQL to become available for user '{postgres_user}' at host '{postgres_host}:{postgres_port}' using SSL mode '{postgres_ssl_mode}'...",
        file=sys.stderr,
    )
    wait_for_postgres(
        user=postgres_user,
        password=postgres_password,
        host=postgres_host,
        port=postgres_port,
        dbname=postgres_db,
        ssl_mode=postgres_ssl_mode,
        ssl_cert=postgres_ssl_cert or None,
        ssl_key=postgres_ssl_key or None,
        ssl_root_cert=postgres_ssl_root_cert or None,
        ssl_crl=postgres_ssl_crl or None,
        max_attempts=max_attempts,
        sleep_seconds=sleep_seconds
    )

    if pgbouncer_host:
        # Wait for PGBouncer
        print(
            f"Waiting for PGBouncer to become available for user '{postgres_user}' at host '{pgbouncer_host}:{pgbouncer_port}' using SSL mode '{pgbouncer_ssl_mode}'...",
            file=sys.stderr,
        )
        wait_for_pgbouncer(
            user=postgres_user,
            password=postgres_password,
            host=pgbouncer_host,
            port=pgbouncer_port,
            dbname=postgres_db,
            ssl_mode=pgbouncer_ssl_mode,
            max_attempts=max_attempts,
            sleep_seconds=sleep_seconds
        )


if __name__ == "__main__":
    main()
