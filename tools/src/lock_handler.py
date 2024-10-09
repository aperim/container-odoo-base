#!/usr/bin/env python3

"""
lock_handler.py - Script for handling Redis-based locking with TLS support.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-09-12: Initial creation
    2024-09-13: Added TLS support
    2024-09-16: Fixed wait_for_lock to wait for lock to be released
"""

import os
import signal
import ssl
import sys
import time
from types import FrameType
from typing import Optional

import redis

# Default constants
DEFAULT_REDIS_HOST: str = 'localhost'
DEFAULT_REDIS_PORT: int = 6379
LOCK_EXPIRE_TIME: int = 3600  # Lock expiration time in seconds


def create_redis_client() -> redis.Redis:
    """Create a Redis client with SSL/TLS support if enabled.

    Reads configuration from environment variables.

    Returns:
        redis.Redis: A Redis client instance.

    Raises:
        SystemExit: If there is an error creating the Redis client.
    """
    # Environment variables
    redis_host: str = os.getenv("REDIS_HOST", DEFAULT_REDIS_HOST)
    redis_port: int = int(os.getenv("REDIS_PORT", str(DEFAULT_REDIS_PORT)))
    redis_password: Optional[str] = os.getenv("REDIS_PASSWORD")

    # TLS/SSL parameters
    redis_ssl_str: str = os.getenv("REDIS_SSL", "false").lower()
    redis_ssl: bool = redis_ssl_str == "true"

    redis_ssl_ca_certs: Optional[str] = os.getenv("REDIS_SSL_CA_CERTS")
    redis_ssl_certfile: Optional[str] = os.getenv("REDIS_SSL_CERTFILE")
    redis_ssl_keyfile: Optional[str] = os.getenv("REDIS_SSL_KEYFILE")
    redis_ssl_check_hostname_str: str = os.getenv("REDIS_SSL_CHECK_HOSTNAME", "false").lower()
    redis_ssl_check_hostname: bool = redis_ssl_check_hostname_str == "true"

    redis_ssl_cert_reqs_str: str = os.getenv("REDIS_SSL_CERT_REQS", "required").lower()
    ssl_cert_reqs_map = {
        'none': ssl.CERT_NONE,
        'optional': ssl.CERT_OPTIONAL,
        'required': ssl.CERT_REQUIRED
    }
    ssl_cert_reqs = ssl_cert_reqs_map.get(redis_ssl_cert_reqs_str, ssl.CERT_REQUIRED)

    try:
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_password,
            ssl=redis_ssl,
            ssl_ca_certs=redis_ssl_ca_certs,
            ssl_certfile=redis_ssl_certfile,
            ssl_keyfile=redis_ssl_keyfile,
            ssl_check_hostname=redis_ssl_check_hostname,
            ssl_cert_reqs=ssl_cert_reqs
        )
        return client
    except Exception as e:
        print(f"Error creating Redis client: {e}", file=sys.stderr)
        sys.exit(1)


client: redis.Redis = create_redis_client()


def wait_for_redis(max_attempts: int = 60, sleep_seconds: int = 5) -> None:
    """Wait for Redis to become available.

    Args:
        max_attempts: Maximum number of attempts.
        sleep_seconds: Seconds to sleep between attempts.

    Raises:
        SystemExit: If Redis is not available after max_attempts.
    """
    attempt: int = 0
    while attempt < max_attempts:
        try:
            if client.ping():
                print("Redis is ready", file=sys.stderr)
                return
        except (redis.ConnectionError, redis.TimeoutError) as e:
            print(f"Error pinging Redis: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Unexpected error when pinging Redis: {e}", file=sys.stderr)
        attempt += 1
        print(f"Attempt {attempt} of {max_attempts}: Redis is not up, waiting...", file=sys.stderr)
        time.sleep(sleep_seconds)
    print(f"Redis is not up after {max_attempts} attempts, aborting", file=sys.stderr)
    sys.exit(1)


def acquire_lock(name: str, expire_time: int = LOCK_EXPIRE_TIME) -> bool:
    """Attempt to acquire a lock with the given name.

    Args:
        name: The name of the lock.
        expire_time: The expiration time of the lock in seconds.

    Returns:
        bool: True if the lock was acquired, False otherwise.
    """
    try:
        result: Optional[bool] = client.set(name, "locked", nx=True, ex=expire_time)
        return result is True
    except Exception as e:
        print(f"Error acquiring lock {name}: {e}", file=sys.stderr)
        return False


def release_lock(name: str) -> None:
    """Release a lock with the given name.

    Args:
        name: The name of the lock to release.
    """
    try:
        deleted = client.delete(name)
        if deleted:
            print(f"Lock {name} released", file=sys.stderr)
        else:
            print(f"Lock {name} did not exist", file=sys.stderr)
    except Exception as e:
        print(f"Error releasing lock {name}: {e}", file=sys.stderr)


def wait_for_lock(name: str, max_attempts: int = 1080, sleep_seconds: int = 10) -> None:
    """Wait until the lock with the given name no longer exists.

    Args:
        name: The name of the lock.
        max_attempts: Maximum number of attempts to check the lock.
        sleep_seconds: Seconds to sleep between attempts.

    Raises:
        SystemExit: Exit with code 0 if lock cleared, 1 if timeout occurs.
    """
    attempt: int = 0
    while attempt < max_attempts:
        if not client.exists(name):
            print(f"Lock {name} has been released", file=sys.stderr)
            sys.exit(0)
        attempt += 1
        print(f"Attempt {attempt} of {max_attempts}: Lock {name} still exists, waiting...", file=sys.stderr)
        time.sleep(sleep_seconds)
    print(f"Lock {name} still exists after {max_attempts} attempts, timeout occurred", file=sys.stderr)
    sys.exit(1)


def handle_signal(signum: int, frame: Optional[FrameType]) -> None:
    """Handle system signals for proper cleanup.

    Args:
        signum: The signal number.
        frame: The current stack frame.
    """
    print(f"Received signal {signum}, cleaning up...", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    """Main function for handling Redis lock operations based on command-line arguments."""
    if len(sys.argv) < 2:
        wait_for_redis()
        return

    command: str = sys.argv[1]
    lock_name: Optional[str] = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        if command == "acquire" and lock_name:
            if acquire_lock(lock_name):
                print(f"Lock {lock_name} acquired successfully", file=sys.stderr)
            else:
                print(f"Failed to acquire lock {lock_name}", file=sys.stderr)
                sys.exit(1)
        elif command == "release" and lock_name:
            release_lock(lock_name)
        elif command == "wait" and lock_name:
            wait_for_lock(lock_name)
        elif command == "wait":
            wait_for_redis()
        else:
            print(f"Unknown command or missing lock name: {command} {lock_name}", file=sys.stderr)
            sys.exit(1)
    except SystemExit:
        raise  # Re-raise SystemExit to exit with specified code
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    main()
