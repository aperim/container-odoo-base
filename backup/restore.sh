#!/usr/bin/env bash
#
# restore.sh - Restore PostgreSQL database and filestore from backup.
#
# Purpose:
#   This script restores a PostgreSQL database and its associated filestore from a backup.
#   It accepts a database name (defaulting to POSTGRES_DB if set) or a path to a backup file.
#   The script confirms the availability of the database server, safely drops and creates the database,
#   verifies the integrity of the backup file using a hash, and restores the database and filestore.
#   The Odoo major version from the ODOO_MAJOR_VERSION environment variable is verified against the backup file.
#
# Author: Troy Kelly
# Email: troy@aperim.com
# Date: 25 September 2024
#
# Code History:
#   - Initial version created.
#   - 08 October 2024: Added ODOO_MAJOR_VERSION verification during restore; only restore backups matching current ODOO_MAJOR_VERSION.
#   - 08 October 2024: Updated script to generate ODOO_MAJOR_VERSION from ODOO_VERSION if not set.
#

set -euo pipefail

# Constants
readonly BACKUP_DIR="/mnt/backup"
readonly MAX_WAIT_TIME=5400  # 90 minutes in seconds
readonly CHECK_INTERVAL=10   # seconds to wait between checks

# Variables
HASH_CHECK=true
DATABASE="${POSTGRES_DB:-}"
BACKUP_FILE=""
NO_HASH_CHECK=false

# Functions

print_usage() {
  echo "Usage: $0 [--no-hash-check] [database_name|backup_file]"
  echo "Options:"
  echo "  --no-hash-check    Ignore hash check of backup file."
  echo "If no database_name or backup_file is provided, defaults to POSTGRES_DB environment variable."
  echo "If POSTGRES_DB is not set, the most recent backup will be restored."
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-hash-check)
        NO_HASH_CHECK=true
        shift
        ;;
      -*)
        echo "Unknown option: $1"
        print_usage
        exit 1
        ;;
      *)
        if [[ -z "${DATABASE}" && -z "${BACKUP_FILE}" ]]; then
          if [[ -f "$1" ]]; then
            BACKUP_FILE="$1"
          else
            DATABASE="$1"
          fi
        else
          echo "Multiple databases or backup files specified."
          print_usage
          exit 1
        fi
        shift
        ;;
    esac
  done
}

wait_for_db() {
  local start_time
  start_time=$(date +%s)
  echo "Waiting for database server to become available..."

  until PGPASSWORD="${POSTGRES_PASSWORD}" pg_isready -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d postgres; do
    sleep "${CHECK_INTERVAL}"
    if [[ $(( $(date +%s) - start_time )) -gt "${MAX_WAIT_TIME}" ]]; then
      echo "Database server did not become available within ${MAX_WAIT_TIME} seconds."
      exit 1
    fi
  done
  echo "Database server is available."
}

drop_database() {
  local database="$1"
  echo "Dropping existing database '${database}' if it exists..."
  PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d postgres -c "DROP DATABASE IF EXISTS \"${database}\" WITH (FORCE);" || {
    echo "Failed to drop database '${database}'."
    exit 1
  }
  echo "Database '${database}' dropped successfully."
}

create_database() {
  local database="$1"
  echo "Creating database '${database}'..."
  PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST}" -U "${POSTGRES_USER}" -d postgres -c "CREATE DATABASE \"${database}\";" || {
    echo "Failed to create database '${database}'."
    exit 1
  }
  echo "Database '${database}' created successfully."
}

find_most_recent_backup() {
  echo "Looking for the most recent backup for Odoo version '${ODOO_MAJOR_VERSION}'..."
  BACKUP_FILE=$(find "${BACKUP_DIR}" -type f -name "*_${ODOO_MAJOR_VERSION}_*.tar.gz" -printf "%T@ %p\n" | sort -n | awk '{print $2}' | tail -1)
  if [[ -z "${BACKUP_FILE}" ]]; then
    echo "No backup files found for Odoo version '${ODOO_MAJOR_VERSION}' in ${BACKUP_DIR}."
    exit 1
  fi
  echo "Most recent backup is ${BACKUP_FILE}."
}

verify_backup() {
  local backup_file="$1"
  local hash_file="${backup_file}.sha256"

  if [[ "${NO_HASH_CHECK}" == true ]]; then
    echo "Hash check is disabled (--no-hash-check). Skipping hash verification."
    return
  fi

  if [[ ! -f "${hash_file}" ]]; then
    echo "Hash file ${hash_file} does not exist."
    echo "To proceed without hash verification, use the --no-hash-check option."
    exit 1
  fi

  echo "Verifying backup integrity using hash..."
  if ! sha256sum --check --status "${hash_file}"; then
    echo "Hash verification failed for backup file ${backup_file}."
    echo "To proceed without hash verification, use the --no-hash-check option."
    exit 1
  fi
  echo "Backup file integrity verified."
}

extract_backup() {
  local backup_file="$1"
  echo "Extracting backup file..."
  mkdir -p "${WORKING_DIR}"
  tar -xzvf "${backup_file}" -C "${WORKING_DIR}"
}

restore_database() {
  local database="$1"
  local dump_file="${WORKING_DIR}/${database}.dump"
  local cpu_count
  cpu_count=$(nproc)
  echo "Restoring database from dump..."
  PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
    --host="${POSTGRES_HOST}" \
    --username="${POSTGRES_USER}" \
    --dbname="${database}" \
    --no-owner \
    --format=directory \
    --jobs="${cpu_count}" \
    --verbose \
    "${dump_file}"
}

restore_filestore() {
  local filestore_source="${WORKING_DIR}/filestore"
  local filestore_dest="/var/lib/odoo/filestore/${DATABASE}"
  if [[ -d "${filestore_source}" ]]; then
    echo "Restoring filestore..."
    mkdir -p "${filestore_dest}"
    cp -r "${filestore_source}/." "${filestore_dest}/"
  else
    echo "No filestore directory found in backup. Skipping filestore restore."
  fi
}

cleanup() {
  echo "Cleaning up temporary files..."
  rm -rf "${WORKING_DIR}"
}

extract_backup_info() {
  local backup_file="$1"
  local backup_filename
  local backup_basename
  local parts
  local len
  
  backup_filename="$(basename "${backup_file}")"
  backup_basename="${backup_filename%.tar.gz}"  # Remove .tar.gz

  IFS='_' read -ra parts <<< "${backup_basename}"
  len="${#parts[@]}"

  if (( len < 3 )); then
    echo "Error: Invalid backup filename format."
    exit 1
  fi

  BACKUP_TIMESTAMP="${parts[$len-1]}"
  BACKUP_ODOO_VERSION="${parts[$len-2]}"
  
  # Join all parts except the last two to reconstruct the database name
  BACKUP_DATABASE="${parts[0]}"
  for (( i=1; i<($len-2); i++ )); do
    BACKUP_DATABASE="${BACKUP_DATABASE}_${parts[i]}"
  done

  echo "Backup info extracted:"
  echo "  Database: ${BACKUP_DATABASE}"
  echo "  Odoo Version: ${BACKUP_ODOO_VERSION}"
  echo "  Timestamp: ${BACKUP_TIMESTAMP}"
}

compare_odoo_version() {
  if [[ "${ODOO_MAJOR_VERSION}" != "${BACKUP_ODOO_VERSION}" ]]; then
    echo "Odoo version mismatch."
    echo "Current Odoo version: '${ODOO_MAJOR_VERSION}', Backup Odoo version: '${BACKUP_ODOO_VERSION}'."
    echo "Cannot restore backup with a different Odoo version."
    exit 1
  fi
}

# Main Script

if [[ -z "${ODOO_MAJOR_VERSION:-}" ]]; then
  if [[ -n "${ODOO_VERSION:-}" ]]; then
    ODOO_MAJOR_VERSION="${ODOO_VERSION%%.*}"
    echo "ODOO_MAJOR_VERSION not set. Using major version '${ODOO_MAJOR_VERSION}' extracted from ODOO_VERSION '${ODOO_VERSION}'."
  else
    echo "Error: Neither ODOO_MAJOR_VERSION nor ODOO_VERSION environment variable is set." >&2
    exit 1
  fi
fi

readonly ODOO_MAJOR_VERSION

parse_args "$@"

if [[ -z "${DATABASE}" && -z "${BACKUP_FILE}" ]]; then
  DATABASE="${POSTGRES_DB:-}"
fi

if [[ -z "${DATABASE}" && -z "${BACKUP_FILE}" ]]; then
  find_most_recent_backup
elif [[ -n "${DATABASE}" && -z "${BACKUP_FILE}" ]]; then
  echo "Looking for the most recent backup for database '${DATABASE}' and Odoo version '${ODOO_MAJOR_VERSION}'..."
  BACKUP_FILE=$(find "${BACKUP_DIR}" -type f -name "${DATABASE}_${ODOO_MAJOR_VERSION}_*.tar.gz" -printf "%T@ %p\n" | sort -n | awk '{print $2}' | tail -1)
  if [[ -z "${BACKUP_FILE}" ]]; then
    echo "No backup files found for database '${DATABASE}' and Odoo version '${ODOO_MAJOR_VERSION}' in ${BACKUP_DIR}."
    exit 1
  fi
elif [[ -n "${BACKUP_FILE}" ]]; then
  if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "Backup file '${BACKUP_FILE}' does not exist."
    exit 1
  fi
fi

extract_backup_info "${BACKUP_FILE}"

compare_odoo_version

DATABASE="${DATABASE:-${BACKUP_DATABASE}}"
readonly DATABASE
readonly WORKING_DIR="/tmp/restore_${DATABASE}"

trap cleanup EXIT

wait_for_db
verify_backup "${BACKUP_FILE}"
drop_database "${DATABASE}"
create_database "${DATABASE}"
extract_backup "${BACKUP_FILE}"
restore_database "${DATABASE}"
restore_filestore

echo "Database '${DATABASE}' restored successfully from backup '${BACKUP_FILE}'."