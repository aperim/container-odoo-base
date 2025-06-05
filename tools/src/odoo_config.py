#!/usr/bin/env python3
"""Manage the ``odoo.conf`` configuration file.

This script provides utilities to create and modify ``odoo.conf`` in a safe
and atomic way.  It supports reading and writing configuration values,
setting sensible defaults, configuring Redis options and managing the
admin password.  All file operations use locking and syncing to cater for
network or distributed filesystems.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import signal
import sys
import tempfile
from types import FrameType
from typing import Dict, List, Optional


CONFIG_FILE_PATH: str = "/etc/odoo/odoo.conf"
LOCK_FILE_PATH: str = CONFIG_FILE_PATH + ".lock"

DEFAULTS: Dict[str, str] = {
    "addons_path": "/opt/odoo/community,/opt/odoo/enterprise,/opt/odoo/extras",
    "db_maxconn": "64",
    "limit_memory_hard": "2684354560",
    "limit_memory_soft": "2147483648",
    "limit_request": "8192",
    "limit_time_cpu": "60",
    "limit_time_real": "120",
    "db_host": os.getenv("POSTGRES_HOST", "odoo"),
    "db_port": os.getenv("POSTGRES_PORT", "5432"),
    "db_user": os.getenv("POSTGRES_USER", "odoo"),
    "db_password": os.getenv("POSTGRES_PASSWORD", ""),
    "db_sslmode": os.getenv("POSTGRES_SSL_MODE", "disable"),
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _log(message: str) -> None:
    """Print *message* to stderr."""

    print(message, file=sys.stderr)


def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    """Handle termination signals."""

    _log(f"Received signal {signum}, terminating gracefully.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def ensure_config_file_exists() -> None:
    """Ensure ``CONFIG_FILE_PATH`` exists and contains an ``[options]`` section."""

    directory = os.path.dirname(CONFIG_FILE_PATH)
    os.makedirs(directory, exist_ok=True)

    try:
        with open(LOCK_FILE_PATH, "a", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            fd = os.open(CONFIG_FILE_PATH, os.O_RDWR | os.O_CREAT)
            with os.fdopen(fd, "r+", encoding="utf-8") as cfg:
                content = cfg.read()
                if "[options]" not in content:
                    cfg.seek(0)
                    cfg.write("[options]\n" + content)
                    cfg.truncate()
                    cfg.flush()
                    os.fsync(cfg.fileno())
                    _log("Config file created with [options] section." if not content else
                         "Added [options] section to existing config file.")
            os.chmod(CONFIG_FILE_PATH, 0o644)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        _log(f"Error accessing config file: {exc}")
        sys.exit(1)


def read_config_lines() -> List[str]:
    """Return the configuration file as a list of lines."""

    try:
        with open(LOCK_FILE_PATH, "a", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as cfg:
                lines = cfg.readlines()
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            return lines
    except OSError as exc:
        _log(f"Error reading config file: {exc}")
        sys.exit(1)


def write_config_lines(lines: List[str]) -> None:
    """Atomically write *lines* to the configuration file."""

    directory = os.path.dirname(CONFIG_FILE_PATH)
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.writelines(lines)
            tmp.flush()
            os.fsync(tmp.fileno())
        with open(LOCK_FILE_PATH, "a", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            os.replace(tmp_path, CONFIG_FILE_PATH)
            try:
                dir_fd = os.open(directory, os.O_DIRECTORY)
                os.fsync(dir_fd)
            finally:
                try:
                    os.close(dir_fd)
                except Exception:
                    pass
            os.chmod(CONFIG_FILE_PATH, 0o644)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        _log(f"Error writing to config file: {exc}")
        sys.exit(1)
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def remove_commented_option(lines: List[str], key: str) -> None:
    """Remove commented lines that define *key*."""

    pattern = re.compile(rf"^\s*[;#]\s*{re.escape(key)}\s*=.*$")
    indexes: List[int] = []
    for idx, line in enumerate(lines):
        if pattern.match(line):
            indexes.append(idx)
    for idx in reversed(indexes):
        del lines[idx]


def set_defaults() -> None:
    """Ensure all default options exist and update differing values."""

    lines = read_config_lines()

    for key in DEFAULTS:
        remove_commented_option(lines, key)

    new_lines: List[str] = []
    in_options = False
    found_options = False
    updated = False
    keys_seen: Dict[str, bool] = {k: False for k in DEFAULTS}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_options = stripped.lower() == "[options]"
            if in_options:
                found_options = True
        elif in_options and "=" in line and not stripped.startswith((";", "#")):
            key_in_line = line.split("=", 1)[0].strip()
            if key_in_line in DEFAULTS:
                value_in_line = line.split("=", 1)[1].strip()
                if value_in_line != DEFAULTS[key_in_line]:
                    line = f"{key_in_line} = {DEFAULTS[key_in_line]}\n"
                    updated = True
                keys_seen[key_in_line] = True
        new_lines.append(line)

    if not found_options:
        new_lines.insert(0, "[options]\n")
        in_options = True
        found_options = True

    if in_options:
        insert_idx = None
        for idx, l in enumerate(new_lines):
            if l.strip().lower() == "[options]":
                insert_idx = idx + 1
                while insert_idx < len(new_lines) and not new_lines[insert_idx].strip().startswith("["):
                    insert_idx += 1
                break
        if insert_idx is None:
            insert_idx = len(new_lines)
        for key, value in DEFAULTS.items():
            if not keys_seen[key]:
                new_lines.insert(insert_idx, f"{key} = {value}\n")
                insert_idx += 1
                updated = True

    if updated:
        write_config_lines(new_lines)
        _log("Defaults have been set and written to config file.")
    else:
        _log("No defaults were changed.")


def get_config(section: str, key: str) -> None:
    """Print the value of ``key`` from ``section``."""

    lines = read_config_lines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped.strip("[]").lower() == section.lower()
        elif in_section and "=" in line and not stripped.startswith((";", "#")):
            k = line.split("=", 1)[0].strip()
            if k == key:
                value = line.split("=", 1)[1].strip()
                print(value)
                return
    _log(f"Error: Key '{key}' not found in section '{section}'")
    sys.exit(1)


def set_config(section: str, key: str, value: str) -> None:
    """Set ``key`` to ``value`` in ``section``."""

    lines = read_config_lines()
    remove_commented_option(lines, key)

    new_lines: List[str] = []
    section_found = False
    in_section = False
    key_set = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped.strip("[]").lower() == section.lower()
            if in_section:
                section_found = True
        elif in_section and "=" in line and not stripped.startswith((";", "#")):
            current_key = line.split("=", 1)[0].strip()
            if current_key == key:
                line = f"{key} = {value}\n"
                key_set = True
        new_lines.append(line)

    if not section_found:
        new_lines.append(f"[{section}]\n")
        new_lines.append(f"{key} = {value}\n")
        _log(f"Added new section [{section}] with {key} = {value}")
    elif not key_set:
        insert_idx = None
        for idx, line in enumerate(new_lines):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.strip("[]").lower() == section.lower():
                insert_idx = idx + 1
                while insert_idx < len(new_lines) and not new_lines[insert_idx].strip().startswith("["):
                    insert_idx += 1
                break
        if insert_idx is not None:
            new_lines.insert(insert_idx, f"{key} = {value}\n")
        else:
            new_lines.append(f"{key} = {value}\n")
        _log(f"Added {key} = {value} to section [{section}]")

    write_config_lines(new_lines)
    _log(f"Config [{section}] {key} = {value} has been written to file.")


def set_admin_password(password: str) -> None:
    """Set the master admin password."""

    set_config("options", "admin_passwd", password)
    _log("Admin password has been set.")


def get_redis_defaults() -> Dict[str, Optional[str]]:
    """Return default Redis configuration derived from the environment."""

    redis_ssl = os.getenv("REDIS_SSL", "false").lower() in ["true", "1", "yes"]
    return {
        "redis_session": "true",
        "redis_host": os.getenv("REDIS_HOST", "redis"),
        "redis_port": os.getenv("REDIS_PORT", "6379"),
        "redis_expire": "432000",
        "redis_username": "default",
        "redis_password": os.getenv("REDIS_PASSWORD", ""),
        "redis_ssl_ca_certs": "/etc/ssl/certs/ca-certificates.crt" if redis_ssl else None,
    }


def set_redis_configuration() -> None:
    """Write Redis related configuration options."""

    defaults = get_redis_defaults()
    for key, value in defaults.items():
        if value is not None:
            set_config("options", key, value)
    _log("Redis settings have been set in the configuration file.")


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""

    parser = argparse.ArgumentParser(description="Manage the odoo.conf file")
    parser.add_argument("--defaults", action="store_true", help="Set default configuration values")

    subparsers = parser.add_subparsers(dest="command")

    get_parser = subparsers.add_parser("get", help="Get a configuration value")
    get_parser.add_argument("section", type=str)
    get_parser.add_argument("key", type=str)

    set_parser = subparsers.add_parser("set", help="Set a configuration value")
    set_parser.add_argument("section", type=str)
    set_parser.add_argument("key", type=str)
    set_parser.add_argument("value", type=str)

    parser.add_argument("--set-admin-password", nargs="?", const=True,
                        help="Set the admin password from environment or provided value")
    parser.add_argument("--set-redis-config", action="store_true",
                        help="Set Redis keys in the configuration file from environment or defaults")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# User interaction helpers
# ---------------------------------------------------------------------------

def show_config_file() -> None:
    """Print the current configuration file."""

    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as cfg:
            print("## odoo_config: Use --help for usage information\n")
            print(cfg.read())
    except OSError as exc:
        _log(f"Error reading config file: {exc}")
        sys.exit(1)


def report_config_file_status() -> None:
    """Report whether the config file exists and its size."""

    if not os.path.isfile(CONFIG_FILE_PATH):
        _log(f"Error: Config file '{CONFIG_FILE_PATH}' does not exist.")
        sys.exit(1)
        return
    try:
        size = os.path.getsize(CONFIG_FILE_PATH)
    except OSError as exc:
        _log(f"Error getting size of config file: {exc}")
        sys.exit(1)
        return
    _log(f"Config file '{CONFIG_FILE_PATH}' exists ({size} bytes).")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the command line tool."""

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    args = parse_args()

    ensure_config_file_exists()

    if args.defaults:
        set_defaults()
    elif args.command == "get":
        get_config(args.section, args.key)
    elif args.command == "set":
        set_config(args.section, args.key, args.value)
    elif args.set_admin_password is not None:
        if args.set_admin_password is True:
            password_env = os.getenv("ODOO_MASTER_PASSWORD")
            if not password_env:
                _log("Error: Environment variable ODOO_MASTER_PASSWORD is not set or empty.")
                sys.exit(1)
            password = password_env
        else:
            password = args.set_admin_password
            env_pw = os.getenv("ODOO_MASTER_PASSWORD")
            if env_pw and env_pw != password:
                _log("Warning: Provided password does not match the environment variable ODOO_MASTER_PASSWORD.")
        set_admin_password(password)
    elif args.set_redis_config:
        set_redis_configuration()
    else:
        show_config_file()

    report_config_file_status()


if __name__ == "__main__":
    main()
