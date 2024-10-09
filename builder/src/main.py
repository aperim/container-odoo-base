#!/usr/bin/env python3

"""
main.py - Main script for setting up Odoo directories and cloning repositories.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-09-12: Initial creation
    2024-09-13: Added handling of EXTRAS repositories and improved typing and exception handling.
    2024-10-13: Refactored clone_repo function to resolve GitHub authentication issue.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
from types import FrameType
from typing import Dict, List, Optional, TypedDict

from urllib.parse import urlparse, urlunparse

from geoip_updater import update_geoip_database  # Importing the GeoIP updater function

ROOTFS_PATH = 'rootfs/usr/share/odoo'
TEMP_DIR: Optional[str] = None


class ExtraEntry(TypedDict, total=False):
    """Typed dictionary for defining EXTRAS entries."""

    repo: str
    addons: List[str]
    branch: str
    private: bool


# EXTRAS is a list of dictionaries specifying extra addons to include.
# Each dictionary defines:
# - 'repo': The Git repository URL (e.g., 'github.com/user/repo').
# - 'branch': (optional) The branch to clone. Defaults to 'main'.
# - 'addons': A list of addon directories to copy from the repository.
# - 'private': (optional) A boolean indicating if the repository is private. Defaults to False.
#
# Example:
# EXTRAS = [
#     {
#         'repo': 'github.com/productioncity/odoo-addon-salutation',
#         'branch': 'main',
#         'addons': ['salutation', 'salutation_marketing'],
#         'private': True
#     },
#     {
#         'repo': 'github.com/odoo/odoo-extra-addons',
#         'addons': ['addon_one', 'addon_two'],
#     },
# ]

EXTRAS: List[ExtraEntry] = [
    {
        'repo': 'github.com/productioncity/odoo-addon-salutation',
        'branch': 'main',
        'addons': ['salutation', 'salutation_marketing'],
        'private': True
    },
]


def ensure_directory_exists(path: str) -> None:
    """Ensure the given directory exists, creating it if necessary.

    Args:
        path: The directory path to ensure exists.
    """
    if not os.path.exists(path):
        print(f'Creating directory: {path}', file=sys.stderr)
    os.makedirs(path, exist_ok=True)


def run_command(command: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> None:
    """Run a shell command and raise an error if it fails.

    Args:
        command: List of command arguments to execute.
        cwd: Optional current working directory for the command.
        env: Optional environment variables to pass to the command.

    Raises:
        RuntimeError: If the command fails.
    """
    try:
        result = subprocess.run(
            command, cwd=cwd, check=True, capture_output=True, text=True, env=env
        )
        print(f'Command succeeded: {" ".join(command)}', file=sys.stderr)
        print(result.stdout, file=sys.stderr)
    except subprocess.CalledProcessError as err:
        print(f'Command failed: {err.stderr}', file=sys.stderr)
        raise RuntimeError(f'Command failed: {err.stderr}') from err


def clone_repo(
    url: str,
    branch: str,
    dest: str,
    repo_name: str,
    token: Optional[str] = None
) -> None:
    """Clone a specific branch of a Git repository to the destination.

    Args:
        url: The repository URL to clone.
        branch: The branch to clone.
        dest: The destination directory for the clone.
        repo_name: The name of the repository for logging.
        token: Optional GitHub token for private repositories.

    Raises:
        RuntimeError: If the git clone command fails.
    """
    print(f'Cloning {repo_name} branch {branch} into {dest}', file=sys.stderr)
    git_command: List[str] = ['git', 'clone', '--depth', '1', '--branch', branch, url, dest]

    git_env: Dict[str, str] = os.environ.copy()
    askpass_script: Optional[str] = None

    # Handle GitHub authentication if a token is provided
    if token:
        try:
            # Create a temporary script that outputs the token
            with tempfile.NamedTemporaryFile(mode='w', delete=False, prefix='git_askpass_', suffix='.sh') as tf:
                tf.write('#!/usr/bin/env bash\n')
                tf.write(f'echo "{token}"\n')
                tf.flush()
                os.chmod(tf.name, 0o700)
                askpass_script = tf.name

            # Set environment variables for Git to use the askpass script
            git_env['GIT_ASKPASS'] = askpass_script
            git_env['GIT_TERMINAL_PROMPT'] = '0'
            print('Configured GIT_ASKPASS to provide authentication token.', file=sys.stderr)

            # Run the git clone command with the modified environment
            run_command(git_command, cwd=None, env=git_env)
        finally:
            # Ensure that the temporary askpass script is removed
            if askpass_script and os.path.exists(askpass_script):
                os.remove(askpass_script)
                print('Removed temporary GIT_ASKPASS script.', file=sys.stderr)
    else:
        # Run the git clone command without authentication
        run_command(git_command, cwd=None)


def get_repo_url(repo: str) -> str:
    """Construct the repository URL.

    Args:
        repo: The repository path (e.g., 'github.com/user/repo').

    Returns:
        The full repository URL (e.g., 'https://github.com/user/repo').
    """
    if not repo.startswith('https://'):
        repo_url = f'https://{repo}'
    else:
        repo_url = repo
    return repo_url


def prepare_directory_structure() -> None:
    """Ensure the required directory structure for Odoo is present."""
    community_dest = os.path.join(ROOTFS_PATH, 'community')
    enterprise_dest = os.path.join(ROOTFS_PATH, 'enterprise')
    extras_dest = os.path.join(ROOTFS_PATH, 'extras')

    ensure_directory_exists(community_dest)
    ensure_directory_exists(enterprise_dest)
    ensure_directory_exists(extras_dest)
    print(f'Directory structure prepared at {ROOTFS_PATH}', file=sys.stderr)


def clean_up_directory(path: str) -> None:
    """Remove unnecessary files and directories from a given path.

    Args:
        path: The directory path to clean up.
    """
    for root, dirs, files in os.walk(path):
        for dir_name in dirs:
            if dir_name == '.git':
                shutil.rmtree(os.path.join(root, dir_name))
        for file_name in files:
            if file_name.startswith('.'):
                os.remove(os.path.join(root, file_name))
    print(f'Cleaned up directory: {path}', file=sys.stderr)


def copy_addons_to_target(src_dir: str, target_dir: str) -> None:
    """Copy the contents of the addons directory to the target directory.

    Args:
        src_dir: The source directory containing the addons.
        target_dir: The target directory to copy addons into.
    """
    addons_src = os.path.join(src_dir, 'addons')
    if not os.path.exists(addons_src):
        print(f'Addons directory does not exist in {src_dir}', file=sys.stderr)
        return

    for item in os.listdir(addons_src):
        source_item = os.path.join(addons_src, item)
        dest_item = os.path.join(target_dir, item)
        if os.path.isdir(source_item):
            shutil.copytree(source_item, dest_item, dirs_exist_ok=True)
        else:
            shutil.copy2(source_item, dest_item)
    print(f'Copied addons from {addons_src} to {target_dir}', file=sys.stderr)


def clear_target_directory(path: str) -> None:
    """Clear the contents of a target directory.

    Args:
        path: The directory path to clear.
    """
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
    print(f'Cleared target directory: {path}', file=sys.stderr)


def clean_up(exit_code: int = 0) -> None:
    """Clean up resources and exit with the given exit code.

    Args:
        exit_code: The exit code to use when exiting the script.
    """
    global TEMP_DIR
    if TEMP_DIR and os.path.exists(TEMP_DIR):
        print(f'Removing temporary directory: {TEMP_DIR}', file=sys.stderr)
        shutil.rmtree(TEMP_DIR)
    print(f'Exiting with code {exit_code}', file=sys.stderr)
    sys.exit(exit_code)


def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    """Handle system signals for proper cleanup.

    Args:
        signum: The signal number received.
        frame: The current stack frame (unused).
    """
    print(f'Received signal {signum}, initiating cleanup.', file=sys.stderr)
    clean_up(1)


def clone_odoo_repos() -> None:
    """Clone the Odoo community and enterprise repositories.

    Raises:
        EnvironmentError: If required environment variables are missing.
        RuntimeError: If cloning the repositories fails.
    """
    global TEMP_DIR
    odoo_major_version = os.getenv('ODOO_MAJOR_VERSION')
    odoo_minor_version = os.getenv('ODOO_MINOR_VERSION')
    github_token = os.getenv('GITHUB_TOKEN')
    community_repo = os.getenv('ODOO_COMMUNITY_REPOSITORY', 'github.com/odoo/odoo')
    enterprise_repo = os.getenv('ODOO_ENTERPRISE_REPOSITORY', 'github.com/odoo/enterprise')

    if not all([odoo_major_version, odoo_minor_version, github_token, community_repo, enterprise_repo]):
        # Generate list of missing environment variables for error message
        missing_vars = [var for var in ['ODOO_MAJOR_VERSION', 'ODOO_MINOR_VERSION', 'GITHUB_TOKEN', 'ODOO_COMMUNITY_REPOSITORY', 'ODOO_ENTERPRISE_REPOSITORY'] if not os.getenv(var)]
        error_message = f'Required environment variables are missing. Please set: {", ".join(missing_vars)}'
        print(error_message, file=sys.stderr)
        raise EnvironmentError(error_message)

    branch = f'{odoo_major_version}.{odoo_minor_version}'

    community_dest = os.path.join(ROOTFS_PATH, 'community')
    enterprise_dest = os.path.join(ROOTFS_PATH, 'enterprise')

    clear_target_directory(community_dest)
    clear_target_directory(enterprise_dest)

    TEMP_DIR = tempfile.mkdtemp()
    try:
        # Clone community repository
        community_url = get_repo_url(community_repo)
        clone_repo(community_url, branch, TEMP_DIR, 'Community Repository')
        copy_addons_to_target(TEMP_DIR, community_dest)
        clean_up_directory(community_dest)

        # Clone enterprise repository
        enterprise_url = get_repo_url(enterprise_repo)
        clone_repo(
            enterprise_url, branch, enterprise_dest,
            'Enterprise Repository', token=github_token
        )
        clean_up_directory(enterprise_dest)

        print('Repositories cloned and directories cleaned successfully', file=sys.stderr)
    except (RuntimeError, OSError) as err:
        print(f'Error cloning repositories: {err}', file=sys.stderr)
        raise
    finally:
        if TEMP_DIR and os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            TEMP_DIR = None


def process_extras() -> None:
    """Clone EXTRAS repositories and copy specified addons to ROOTFS_PATH/extras."""
    github_token = os.getenv('GITHUB_TOKEN')
    extras_dest = os.path.join(ROOTFS_PATH, 'extras')
    ensure_directory_exists(extras_dest)

    if not github_token:
        print('GITHUB_TOKEN is not set. Skipping EXTRAS processing.', file=sys.stderr)
        return

    for extra in EXTRAS:
        repo = extra.get('repo')
        addons = extra.get('addons', [])
        if not repo or not addons:
            print(f"Warning: 'repo' or 'addons' key not found in extra {extra}. Skipping.", file=sys.stderr)
            continue

        branch = extra.get('branch', 'main')
        is_private = extra.get('private', False)
        repo_url = get_repo_url(repo)

        temp_dir = tempfile.mkdtemp()
        try:
            if is_private:
                clone_repo(
                    repo_url, branch, temp_dir, repo,
                    token=github_token
                )
            else:
                clone_repo(repo_url, branch, temp_dir, repo)

            for addon in addons:
                addon_src = os.path.join(temp_dir, addon)
                addon_dest = os.path.join(extras_dest, addon)
                if not os.path.exists(addon_src):
                    print(f"Warning: Addon '{addon}' not found in repository '{repo}'", file=sys.stderr)
                    continue
                shutil.copytree(addon_src, addon_dest, dirs_exist_ok=True)
                print(f"Copied addon '{addon}' to '{addon_dest}'", file=sys.stderr)
            print(f"Processed extras from repository '{repo}' successfully.", file=sys.stderr)
        except (RuntimeError, OSError) as err:
            print(f"Warning: Failed to process extra '{repo}'. Error: {err}", file=sys.stderr)
            continue
        finally:
            shutil.rmtree(temp_dir)


def main() -> None:
    """Main function to set up Odoo directories, clone repositories, and update GeoIP databases."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    prepare_directory_structure()
    update_geoip_database()  # Perform GeoIP updates

    try:
        clone_odoo_repos()
        process_extras()
    except EnvironmentError as env_err:
        print(f'Environment error: {env_err}', file=sys.stderr)
        clean_up(1)
    except RuntimeError as run_err:
        print(f'Runtime error: {run_err}', file=sys.stderr)
        clean_up(1)
    except Exception as unexpected_err:
        print(f'An unexpected error occurred: {unexpected_err}', file=sys.stderr)
        clean_up(1)
    else:
        clean_up(0)


if __name__ == '__main__':
    main()
