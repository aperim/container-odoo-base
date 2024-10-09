#!/usr/bin/env python3

"""
replace_odoo_addons_path.py - Replace Odoo addons path with symlink

Author: [Your Name]
Contact: [Your Contact Information]
History:
    2023-10-25: Initial creation
"""

import os
import shutil
import sys


def replace_odoo_addons_path(source_dir: str, target_dir: str) -> None:
    """
    Replace the target directory with a symlink pointing to the source directory.

    Args:
        source_dir (str): Path to the source directory.
        target_dir (str): Path to the target directory.

    Raises:
        Exception: If the source directory does not exist.
    """
    if not os.path.exists(source_dir):
        raise Exception(f"Source directory {source_dir} does not exist. Exiting.")

    # Remove existing target directory if it exists or is a symlink
    if os.path.exists(target_dir):
        if os.path.islink(target_dir):
            os.unlink(target_dir)
        else:
            shutil.rmtree(target_dir)

    # Create the symlink from target to source
    os.symlink(source_dir, target_dir)

    print(f"Symlink created from {target_dir} to {source_dir}")


def main() -> None:
    """Main function for script."""
    if len(sys.argv) != 3:
        print(
            "Usage: replace_odoo_addons_path.py <source_dir> <target_dir>", file=sys.stderr)
        sys.exit(1)

    source_dir = sys.argv[1]
    target_dir = sys.argv[2]

    try:
        replace_odoo_addons_path(source_dir, target_dir)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
