#!/usr/bin/env python3
"""
odoo_config.py - Manage the odoo.conf configuration file.

This script allows managing the Odoo configuration file by setting default values,
getting and setting specific configuration values, managing the admin password,
and configuring Redis settings.

Author: Troy Kelly
Contact: troy@aperim.com

History:
    2024-09-12: Initial creation.
    2024-09-13: Refactored to comply with code requirements.
    2024-09-13: Modified to ensure that set_defaults updates or adds default values without overwriting the entire file,
                and that when setting values, any commented out settings are removed.
    2024-09-15: Refactored REDIS_DEFAULTS into a function for better testability.
"""

import argparse
import os
import re
import signal
import sys
import tempfile
import fcntl
from types import FrameType
from typing import Dict, List, Optional


# Constants
CONFIG_FILE_PATH: str = '/etc/odoo/odoo.conf'
LOCK_FILE_PATH: str = CONFIG_FILE_PATH + '.lock'

# Default configuration values
DEFAULTS: Dict[str, str] = {
    'addons_path': '/opt/odoo/community,/opt/odoo/enterprise,/opt/odoo/extras',
    'db_maxconn': '64',
    'limit_memory_hard': '2684354560',
    'limit_memory_soft': '2147483648',
    'limit_request': '8192',
    'limit_time_cpu': '60',
    'limit_time_real': '120',
    'db_host': os.getenv('POSTGRES_HOST', 'odoo'),
    'db_port': os.getenv('POSTGRES_PORT', '5432'),
    'db_user': os.getenv('POSTGRES_USER', 'odoo'),
    'db_password': os.getenv('POSTGRES_PASSWORD', ''),
    'db_sslmode': os.getenv('POSTGRES_SSL_MODE', 'disable')
}

# Global variable to track termination signals
TERMINATED: bool = False


def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    """Handle system signals for proper cleanup.

    Args:
        signum (int): The signal number received.
        frame (Optional[FrameType]): The current stack frame.
    """
    global TERMINATED
    print(f"Received signal {signum}, terminating gracefully.", file=sys.stderr)
    TERMINATED = True
    sys.exit(1)


def ensure_config_file_exists() -> None:
    """Ensure the configuration file exists and contains an [options] section."""
    dir_name = os.path.dirname(CONFIG_FILE_PATH)
    os.makedirs(dir_name, exist_ok=True)
    try:
        with open(LOCK_FILE_PATH, 'a', encoding='utf-8') as lockfile:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
            fd: int = os.open(CONFIG_FILE_PATH, os.O_RDWR | os.O_CREAT)
            with os.fdopen(fd, 'r+', encoding='utf-8') as configfile:
                configfile.seek(0)
                content: str = configfile.read()
                if '[options]' not in content:
                    configfile.seek(0)
                    configfile.write('[options]\n' + content)
                    configfile.truncate()
                    configfile.flush()
                    os.fsync(configfile.fileno())
                    print(
                        "Config file created with [options] section." if not content else
                        "Added [options] section to existing config file.",
                        file=sys.stderr,
                    )
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
    except OSError as e:
        print(f"Error accessing config file: {e}", file=sys.stderr)
        sys.exit(1)


def read_config_lines() -> List[str]:
    """Read the configuration file and return its content as a list of lines."""
    try:
        with open(LOCK_FILE_PATH, 'a', encoding='utf-8') as lockfile:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_SH)
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as configfile:
                lines = configfile.readlines()
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
            return lines
    except OSError as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)


def write_config_lines(lines: List[str]) -> None:
    """Write the given lines to the configuration file.

    Args:
        lines (List[str]): The list of lines to write to the config file.

    Raises:
        SystemExit: If the configuration file cannot be written.
    """
    dir_name = os.path.dirname(CONFIG_FILE_PATH)
    os.makedirs(dir_name, exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as tmpfile:
            tmpfile.writelines(lines)
            tmpfile.flush()
            os.fsync(tmpfile.fileno())
        with open(LOCK_FILE_PATH, 'a', encoding='utf-8') as lockfile:
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
            os.replace(temp_path, CONFIG_FILE_PATH)
            try:
                dir_fd = os.open(dir_name, os.O_DIRECTORY)
                os.fsync(dir_fd)
            finally:
                try:
                    os.close(dir_fd)
                except Exception:
                    pass
            fcntl.flock(lockfile.fileno(), fcntl.LOCK_UN)
    except OSError as e:
        print(f"Error writing to config file: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass


def remove_commented_option(lines: List[str], key: str) -> None:
    """Remove lines with commented out options matching the given key.

    Args:
        lines (List[str]): The list of lines to process.
        key (str): The option key to search for and remove if commented out.
    """
    pattern = re.compile(rf'^\s*[;#]\s*{re.escape(key)}\s*=.*$')
    indices_to_remove: List[int] = []
    for idx, line in enumerate(lines):
        if pattern.match(line):
            indices_to_remove.append(idx)
    for idx in reversed(indices_to_remove):
        del lines[idx]


def set_defaults() -> None:
    """Set default configuration values without destroying the existing file."""
    lines: List[str] = read_config_lines()
    options_section_found: bool = False
    updated: bool = False

    # Remove commented out options
    for key in DEFAULTS.keys():
        remove_commented_option(lines, key)

    # Process the lines and update or add defaults
    new_lines: List[str] = []
    in_options_section: bool = False
    keys_set: Dict[str, bool] = {key: False for key in DEFAULTS.keys()}

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('['):
            # Check if we are entering or leaving the [options] section
            in_options_section = stripped_line.lower() == '[options]'
            if in_options_section:
                options_section_found = True
        elif in_options_section and '=' in line and not line.strip().startswith((';', '#')):
            # Parse the key in the current line
            key_in_line = line.split('=', 1)[0].strip()
            if key_in_line in DEFAULTS:
                # Update the value if it's different
                value_in_line = line.split('=', 1)[1].strip()
                if value_in_line != DEFAULTS[key_in_line]:
                    line = f"{key_in_line} = {DEFAULTS[key_in_line]}\n"
                    updated = True
                keys_set[key_in_line] = True
        new_lines.append(line)

    # If options section was not found, create it
    if not options_section_found:
        new_lines.insert(0, '[options]\n')
        in_options_section = True
        options_section_found = True

    # Add any missing defaults
    if in_options_section:
        for key, value in DEFAULTS.items():
            if not keys_set[key]:
                new_lines.append(f"{key} = {value}\n")
                updated = True

    if updated:
        write_config_lines(new_lines)
        print("Defaults have been set and written to config file.", file=sys.stderr)
    else:
        print("No defaults were changed.", file=sys.stderr)


def get_config(section: str, key: str) -> None:
    """Get a configuration value.

    Args:
        section (str): The configuration section.
        key (str): The configuration key.

    Raises:
        SystemExit: If the section or key does not exist.
    """
    lines: List[str] = read_config_lines()
    in_section: bool = False
    value_found: bool = False
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('['):
            in_section = stripped_line.strip('[]').lower() == section.lower()
        elif in_section and '=' in line and not line.strip().startswith((';', '#')):
            key_in_line = line.split('=', 1)[0].strip()
            if key_in_line == key:
                value = line.split('=', 1)[1].strip()
                print(value)
                value_found = True
                break
    if not value_found:
        print(f"Error: Key '{key}' not found in section '{section}'", file=sys.stderr)
        sys.exit(1)


def set_config(section: str, key: str, value: str) -> None:
    """Set a configuration value.

    Args:
        section (str): The configuration section.
        key (str): The configuration key.
        value (str): The configuration value.

    Raises:
        SystemExit: If the configuration file cannot be written.
    """
    lines: List[str] = read_config_lines()
    section_found: bool = False
    in_section: bool = False
    key_set: bool = False

    # Remove commented out option
    remove_commented_option(lines, key)

    new_lines: List[str] = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('['):
            in_section = stripped_line.strip('[]').lower() == section.lower()
            if in_section:
                section_found = True
        elif in_section and '=' in line and not line.strip().startswith((';', '#')):
            key_in_line = line.split('=', 1)[0].strip()
            if key_in_line == key:
                line = f"{key} = {value}\n"
                key_set = True
        new_lines.append(line)

    if not section_found:
        # Add the section at the end
        new_lines.append(f'[{section}]\n')
        new_lines.append(f"{key} = {value}\n")
        print(f"Added new section [{section}] with {key} = {value}", file=sys.stderr)
    elif not key_set:
        # Add the key=value at the end of the section
        # Find where the section ends
        insert_idx = None
        for idx, line in enumerate(new_lines):
            stripped_line = line.strip()
            if stripped_line.startswith('['):
                if stripped_line.strip('[]').lower() == section.lower():
                    # Find the end of the section
                    insert_idx = idx + 1
                    while insert_idx < len(new_lines) and not new_lines[insert_idx].strip().startswith('['):
                        insert_idx += 1
                    break
        if insert_idx is not None:
            new_lines.insert(insert_idx, f"{key} = {value}\n")
        else:
            new_lines.append(f"{key} = {value}\n")
        print(f"Added {key} = {value} to section [{section}]", file=sys.stderr)

    write_config_lines(new_lines)
    print(f"Config [{section}] {key} = {value} has been written to file.", file=sys.stderr)


def set_admin_password(password: str) -> None:
    """Set the admin (master) password in the configuration file.

    Args:
        password (str): The admin password.
    """
    set_config('options', 'admin_passwd', password)
    print("Admin password has been set.", file=sys.stderr)


def get_redis_defaults() -> Dict[str, Optional[str]]:
    """Compute and return Redis defaults.

    Returns:
        Dict[str, Optional[str]]: The Redis configuration defaults.
    """
    redis_ssl_env: str = os.getenv('REDIS_SSL', 'false')
    redis_ssl: bool = redis_ssl_env.lower() in ['true', '1', 'yes']
    redis_ssl_ca_certs: Optional[str] = (
        "/etc/ssl/certs/ca-certificates.crt" if redis_ssl else None
    )
    return {
        'redis_session': 'true',
        'redis_host': os.getenv('REDIS_HOST', 'redis'),
        'redis_port': os.getenv('REDIS_PORT', '6379'),
        'redis_expire': '432000',
        'redis_username': 'default',
        'redis_password': os.getenv('REDIS_PASSWORD', ''),
        'redis_ssl_ca_certs': redis_ssl_ca_certs
    }


def set_redis_configuration() -> None:
    """Set Redis configuration values in the configuration file."""
    redis_defaults: Dict[str, Optional[str]] = get_redis_defaults()
    for key, value in redis_defaults.items():
        if value is not None:
            set_config('options', key, value)
    print("Redis settings have been set in the configuration file.", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Manage the odoo.conf configuration file")

    parser.add_argument('--defaults', action='store_true',
                        help='Set default configuration values')

    subparsers = parser.add_subparsers(dest='command')

    # 'get' command
    get_parser = subparsers.add_parser('get', help='Get a configuration value')
    get_parser.add_argument('section', type=str, help='Configuration section')
    get_parser.add_argument('key', type=str, help='Configuration key')

    # 'set' command
    set_parser = subparsers.add_parser('set', help='Set a configuration value')
    set_parser.add_argument('section', type=str, help='Configuration section')
    set_parser.add_argument('key', type=str, help='Configuration key')
    set_parser.add_argument('value', type=str, help='Configuration value')

    # '--set-admin-password' option
    parser.add_argument('--set-admin-password', nargs='?', const=True,
                        help='Set the admin password from environment or provided value')

    # '--set-redis-config' option
    parser.add_argument('--set-redis-config', action='store_true',
                        help='Set Redis keys in the configuration file from environment or defaults')

    return parser.parse_args()


def show_config_file() -> None:
    """Display the content of the configuration file."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as configfile:
            print('## odoo_config: Use --help for usage information\n')
            print(configfile.read())
    except OSError as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main function to handle different commands."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    args: argparse.Namespace = parse_args()

    ensure_config_file_exists()

    if args.defaults:
        set_defaults()
    elif args.command == 'get':
        get_config(args.section, args.key)
    elif args.command == 'set':
        set_config(args.section, args.key, args.value)
    elif args.set_admin_password is not None:
        if args.set_admin_password is True:
            # Set from environment variable if no argument is passed
            password_env: Optional[str] = os.getenv('ODOO_MASTER_PASSWORD')
            if not password_env:
                print("Error: Environment variable ODOO_MASTER_PASSWORD is not set or empty.", file=sys.stderr)
                sys.exit(1)
            password: str = password_env
        else:
            # Set from the argument
            password: str = args.set_admin_password
            env_password: Optional[str] = os.getenv('ODOO_MASTER_PASSWORD')
            if env_password and env_password != password:
                print("Warning: Provided password does not match the environment variable ODOO_MASTER_PASSWORD.", file=sys.stderr)
        set_admin_password(password)
    elif args.set_redis_config:
        set_redis_configuration()
    else:
        show_config_file()


if __name__ == '__main__':
    main()
