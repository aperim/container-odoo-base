#!/usr/bin/env python3

"""
geoip_updater.py - Update GeoIP databases.

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-09-12: Initial creation
    2024-09-16: Fixed type annotations for compatibility with older Python versions
"""

import os
import sys
import tarfile
import requests
from typing import Optional, Dict, List

# Constants
GEOIP_DIR: str = "rootfs/usr/share/GeoIP"
GEOIPUPDATE_ACCOUNT_ID: Optional[str] = os.getenv("GEOIPUPDATE_ACCOUNT_ID")
GEOIPUPDATE_LICENSE_KEY: Optional[str] = os.getenv("GEOIPUPDATE_LICENSE_KEY")

DATABASES: List[Dict[str, str]] = [
    {
        "name": "GeoLite2-ASN",
        "primary_url": "https://download.maxmind.com/geoip/databases/GeoLite2-ASN/download?suffix=tar.gz",
        "alt_url": "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-ASN.mmdb"
    },
    {
        "name": "GeoLite2-City",
        "primary_url": "https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz",
        "alt_url": "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb"
    },
    {
        "name": "GeoLite2-Country",
        "primary_url": "https://download.maxmind.com/geoip/databases/GeoLite2-Country/download?suffix=tar.gz",
        "alt_url": "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
    }
]


def ensure_directory_exists(path: str) -> None:
    """Ensure the given directory exists, creating it if necessary."""
    os.makedirs(path, exist_ok=True)


def download_file(url: str, dest: str, account_id: Optional[str] = None, license_key: Optional[str] = None) -> bool:
    """
    Download a file from a URL to a destination.

    Args:
        url (str): The URL to download from.
        dest (str): The destination file path.
        account_id (Optional[str]): Account ID for authentication.
        license_key (Optional[str]): License key for authentication.

    Returns:
        bool: True if download was successful, False otherwise.
    """
    try:
        headers: Dict[str, str] = {}
        if account_id and license_key:
            headers['Authorization'] = f"Basic {account_id}:{license_key}"

        response = requests.get(url, headers=headers, timeout=60, stream=True)
        response.raise_for_status()

        with open(dest, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True

    except (requests.RequestException, IOError) as e:
        print(f"Download error: {e}", file=sys.stderr)
        return False


def extract_tar_gz(file_path: str, extract_path: str) -> None:
    """
    Extract a .tar.gz file to a specified path.

    Args:
        file_path (str): The path to the .tar.gz file.
        extract_path (str): The path to extract the files to.
    """
    try:
        with tarfile.open(file_path, "r:gz") as tar:
            tar.extractall(path=extract_path)
        print(f"Extracted {file_path} to {extract_path}", file=sys.stderr)

    except (tarfile.TarError, IOError) as e:
        print(f"Extraction error: {e}", file=sys.stderr)


def update_geoip_database() -> None:
    """Update GeoIP databases by downloading and extracting them."""
    ensure_directory_exists(GEOIP_DIR)

    for db in DATABASES:
        dest_tar_file = os.path.join("/tmp", f"{db['name']}.tgz")
        dest_mmdb_file = os.path.join(GEOIP_DIR, f"{db['name']}.mmdb")

        primary_success = download_file(
            db["primary_url"], dest_tar_file, GEOIPUPDATE_ACCOUNT_ID, GEOIPUPDATE_LICENSE_KEY)

        if primary_success:
            extract_tar_gz(dest_tar_file, GEOIP_DIR)
        else:
            if not download_file(db["alt_url"], dest_mmdb_file):
                print(f"Could not update the {db['name']} database.", file=sys.stderr)


if __name__ == "__main__":
    update_geoip_database()
