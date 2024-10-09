#!/usr/bin/env python3

"""
addon_updater.py - Ensure shipped Odoo add-ons are present and up-to-date across community, enterprise, and extras.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2023-11-01: Refactored to compare addons across community, enterprise, and extras.
"""

import os
import sys
import shutil
import filecmp
import signal
from types import FrameType
from typing import List, Set, Optional

# Constants for source and target directories
PATHS = [
    ('/usr/share/odoo/community', '/opt/odoo/community'),
    ('/usr/share/odoo/enterprise', '/opt/odoo/enterprise'),
    ('/usr/share/odoo/extras', '/opt/odoo/extras'),
]


def is_symlink_to(source: str, target: str) -> bool:
    """
    Check if the target directory is a symlink to the source directory.

    Args:
        source (str): The source directory path.
        target (str): The target directory path.

    Returns:
        bool: True if target is a symlink to source, False otherwise.
    """
    try:
        # os.path.realpath resolves symlinks to get the actual path
        return os.path.islink(target) and os.path.realpath(target) == os.path.realpath(source)
    except OSError as error:
        print(f'Error checking symlink for {target}: {error}', file=sys.stderr)
        return False


def ensure_directory_exists(path: str) -> None:
    """
    Ensure that the specified directory exists.

    Args:
        path (str): The directory path to ensure exists.

    Raises:
        OSError: If the directory cannot be created.
    """
    if not os.path.exists(path):
        print(f'Creating directory: {path}', file=sys.stderr)
    os.makedirs(path, exist_ok=True)


def copy_addon(source: str, target: str) -> None:
    """
    Copy an addon from the source directory to the target directory.

    Args:
        source (str): The source addon directory.
        target (str): The target addon directory.

    Raises:
        OSError: If the copy operation fails.
    """
    try:
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.copytree(source, target)
        print(f'Copied addon from {source} to {target}', file=sys.stderr)
    except OSError as error:
        print(f'Error copying addon from {source} to {target}: {error}', file=sys.stderr)
        raise


def dirs_are_same(dir1: str, dir2: str) -> bool:
    """
    Check if two directories have the same contents.

    Args:
        dir1 (str): Path to the first directory.
        dir2 (str): Path to the second directory.

    Returns:
        bool: True if the directories are the same, False otherwise.
    """
    comparison = filecmp.dircmp(dir1, dir2)
    if comparison.left_only or comparison.right_only or comparison.diff_files or comparison.funny_files:
        return False
    # Recursively compare subdirectories
    for subdir in comparison.common_dirs:
        dir1_sub = os.path.join(dir1, subdir)
        dir2_sub = os.path.join(dir2, subdir)
        if not dirs_are_same(dir1_sub, dir2_sub):
            return False
    return True


def compare_and_update_addons(source_dir: str, target_dir: str) -> None:
    """
    Compare addons in the source and target directories, and update target addons as needed.

    Args:
        source_dir (str): The source directory containing addons.
        target_dir (str): The target directory to update addons.

    Raises:
        OSError: If there is an error accessing the directories.
    """
    try:
        ensure_directory_exists(target_dir)

        # Get list of addons in source
        source_addons: List[str] = [
            d for d in os.listdir(source_dir) if os.path.isdir(os.path.join(source_dir, d))]
        # Get list of addons in target
        target_addons: List[str] = [
            d for d in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, d))]

        source_set: Set[str] = set(source_addons)
        target_set: Set[str] = set(target_addons)

        # For each addon in the source directory
        for addon in source_set:
            source_addon_path = os.path.join(source_dir, addon)
            target_addon_path = os.path.join(target_dir, addon)

            if os.path.exists(target_addon_path):
                # Compare the directories
                same = dirs_are_same(source_addon_path, target_addon_path)
                if not same:
                    print(f'Updating addon {addon}...', file=sys.stderr)
                    copy_addon(source_addon_path, target_addon_path)
                else:
                    # Addon is up-to-date
                    print(f'Addon {addon} is up-to-date.', file=sys.stderr)
            else:
                # Addon does not exist in target, copy it
                print(f'Adding new addon {addon}...', file=sys.stderr)
                copy_addon(source_addon_path, target_addon_path)

        # Set ownership to odoo:odoo
        os.system(f'chown -R odoo:odoo "{target_dir}"')

    except OSError as error:
        print(f'Error comparing and updating addons: {error}', file=sys.stderr)
        raise


def clean_up(exit_code: int = 0) -> None:
    """
    Clean up resources and exit with the given code.

    Args:
        exit_code (int): Exit code to exit with. Defaults to 0.
    """
    print(f'Exiting with code {exit_code}', file=sys.stderr)
    sys.exit(exit_code)


def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    """
    Handle received signals and perform clean up.

    Args:
        signum (int): The signal number received.
        frame (Optional[FrameType]): The current stack frame.
    """
    print(f'Received signal {signum}, initiating cleanup.', file=sys.stderr)
    clean_up(1)


def main() -> None:
    """
    Main function to update addons across community, enterprise, and extras.
    """
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        for source_dir, target_dir in PATHS:
            print(f'Processing {source_dir} -> {target_dir}', file=sys.stderr)
            if is_symlink_to(source_dir, target_dir):
                print(f'Target {target_dir} is a symlink to source {source_dir}, skipping.', file=sys.stderr)
                continue
            else:
                compare_and_update_addons(source_dir, target_dir)
        clean_up(0)
    except Exception as error:
        print(f'An unexpected error occurred: {error}', file=sys.stderr)
        clean_up(1)


if __name__ == '__main__':
    main()
