#!/usr/bin/env python3
"""
healthcheck_full.py - Perform full health checks including web and WebSocket services.

This script performs health checks on both the web service and the WebSocket service.
It utilises the websocket_checker module to check the WebSocket service.
The web service health check verifies that the response is JSON and contains {"status": "pass"}.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-10-01: Initial creation.
    2024-10-02: Added support for --websocket-origin argument.
"""

import argparse
import signal
import sys
from typing import Optional, List
import requests

import websockets
from websockets.exceptions import InvalidHandshake, InvalidMessage


def signal_handler(signum: int, frame) -> None:
    """Handle termination signals and exit gracefully.

    Args:
        signum (int): The signal number.
        frame: The current stack frame.
    """
    print(f"Received signal {signum}, exiting.", file=sys.stderr)
    sys.exit(1)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Perform full health checks including web and WebSocket services."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="URLs of the web service and/or WebSocket service to check",
    )
    parser.add_argument(
        "--websocket-origin",
        type=str,
        help="The Origin header to use in the WebSocket handshake",
    )
    return parser.parse_args()


def check_web_service(url: str) -> int:
    """Check the web service health.

    Args:
        url (str): The URL of the web service health endpoint.

    Returns:
        int: 0 if the health check passes, 1 otherwise.
    """
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            print(f"Web service {url} did not return JSON.", file=sys.stderr)
            return 1
        data = response.json()
        if data.get("status") == "pass":
            print(f"Web service {url} is healthy.", file=sys.stderr)
            return 0
        else:
            print(f"Web service {url} health check failed: {data}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Failed to check web service {url}: {e}", file=sys.stderr)
        return 1


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
    """Main function to execute the full health checks."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    args = parse_arguments()

    web_url: Optional[str] = None
    websocket_url: Optional[str] = None
    websocket_origin: Optional[str] = args.websocket_origin

    for url in args.urls:
        if url.startswith("http://") or url.startswith("https://"):
            web_url = url
        elif url.startswith("ws://") or url.startswith("wss://"):
            websocket_url = url

    if not web_url and not websocket_url:
        print("Error: At least one URL must be provided.", file=sys.stderr)
        sys.exit(1)

    # Check web service
    web_exit_code = 0
    if web_url:
        web_exit_code = check_web_service(web_url)

    # Check WebSocket service
    websocket_exit_code = 0
    if websocket_url:
        try:
            import asyncio
            websocket_exit_code = asyncio.run(
                check_websocket(websocket_url, websocket_origin)
            )
        except ImportError as e:
            print(f"Asyncio module not found: {e}", file=sys.stderr)
            sys.exit(1)

    # If both checks pass, exit 0; otherwise, exit 1
    if web_exit_code == 0 and websocket_exit_code == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
