#!/usr/bin/env python3

"""
wait_for_initialization.py - Wait for Odoo instance initialization

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-09-12: Initial creation
"""

import os
import signal
import sys
import time
from typing import Optional

DEFAULT_MAX_ATTEMPTS = 1080
DEFAULT_SLEEP_SECONDS = 5
INIT_FILE = '/etc/odoo/.scaffolded'


def wait_for_initialization(
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
        init_file: str = INIT_FILE) -> None:
    """
    Wait for the Odoo instance to be initialized by another replica.

    Args:
        max_attempts (int): Maximum number of attempts. Defaults to 1080.
        sleep_seconds (int): Number of seconds to sleep between attempts. Defaults to 5.
        init_file (str): Path to the initialization file. Defaults to /etc/odoo/.scaffolded.

    Raises:
        SystemExit: If the file is not found within the maximum attempts.
    """
    print("Waiting for the Odoo instance to be initialized by another replica...")
    for attempt in range(1, max_attempts + 1):
        if os.path.isfile(init_file):
            print("Odoo instance initialization detected. Proceeding...",
                  file=sys.stderr)
            clean_up(0)
        print(f"Attempt {attempt} of {max_attempts}: Waiting for initialization to complete...")
        time.sleep(sleep_seconds)
    print("Timeout waiting for initialization to complete. Aborting.", file=sys.stderr)
    clean_up(1)


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
    """Main function to call the wait_for_initialization function with default parameters."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    wait_for_initialization()


if __name__ == "__main__":
    main()
