#!/usr/bin/env bash
#
# backup.sh - Backup PostgreSQL database and filestore.
#
# Purpose:
#   This script creates a backup of a specified PostgreSQL database and its associated filestore.
#   The backup includes both a compressed PostgreSQL dump and a copy of the filestore directory.
#   A hash file is also generated to verify the integrity of the backup file.
#   The Odoo major version from the ODOO_MAJOR_VERSION environment variable is included in the backup file name.
#
# Author: Troy Kelly
# Email: troy@aperim.com
# Date: 25 September 2024
#
# Code History:
#   - Initial version created.
#   - Refactored to meet coding style guidelines.
#   - Added support for default database from POSTGRES_DB environment variable.
#   - Added hash generation for backup integrity verification.
#   - 08 October 2024: Added ODOO_MAJOR_VERSION to backup filename.
#   - 08 October 2024: Updated script to generate ODOO_MAJOR_VERSION from ODOO_VERSION if not set.
#

set -euo pipefail

# Constants
readonly BACKUP_DIR="/mnt/backup"
readonly TIMESTAMP="$(date +"%Y%m%d%H%M%S")"

# Functions

print_usage() {
  echo "Usage: $0 [database_name]"
  echo "If [database_name] is not provided, defaults to the value of POSTGRES_DB environment variable."
}

cleanup() {
  echo "Cleaning up temporary files..."
  rm -rf "${WORKING_DIR}"
}

generate_hash() {
  local backup_file="$1"
  echo "Generating hash for backup file..."
  sha256sum "${backup_file}" > "${backup_file}.sha256"
}

verify_backup() {
  local backup_file="$1"
  echo "Verifying backup integrity..."
  if ! tar -tzf "${backup_file}" > /dev/null; then
    echo "Backup file is corrupted, exiting." >&2
    exit 5
  fi
}

backup_database() {
  local database="$1"
  local cpu_count
  cpu_count=$(nproc)
  echo "Backing up the PostgreSQL database '${database}'..."
  PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    --host="${POSTGRES_HOST}" \
    --username="${POSTGRES_USER}" \
    --no-owner \
    --format=directory \
    --large-objects \
    --verbose \
    --file="${WORKING_DIR}/${database}.dump" \
    --jobs="${cpu_count}" \
    "${database}"
}

backup_filestore() {
  local filestore_path="/var/lib/odoo/filestore/$1"
  if [[ -d "${filestore_path}" ]]; then
    echo "Backing up the filestore..."
    cp -r "${filestore_path}" "${WORKING_DIR}/filestore"
  else
    echo "Filestore directory does not exist, skipping filestore backup."
  fi
}

compress_backup() {
  local backup_name="$1"
  echo "Compressing backup..."
  tar -czvf "${BACKUP_DIR}/${backup_name}.tar.gz" -C "${WORKING_DIR}" .
}

# Main Script

# Handle arguments
DATABASE="${1:-${POSTGRES_DB:-}}"

if [[ -z "${DATABASE}" ]]; then
  echo "Error: No database specified and POSTGRES_DB environment variable is not set." >&2
  print_usage
  exit 1
fi

if [[ -z "${ODOO_MAJOR_VERSION:-}" ]]; then
  if [[ -n "${ODOO_VERSION:-}" ]]; then
    ODOO_MAJOR_VERSION="${ODOO_VERSION%%.*}"
    echo "ODOO_MAJOR_VERSION not set. Using major version '${ODOO_MAJOR_VERSION}' extracted from ODOO_VERSION '${ODOO_VERSION}'."
  else
    echo "Error: Neither ODOO_MAJOR_VERSION nor ODOO_VERSION environment variable is set." >&2
    exit 1
  fi
fi

readonly DATABASE
readonly ODOO_MAJOR_VERSION
readonly BACKUP_NAME="${DATABASE}_${ODOO_MAJOR_VERSION}_${TIMESTAMP}"
readonly WORKING_DIR="/tmp/${BACKUP_NAME}"

# Ensure working directory exists
mkdir -p "${WORKING_DIR}"

trap cleanup EXIT

backup_database "${DATABASE}"
backup_filestore "${DATABASE}"
compress_backup "${BACKUP_NAME}"
generate_hash "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
verify_backup "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

echo "Backup completed successfully. Backup file: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"