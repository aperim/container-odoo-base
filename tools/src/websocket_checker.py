#!/usr/bin/env python3
"""
websocket_checker.py - Check the availability of a WebSocket URL with optional Origin header.

This script attempts to connect to a specified WebSocket URL to verify its availability.
It supports specifying an Origin header to comply with servers that enforce origin checks.
It is intended for use as a health check in containerised environments such as Docker Compose.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-10-01: Initial creation.
    2024-10-02: Added support for specifying an Origin header.

"""

import argparse
import asyncio
import signal
import sys
from typing import Optional

import websockets
from websockets.exceptions import InvalidHandshake, InvalidMessage


def signal_handler(signum: int, frame: Optional[object]) -> None:
    """Handle termination signals and exit gracefully.

    Args:
        signum (int): The signal number.
        frame (Optional[object]): The current stack frame.
    """
    print(f"Received signal {signum}, exiting.", file=sys.stderr)
    sys.exit(1)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Check the availability of a WebSocket URL."
    )
    parser.add_argument(
        "websocket_url",
        nargs="?",
        default="ws://localhost:8072/websocket",
        help="The WebSocket URL to check (default: ws://localhost:8072/websocket)",
    )
    parser.add_argument(
        "--origin",
        type=str,
        default="ws://localhost:8072/websocket",
        help="The Origin header to use in the WebSocket handshake",
    )
    return parser.parse_args()


async def check_websocket(url: str, origin: Optional[str] = None) -> int:
    """Attempt to connect to the WebSocket URL with an optional Origin header.

    Args:
        url (str): The WebSocket URL to connect to.
        origin (Optional[str], optional): The Origin header to send. Defaults to None.

    Returns:
        int: 0 if successful, 1 otherwise.
    """
    try:
        headers = {}
        if origin:
            headers["Origin"] = origin
            print(f"Using Origin header: {origin}", file=sys.stderr)
        async with websockets.connect(url, extra_headers=headers):
            print(f"Connected to WebSocket URL: {url}", file=sys.stderr)
        return 0
    except InvalidHandshake as e:
        print(f"Invalid handshake with WebSocket URL {url}: {e}", file=sys.stderr)
        return 1
    except InvalidMessage as e:
        print(f"Invalid message from WebSocket URL {url}: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Failed to connect to WebSocket URL {url}: {e}", file=sys.stderr)
        return 1


def main() -> None:
    """Main function to execute the WebSocket checker."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    args = parse_arguments()

    exit_code = asyncio.run(check_websocket(args.websocket_url, args.origin))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
