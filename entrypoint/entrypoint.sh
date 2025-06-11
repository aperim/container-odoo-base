#!/usr/bin/env bash
#
# entrypoint.sh - Entrypoint script for the Odoo Docker container
#
# Author: Troy Kelly
# Contact: troy@aperim.com
# History:
#   2024-09-13: Initial creation
#   2024-10-13: Added argument handling, logging to STDERR, UID/GID modification, and permissions function
#   2024-10-20: Modified to include user-passed parameters when executing Odoo
#   2024-10-25: Refactored database destruction to honor TLS settings and handle active connections
#   2024-10-30: Enhanced start_odoo function to respect user-supplied options
#   2024-09-16: Ensured init lock is released on script termination
#   2024-09-16: Added PGBOUNCER support and improved failure handling in initialize_odoo
#   2024-09-16: Fixed compatibility issues with older Bash versions
#   2024-10-01: Added support for optional additional Odoo addons in /mnt/addons
#   2024-10-04: Added upgrade_odoo function to upgrade modules on startup unless ODOO_NO_AUTO_UPGRADE is set
#   2024-10-05: Prevent upgrades being executed on every startup by checking for a timestamp file

set -Eeuo pipefail

# Constants
readonly DESTROY_SEMAPHORE="/etc/odoo/.destroy"
readonly SCAFFOLDED_SEMAPHORE="/etc/odoo/.scaffolded"
readonly ADDON_UPDATE_TIMESTAMP="/etc/odoo/.timestamp"
readonly INIT_LOCK="initlead"
readonly UPGRADE_LOCK="upgradelead"
# Languages supported by default when ODOO_LANGUAGES env var isn't provided.
readonly DEFAULT_ODOO_LANGUAGES="en_AU,en_CA,en_IN,en_NZ,en_UK,en_US"

# Global variables
WORKERS=0
LISTEN_INTERFACE="0.0.0.0"
INIT_LOCK_HELD=false    # Track whether init lock is held
UPGRADE_LOCK_HELD=false # Track whether upgrade lock is held

# Trap signals and errors for cleanup
trap 'cleanup 1' SIGINT SIGTERM
trap 'cleanup $?' ERR EXIT

# Function to perform cleanup tasks before exiting
cleanup() {
  local exit_code="${1:-1}"
  log "Cleaning up (exit code: $exit_code)..."
  if [[ "$INIT_LOCK_HELD" == true ]]; then
    log "Releasing init lock due to termination..."
    release_init_lock
  fi
  if [[ "$UPGRADE_LOCK_HELD" == true ]]; then
    log "Releasing upgrade lock due to termination..."
    release_upgrade_lock
  fi
  exit "$exit_code"
}

# Function to log messages with timestamps to STDERR
log() {
  local message="$1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') [entrypoint] $message" >&2
}

# Function to parse blocklist
parse_blocklist() {
  local blocklist_var="$1"
  local blocklist=()
  IFS=', ' read -r -a blocklist <<<"$blocklist_var"
  echo "${blocklist[@]}"
}

# Function to check if an addon is in the blocklist
is_blocked_addon() {
  local addon_name="$1"
  shift
  local blocklist=("$@")
  for blocked in "${blocklist[@]}"; do
    if [[ "$addon_name" =~ $blocked ]]; then
      return 0
    fi
  done
  return 1
}

# -----------------------------------------------------------------------------
# Generic helper to build the list of addons residing in given paths, honouring 
#  * ODOO_LANGUAGES         – localisation filter (same algorithm as initialise)
#  * ODOO_ADDON_INIT_BLOCKLIST – comma-separated glob patterns to exclude
# It exposes semantically identical behaviour to the collect_addons function
# previously defined inside initialize_odoo so it can be reused by other
# top-level helpers (e.g. upgrade_odoo) without requiring initialization to run
# first.
# -----------------------------------------------------------------------------
collect_addons() {
  # Purpose: populate the provided bash array with addon names ordered by
  # dependency, deduplicated and filtered according to localisation and
  # block-list rules.
  # Globals:
  #   ODOO_LANGUAGES, ODOO_ADDON_INIT_BLOCKLIST, DEFAULT_ODOO_LANGUAGES
  # Arguments:
  #   $1 – nameref to output array variable.
  #   $@ – list of addon root directories to scan.
  local -n _out_array=$1
  shift
  local _addon_paths=("$@")

  # -------------------------------------------------------------------------
  # Build list of supported country codes from languages
  # -------------------------------------------------------------------------
  local _langs="${ODOO_LANGUAGES:-$DEFAULT_ODOO_LANGUAGES}"
  declare -A _seen_cc=()
  local -a _country_codes=()
  local _lang
  IFS=',' read -ra _lang <<<"$_langs"
  for _l in "${_lang[@]}"; do
    if [[ "$_l" == *_* ]]; then
      local _cc="${_l#*_}"
      _cc="${_cc,,}"
      if [[ -z "${_seen_cc[$_cc]:-}" ]]; then
        _country_codes+=("$_cc")
        _seen_cc[$_cc]=1
      fi
    fi
  done

  # Parse blocklist (comma / space separated)
  local _block_raw="${ODOO_ADDON_INIT_BLOCKLIST:-}"
  local -a _blocklist=()
  if [[ -n "$_block_raw" ]]; then
    _block_raw="${_block_raw//,/ }"
    read -r -a _blocklist <<<"$_block_raw"
  fi

  # Iterate directories, gather module -> manifest path mapping
  local -A _mod2path=()
  local -a _discover_order=()
  local _addon_path _dir _addon_name
  for _addon_path in "${_addon_paths[@]}"; do
    [[ -d "$_addon_path" ]] || { log "Addon path '$_addon_path' not found"; continue; }

    for _dir in "$_addon_path"/*; do
      [[ -d "$_dir" && -f "$_dir/__manifest__.py" ]] || continue

      _addon_name="$(basename "$_dir")"

      # Blocklist filter
      if is_blocked_addon "$_addon_name" "${_blocklist[@]}"; then
        log "collect_addons: Skipping blocked addon '$_addon_name'"
        continue
      fi

      # Localisation filter for l10n modules
      if [[ "$_addon_name" == *"l10n"* ]]; then
        # Extract candidate country codes from addon name
        IFS='_' read -ra _parts <<<"$_addon_name"
        local -a _addon_cc=()
        local _p
        for _p in "${_parts[@]}"; do
          if [[ "$_p" =~ ^[a-z]{2}$ ]]; then
            _addon_cc+=("$_p")
          fi
        done

        local _matched=false
        local _acc
        for _acc in "${_addon_cc[@]}"; do
          if [[ " ${_country_codes[*]} " == *" $_acc "* ]]; then
            _matched=true; break
          fi
        done

        if [[ "$_matched" == false ]]; then
          log "collect_addons: Skipping localisation addon '$_addon_name' (lang filter)"
          continue
        fi
      fi

      # Store mapping and skip duplicates to keep first discovered path
      if [[ -z "${_mod2path[$_addon_name]:-}" ]]; then
        _mod2path[$_addon_name]="$_dir"
        _discover_order+=("$_addon_name")
      fi
    done
  done

  # -------------------------------------------------------------------------
  # Deduplicate while preserving discovery order
  # -------------------------------------------------------------------------
  local -a _unique_modules=("${_discover_order[@]}")

  # -------------------------------------------------------------------------
  # Dependency ordering using Python for robustness.
  # We pass two JSON arrays via environment variables (module names / paths)
  # and receive a space-separated list in correct topological order.
  # -------------------------------------------------------------------------
  local _pybin
  if command -v python3 >/dev/null 2>&1; then
    _pybin="python3"
  elif command -v python >/dev/null 2>&1; then
    _pybin="python"
  else
    log "Python interpreter not found – using discovery order for dependency resolution."
    _out_array+=("${_unique_modules[@]}")
    return
  fi

  local _json_modules _json_paths
  _json_modules=$(printf '%s\n' "${_unique_modules[@]}" | $_pybin -c 'import json,sys;print(json.dumps(sys.stdin.read().strip().split()))')
  # parallel list of paths matching module array order
  local _tmp_paths=()
  for _m in "${_unique_modules[@]}"; do
    _tmp_paths+=("${_mod2path[$_m]}")
  done
  _json_paths=$(printf '%s\n' "${_tmp_paths[@]}" | $_pybin -c 'import json,sys;print(json.dumps(sys.stdin.read().strip().split()))')

  local _sorted
  _sorted=$(MODULES="$_json_modules" PATHS="$_json_paths" $_pybin - <<'PY'
import os, json, ast, sys, os.path
mods = json.loads(os.environ['MODULES'])
paths = json.loads(os.environ['PATHS'])
mod2path = dict(zip(mods, paths))

# Build dependency dict
deps = {}
for mod, path in mod2path.items():
    try:
        with open(os.path.join(path, '__manifest__.py'), 'r') as f:
            manifest = ast.literal_eval(f.read())
            deps[mod] = manifest.get('depends', []) or []
    except Exception:
        deps[mod] = []

# Topological sort
visited = {}
order = []

def visit(m):
    state = visited.get(m, 0)
    if state == 1:
        # Already ordered
        return
    if state == -1:
        # Currently visiting, cycle detected – ignore order constraints inside the cycle.
        return
    visited[m] = -1
    for d in deps.get(m, []):
        if d in deps:  # only care dependencies present in our list
            visit(d)
    visited[m] = 1
    order.append(m)

for m in mods:
    visit(m)

print(' '.join(order))
PY
)

  # shellcheck disable=SC2206
  _unique_modules=( ${_sorted} )

  # Populate caller's array variable
  _out_array+=("${_unique_modules[@]}")
}

# Function to handle custom commands
handle_custom_command() {
  # Execute custom command provided as arguments
  log "Executing custom command: $*"
  exec "$@"
}

# Function to modify UID and GID of the 'odoo' user if UID and/or GID environment variables are set
modify_uid_gid() {
  local target_uid="${PUID:-}"
  local target_gid="${PGID:-}"
  local current_uid
  local current_gid

  if [[ -n "$target_uid" || -n "$target_gid" ]]; then
    log "Modifying 'odoo' user UID and/or GID..."

    current_uid=$(id -u odoo)
    current_gid=$(id -g odoo)

    if [[ -n "$target_gid" && "$target_gid" != "$current_gid" ]]; then
      log "Changing GID from $current_gid to $target_gid"
      groupmod -o -g "$target_gid" odoo
    fi

    if [[ -n "$target_uid" && "$target_uid" != "$current_uid" ]]; then
      log "Changing UID from $current_uid to $target_uid"
      usermod -o -u "$target_uid" odoo
    fi

    log "UID/GID modification completed."
  fi
}

# Function to ensure correct permissions on critical files and folders
ensure_permissions() {
  log "Ensuring correct permissions on critical files and folders..."

  # Change ownership for /var/lib/odoo and /etc/odoo as in the original script
  # This seems to be unnecessary and has been disabled
  # chown -R odoo:odoo /var/lib/odoo /etc/odoo
  # log "Changed ownership for /var/lib/odoo and /etc/odoo."

  # Define source and target directories as per the addon updater
  local sources=(
    "/usr/share/odoo/community"
    "/usr/share/odoo/enterprise"
    "/usr/share/odoo/extras"
  )
  local targets=(
    "/opt/odoo/community"
    "/opt/odoo/enterprise"
    "/opt/odoo/extras"
  )

  # Ensure both arrays have the same length
  if [[ "${#sources[@]}" -ne "${#targets[@]}" ]]; then
    log "Source and target directories count mismatch."
    exit 1
  fi

  # Iterate over each source and corresponding target
  for ((i = 0; i < ${#sources[@]}; i++)); do
    local source="${sources[i]}"
    local target="${targets[i]}"

    if [[ -e "$target" ]]; then
      if [[ -L "$target" ]]; then
        # It's a symbolic link; determine its target
        local symlink_target
        symlink_target=$(readlink -f "$target") || {
          log "Failed to resolve symlink for '$target'. Skipping."
          continue
        }

        if [[ "$symlink_target" == "$source" ]]; then
          log "Skipping permission change for symlinked path '$target' pointing to '$source'."
        else
          log "Changing ownership for symlinked path '$target' pointing to '$symlink_target'."
          chown -R odoo:odoo "$target" || {
            log "Failed to change ownership for symlinked path '$target'."
            exit 1
          }
        fi
      else
        # It's a regular directory; change ownership
        log "Changing ownership for directory '$target'."
        chown -R odoo:odoo "$target" || {
          log "Failed to change ownership for directory '$target'."
          exit 1
        }
      fi
    else
      log "Path '$target' does not exist. Skipping."
    fi
  done

  log "Permissions have been ensured for targeted directories."
}

# Step 1: Wait for Redis to become available
wait_for_redis() {
  log "Waiting for Redis to become available..."

  lock-handler wait || {
    log "Failed to connect to Redis."
    exit 1
  }

  log "Redis is available."
}

# Step 2: Wait for PostgreSQL and PGBouncer to become fully available
wait_for_postgres() {
  log "Waiting for PostgreSQL and PGBouncer to become available..."

  # Set POSTGRES variables
  export POSTGRES_USER="${POSTGRES_USER:-odoo}"
  export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-odoo}"
  export POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
  export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  export POSTGRES_DB="${POSTGRES_DB:-odoo}"
  export POSTGRES_SSL_MODE="${POSTGRES_SSL_MODE:-disable}"
  export POSTGRES_SSL_CERT="${POSTGRES_SSL_CERT:-}"
  export POSTGRES_SSL_KEY="${POSTGRES_SSL_KEY:-}"
  export POSTGRES_SSL_ROOT_CERT="${POSTGRES_SSL_ROOT_CERT:-}"
  export POSTGRES_SSL_CRL="${POSTGRES_SSL_CRL:-}"

  # Set PGBOUNCER variables
  export PGBOUNCER_HOST="${PGBOUNCER_HOST:-}"
  export PGBOUNCER_PORT="${PGBOUNCER_PORT:-5432}"
  export PGBOUNCER_SSL_MODE="${PGBOUNCER_SSL_MODE:-disable}"

  wait-for-postgres || {
    log "Failed to connect to PostgreSQL or PGBouncer."
    exit 1
  }

  log "PostgreSQL and PGBouncer are available."
}

# Step 3: Attempt to get a Redis lock at "initlead"
acquire_init_lock() {
  log "Acquiring init lock '${INIT_LOCK}'..."

  if lock-handler acquire "${INIT_LOCK}" 10800; then
    log "Init lock acquired."
    INIT_LOCK_HELD=true # Lock is now held
    return 0
  else
    log "Init lock not acquired. Another instance is handling initialization."
    return 1
  fi
}

wait_for_init_lock() {
  log "Waiting for init lock '${INIT_LOCK}'..."

  if lock-handler wait "${INIT_LOCK}"; then
    log "Init lock acquired."
    return 0
  else
    log "Failed to acquire init lock."
    return 1
  fi
}

# Function to execute psql commands with proper environment variables
# Globals:
#   POSTGRES_USER
#   POSTGRES_PASSWORD
#   POSTGRES_HOST
#   POSTGRES_PORT
#   POSTGRES_SSL_MODE
#   POSTGRES_SSL_CERT
#   POSTGRES_SSL_KEY
#   POSTGRES_SSL_ROOT_CERT
#   POSTGRES_SSL_CRL
# Arguments:
#   $1: Database name to connect to.
#   $2: SQL command to execute.
# Returns:
#   The exit code of the psql command.
execute_psql_command() {
  local dbname="$1"
  local sql_command="$2"

  # Set PostgreSQL environment variables
  export PGPASSWORD="${POSTGRES_PASSWORD:-}"
  export PGHOST="${POSTGRES_HOST:-}"
  export PGPORT="${POSTGRES_PORT:-}"
  export PGUSER="${POSTGRES_USER:-}"
  export PGDATABASE="${dbname}"
  export PGSSLMODE="${POSTGRES_SSL_MODE:-disable}"

  if [[ -n "${POSTGRES_SSL_CERT:-}" ]]; then
    export PGSSLCERT="${POSTGRES_SSL_CERT}"
  fi
  if [[ -n "${POSTGRES_SSL_KEY:-}" ]]; then
    export PGSSLKEY="${POSTGRES_SSL_KEY}"
  fi
  if [[ -n "${POSTGRES_SSL_ROOT_CERT:-}" ]]; then
    export PGSSLROOTCERT="${POSTGRES_SSL_ROOT_CERT}"
  fi
  if [[ -n "${POSTGRES_SSL_CRL:-}" ]]; then
    export PGSSLCRL="${POSTGRES_SSL_CRL}"
  fi

  # Execute the SQL command via standard input to handle special characters properly
  if ! printf '%s\n' "${sql_command}" | psql --no-psqlrc --quiet; then
    unset PGPASSWORD PGHOST PGPORT PGUSER PGDATABASE PGSSLMODE PGSSLCERT PGSSLKEY PGSSLROOTCERT PGSSLCRL
    return 1
  fi

  unset PGPASSWORD PGHOST PGPORT PGUSER PGDATABASE PGSSLMODE PGSSLCERT PGSSLKEY PGSSLROOTCERT PGSSLCRL
  return 0
}

# Function to check if /mnt/addons contains any valid addons with __manifest__.py files
# Returns:
#   0 if /mnt/addons exists and contains at least one valid addon
#   1 otherwise
has_valid_addons_in_mnt() {
  log "Checking for valid addons in /mnt/addons..."
  if [[ -d "/mnt/addons" ]]; then
    for dir in /mnt/addons/*; do
      if [[ -d "$dir" && -f "$dir/__manifest__.py" ]]; then
        log "Found valid addon in /mnt/addons: $(basename "$dir")"
        return 0 # Found at least one valid addon
      fi
    done
  fi
  log "No valid addons found in /mnt/addons."
  return 1 # No valid addons found
}

# Function to get the list of addon paths, including /mnt/addons if it contains valid addons
# Globals:
#   None
# Arguments:
#   None
# Outputs:
#   Echoes the comma-separated list of addon paths
get_addons_paths() {
  local addons_paths=("/opt/odoo/community" "/opt/odoo/enterprise" "/opt/odoo/extras")
  if has_valid_addons_in_mnt; then
    addons_paths+=("/mnt/addons")
  fi
  # Join the addons paths by comma and echo
  IFS=','
  echo "${addons_paths[*]}"
}

# Function to restore the Odoo instance from a backup
# Globals:
#   None
# Arguments:
#   None
# Outputs:
#   Logs the status of the restore process
#   Creates a semaphore file if the restore completes successfully
# Returns:
#   0 if the restore completes successfully, 1 otherwise
restore() {
  log "Restoring Odoo instance..."
  if /usr/local/sbin/restore; then
    log "Restore completed successfully. Creating scaffolded semaphore file."
    touch "${SCAFFOLDED_SEMAPHORE}"
    return 0
  else
    log "Restore failed."
    return 1
  fi
}

# Function to regenerate Odoo assets
# Globals:
#   None
# Arguments:
#   None
# Outputs:
#   Logs the status of the regenerate process
# Returns:
#   0 if the regenerate completes successfully, 1 otherwise
regenerate() {
  log "Regenerating Odoo assets..."
  if /usr/local/sbin/odoo-regenerate-assets; then
    log "Regenerate completed successfully. Creating scaffolded semaphore file."
    return 0
  else
    log "Restore failed."
    return 1
  fi
}

# Function to determine if an update is needed based on timestamp comparison
# Globals:
#   ODOO_ADDONS_TIMESTAMP
#   ADDON_UPDATE_TIMESTAMP
# Arguments:
#   None
# Outputs:
#   Logs the status of the update check
# Returns:
#   0 if update is needed, 1 otherwise
update_needed() {
  local build_timestamp="${ODOO_ADDONS_TIMESTAMP:-}"
  local timestamp_file="${ADDON_UPDATE_TIMESTAMP}"
  local existing_timestamp=""

  # Validate the build timestamp
  if [[ -z "$build_timestamp" ]]; then
    log "Build timestamp is not set. Assuming no update is needed."
    return 1
  fi
  if ! [[ "$build_timestamp" =~ ^[0-9]+$ ]]; then
    log "Invalid build timestamp '$build_timestamp'. Assuming no update is needed."
    return 1
  fi

  # Check if the timestamp file exists
  if [[ -f "$timestamp_file" ]]; then
    existing_timestamp="$(cat "$timestamp_file")"

    # Validate the existing timestamp
    if ! [[ "$existing_timestamp" =~ ^[0-9]+$ ]]; then
      log "Invalid existing timestamp '$existing_timestamp'. Update is needed."
      return 0
    fi

    # Compare the timestamps
    if ((existing_timestamp < build_timestamp)); then
      log "Existing timestamp ($existing_timestamp) is less than build timestamp ($build_timestamp). Update is needed."
      return 0
    else
      log "Existing timestamp ($existing_timestamp) is greater than or equal to build timestamp ($build_timestamp). No update needed."
      return 1
    fi
  else
    log "Timestamp file does not exist. Update is needed."
    return 0
  fi
}

# Function to update the timestamp file with fallback locking mechanism
# Globals:
#   ODOO_ADDONS_TIMESTAMP
#   ADDON_UPDATE_TIMESTAMP
# Arguments:
#   None
# Outputs:
#   Logs the status of the timestamp update
# Returns:
#   0 if successful, non-zero otherwise
update_timestamp_file() {
  local timestamp="${ODOO_ADDONS_TIMESTAMP}"
  local timestamp_file="${ADDON_UPDATE_TIMESTAMP}"
  local temp_file="${timestamp_file}.tmp"
  local lock_file="${timestamp_file}.lock"
  local lock_dir="${timestamp_file}.lockdir"
  local use_flock=true

  # Try to acquire lock using flock
  exec 300>"$lock_file"
  if ! flock -n 300; then
    log "flock not supported or lock acquisition failed. Falling back to directory-based locking."
    exec 300>&-
    rm -f "$lock_file"
    use_flock=false
  fi

  if [[ "$use_flock" == true ]]; then
    # Proceed with flock-based locking
    _write_timestamp_file "$temp_file" "$timestamp_file"
    # Release the lock
    flock -u 300
    exec 300>&-
    rm -f "$lock_file"
  else
    # Fallback to directory-based locking using mkdir
    if mkdir "$lock_dir" 2>/dev/null; then
      # Acquired the lock
      _write_timestamp_file "$temp_file" "$timestamp_file"
      # Release the lock by removing the directory
      rmdir "$lock_dir"
    else
      log "Another process is updating the timestamp file. Exiting."
      return 1
    fi
  fi

  log "Timestamp file updated successfully."
  return 0
}

# Helper function to write the timestamp file
_write_timestamp_file() {
  local temp_file="$1"
  local timestamp_file="$2"

  # Write the timestamp to a temporary file
  if ! echo "$timestamp" >"$temp_file"; then
    log "Failed to write to temporary timestamp file."
    return 1
  fi

  # Move the temporary file to the timestamp file atomically
  if ! mv "$temp_file" "$timestamp_file"; then
    log "Failed to move temporary file to timestamp file."
    return 1
  fi

  # Set the appropriate ownership and permissions
  if ! chown odoo:odoo "$timestamp_file"; then
    log "Failed to set ownership on the timestamp file."
    return 1
  fi

  return 0
}

# Step 4: Handle initialization if the lock is acquired
handle_initialization() {
  # Step 4.1: Ensure addons are up-to-date
  log "Updating Odoo addons..."
  odoo-addon-updater || {
    log "Failed to update Odoo addons."
    release_init_lock
    exit 1
  }

  odoo-config --defaults || {
    log "Failed to set Odoo configuration defaults."
    release_init_lock
    exit 1
  }

  # Step 4.2: Check for destroy semaphore file
  if [[ -f "${DESTROY_SEMAPHORE}" ]]; then
    log "Destroy semaphore detected."
    perform_destroy
  fi

  # Step 4.3: Check for scaffolded semaphore file
  if [[ ! -f "${SCAFFOLDED_SEMAPHORE}" ]]; then
    log "Scaffolded semaphore not found. Letting postgres warm up (3 minutes)..."
    sleep 180
    wait_for_postgres
    log "Postgres is ready. Checking for restore..."
    if ! restore; then
      log "No restore files or restore failed."
      if [[ ! -f "${DESTROY_SEMAPHORE}" ]]; then
        perform_destroy
      fi
      initialize_odoo
    else
      regenerate
      log "Restore completed successfully. Creating scaffolded semaphore file."
      touch "${SCAFFOLDED_SEMAPHORE}"
    fi
  fi

  # Step 4.4: Release the init lock
  release_init_lock
}

# Function to perform destroy operations
perform_destroy() {
  log "Performing destroy operations..."

  # Terminate all connections to the database
  log "Terminating all connections to database '${POSTGRES_DB}'..."
  local terminate_sql
  terminate_sql=$(
    cat <<EOF
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '${POSTGRES_DB}'
  AND pid <> pg_backend_pid();
EOF
  )
  if ! execute_psql_command "postgres" "${terminate_sql}"; then
    log "Failed to terminate connections to database '${POSTGRES_DB}'."
    release_init_lock
    exit 1
  fi

  # Destroy the database via psql
  log "Destroying the database '${POSTGRES_DB}'..."

  if ! execute_psql_command "postgres" "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\" WITH (FORCE);"; then
    log "Failed to drop database '${POSTGRES_DB}'."
    release_init_lock
    exit 1
  fi

  # Wait for PGBouncer to cool down
  log "Waiting for PGBouncer to cool down..."
  sleep 10

  # Ensure the database exists
  log "Creating the database '${POSTGRES_DB}'..."

  if ! execute_psql_command "postgres" "CREATE DATABASE \"${POSTGRES_DB}\";"; then
    log "Failed to create database '${POSTGRES_DB}'."
    release_init_lock
    exit 1
  fi

  # Destroy the filestore
  log "Removing filestore for database '${POSTGRES_DB}'..."
  if ! rm -rf "/var/lib/odoo/filestore/${POSTGRES_DB}"; then
    log "Failed to remove filestore for database '${POSTGRES_DB}'."
    release_init_lock
    exit 1
  fi

  # Remove destroy semaphore
  rm -f "${DESTROY_SEMAPHORE}"

  # Remove scaffolded semaphore
  rm -f "${SCAFFOLDED_SEMAPHORE}"

  log "Destroy operations completed."
}

# Step 4.3.3: Initialize the Odoo instance
initialize_odoo() {
  log "Initializing Odoo instance..."

  # Set default supported languages if not set
  local odoo_languages="${ODOO_LANGUAGES:-$DEFAULT_ODOO_LANGUAGES}"

  # Extract unique country codes from ODOO_LANGUAGES
  local langs=()
  IFS=',' read -ra langs <<<"$odoo_languages" # Split ODOO_LANGUAGES by comma

  local country_codes=()
  local lang
  for lang in "${langs[@]}"; do
    # Extract country code after underscore, e.g., en_US -> US
    if [[ "$lang" == *"_"* ]]; then
      local country_code="${lang#*_}"              # Remove everything before underscore
      local country_code_lower="${country_code,,}" # Convert to lowercase
      country_codes+=("$country_code_lower")
    fi
  done

  # Remove duplicate country codes using an associative array
  declare -A seen_country_codes=()
  local unique_country_codes=()
  local code
  for code in "${country_codes[@]}"; do
    if [[ -z "${seen_country_codes[$code]:-}" ]]; then
      unique_country_codes+=("$code")
      seen_country_codes[$code]=1
    fi
  done



  # Get the list of addon paths
  local addon_paths_str
  addon_paths_str="$(get_addons_paths)"
  # Split the addon paths into an array
  IFS=',' read -ra addon_paths <<<"$addon_paths_str"

  # Collect Odoo addons from community and enterprise directories
  local odoo_addons=()
  collect_addons odoo_addons "/opt/odoo/community" "/opt/odoo/enterprise"

  # Ensure 'base' and 'web' modules are always included
  local mandatory_addons=("web" "base")
  local mandatory_addon
  for mandatory_addon in "${mandatory_addons[@]}"; do
    if [[ ! " ${odoo_addons[*]} " =~ " $mandatory_addon " ]]; then
      odoo_addons+=("$mandatory_addon")
      log "Including mandatory addon '$mandatory_addon'."
    fi
  done

  # Initialise Odoo addons first
  local odoo_addon_init_list=""
  if [[ ${#odoo_addons[@]} -gt 0 ]]; then
    # Combine the addons into a comma-separated string
    odoo_addon_init_list="$(
      IFS=','
      echo "${odoo_addons[*]}"
    )"
    log "Odoo addons to initialise: $odoo_addon_init_list"
  else
    log "No Odoo addons found to initialise."
  fi

  # Determine database connection parameters
  local db_host db_port db_user db_password db_sslmode
  if [[ -n "${PGBOUNCER_HOST}" ]]; then
    db_host="${PGBOUNCER_HOST}"
    db_port="${PGBOUNCER_PORT:-5432}"
    db_user="${POSTGRES_USER:-odoo}"
    db_password="${POSTGRES_PASSWORD:-odoo}"
    db_sslmode="${PGBOUNCER_SSL_MODE:-disable}"
  else
    db_host="${POSTGRES_HOST:-postgres}"
    db_port="${POSTGRES_PORT:-5432}"
    db_user="${POSTGRES_USER:-odoo}"
    db_password="${POSTGRES_PASSWORD:-odoo}"
    db_sslmode="${POSTGRES_SSL_MODE:-disable}"
  fi

  # Now, call Odoo with dynamic --init for Odoo addons
  gosu odoo /usr/bin/odoo server \
    --init="$odoo_addon_init_list" \
    --database="${POSTGRES_DB}" \
    --without-demo \
    --unaccent \
    --stop-after-init \
    --db_host="${db_host}" \
    --db_port="${db_port}" \
    --db_user="${db_user}" \
    --db_password="${db_password}" \
    --db_sslmode="${db_sslmode}" \
    --data-dir=/var/lib/odoo \
    --addons-path="$addon_paths_str" \
    --load-language="${odoo_languages}" \
    --no-http \
    --config=/etc/odoo/odoo.conf

  local exit_code="$?"
  if [[ "$exit_code" -ne 0 ]]; then
    log "Odoo initialisation failed with exit code $exit_code."
    perform_destroy
    release_init_lock
    exit 2
  fi

  # After successful Odoo addons initialisation, proceed to extras
  # Collect extras addons from /opt/odoo/extras and /mnt/addons if valid
  local extras_addons=()
  local extras_addon_paths=("/opt/odoo/extras")
  if has_valid_addons_in_mnt; then
    extras_addon_paths+=("/mnt/addons")
  fi
  collect_addons extras_addons "${extras_addon_paths[@]}"

  # Initialise extras addons if any
  if [[ ${#extras_addons[@]} -gt 0 ]]; then
    local extras_addon_init_list
    extras_addon_init_list="$(
      IFS=','
      echo "${extras_addons[*]}"
    )"
    log "Extras addons to initialise: $extras_addon_init_list"

    # Try to initialise extras addons
    gosu odoo /usr/bin/odoo server \
      --init="$extras_addon_init_list" \
      --database="${POSTGRES_DB}" \
      --without-demo \
      --unaccent \
      --stop-after-init \
      --db_host="${db_host}" \
      --db_port="${db_port}" \
      --db_user="${db_user}" \
      --db_password="${db_password}" \
      --db_sslmode="${db_sslmode}" \
      --data-dir=/var/lib/odoo \
      --addons-path="$addon_paths_str" \
      --load-language="${odoo_languages}" \
      --no-http \
      --config=/etc/odoo/odoo.conf

    local extras_exit_code="$?"
    if [[ "$extras_exit_code" -ne 0 ]]; then
      log "Extras initialisation failed with exit code $extras_exit_code."
      perform_destroy
      release_init_lock
      exit 2
    else
      log "Extras addons initialisation completed successfully."
    fi
  else
    log "No extras addons found to initialise."
  fi

  # Create scaffolded semaphore to indicate initialisation is complete
  touch "${SCAFFOLDED_SEMAPHORE}"
  # Update the timestamp file
  if ! update_timestamp_file; then
    log "Failed to update timestamp file."
  fi

  log "Odoo initialisation completed successfully."
}

# Step 4.4: Release the init lock
release_init_lock() {
  if [[ "$INIT_LOCK_HELD" == true ]]; then
    log "Releasing init lock '${INIT_LOCK}'..."
    lock-handler release "${INIT_LOCK}"
    INIT_LOCK_HELD=false # Lock is no longer held
  else
    log "Init lock '${INIT_LOCK}' not held, no need to release."
  fi
}

# Function to upgrade Odoo modules
upgrade_odoo() {
  # Check if ODOO_NO_AUTO_UPGRADE is set and truthy
  if [[ -n "${ODOO_NO_AUTO_UPGRADE:-}" ]]; then
    log "ODOO_NO_AUTO_UPGRADE is set. Skipping module upgrade."
    return 0
  fi

  # Attempt to acquire the upgrade lock
  log "Acquiring upgrade lock '${UPGRADE_LOCK}'..."
  if lock-handler acquire "${UPGRADE_LOCK}"; then
    log "Upgrade lock acquired."
    UPGRADE_LOCK_HELD=true

    if update_needed; then
      log "Starting Odoo module upgrade (sequential)..."

      # Determine database connection parameters
      local db_host db_port db_user db_password db_sslmode
      if [[ -n "${PGBOUNCER_HOST:-}" ]]; then
        db_host="${PGBOUNCER_HOST}"
        db_port="${PGBOUNCER_PORT:-5432}"
        db_user="${POSTGRES_USER:-odoo}"
        db_password="${POSTGRES_PASSWORD:-odoo}"
        db_sslmode="${PGBOUNCER_SSL_MODE:-disable}"
      else
        db_host="${POSTGRES_HOST:-postgres}"
        db_port="${POSTGRES_PORT:-5432}"
        db_user="${POSTGRES_USER:-odoo}"
        db_password="${POSTGRES_PASSWORD:-odoo}"
        db_sslmode="${POSTGRES_SSL_MODE:-disable}"
      fi

      # Get the addons paths
      local addon_paths_str
      addon_paths_str="$(get_addons_paths)"

      # Helper to run module upgrade for a single module
      _run_module_upgrade() {
        local module_name="$1"
        log "Upgrading module '$module_name'..."
        gosu odoo /usr/bin/odoo server \
          --update="${module_name}" \
          --database="${POSTGRES_DB}" \
          --stop-after-init \
          --db_host="${db_host}" \
          --db_port="${db_port}" \
          --db_user="${db_user}" \
          --db_password="${db_password}" \
          --db_sslmode="${db_sslmode}" \
          --data-dir=/var/lib/odoo \
          --addons-path="$addon_paths_str" \
          --config=/etc/odoo/odoo.conf
        return "$?"
      }

      # Build list of modules to upgrade. We rely on the database to provide the precise list.
      # Build list of addons using collect_addons for consistency with initialization
      # ---------------------------------------------------------------------------
      # Assemble addon paths array from get_addons_paths result
      IFS=',' read -ra addon_paths <<<"$addon_paths_str"

      local -a modules_array_tmp=()
      collect_addons modules_array_tmp "${addon_paths[@]}"

      # Ensure mandatory modules are always included
      local mandatory_modules=("web" "base")
      local m
      for m in "${mandatory_modules[@]}"; do
        if [[ ! " ${modules_array_tmp[*]} " =~ " $m " ]]; then
          modules_array_tmp+=("$m")
        fi
      done

      if (( ${#modules_array_tmp[@]} == 0 )); then
        log "No addons detected via collect_addons. Nothing to upgrade."
        release_upgrade_lock
        return 0
      fi

      local -a modules_array=("${modules_array_tmp[@]}")

      #
      # Upgrade algorithm requirements (specification):
      #   1. Build full list of modules.
      #   2. Attempt to upgrade each module once, logging failures but
      #      continuing the loop.
      #   3. Retry the set of failed modules two more times (total 3 attempts).
      #   4. After the third attempt, if *all* modules remain in the failed
      #      list, consider the upgrade a fatal error (non-zero exit status).
      #      Otherwise, finish successfully while logging a warning that
      #      includes the list of modules that could not be upgraded.

      local -a failed_modules=("${modules_array[@]}")  # start by assuming all will fail
      local -a attempted_failures=()                   # temp holder per round
      local max_attempts=3
      local attempt=1

      while (( attempt <= max_attempts )) && (( ${#failed_modules[@]} > 0 )); do
        log "Starting module upgrade attempt ${attempt}/${max_attempts}. Modules to process: ${failed_modules[*]}"

        attempted_failures=()  # reset list for this iteration

        for module in "${failed_modules[@]}"; do
          # Special-case support for the magic keyword "all" used by some
          # deployments. If present we run a single global update and break –
          # we still honour retry semantics for the keyword itself.
          if [[ "${module}" == "all" ]]; then
            if _run_module_upgrade "all"; then
              log "Global module upgrade ('all') succeeded on attempt ${attempt}."
            else
              log "Global module upgrade ('all') failed on attempt ${attempt}."
              attempted_failures+=("all")
            fi
            # Nothing else to do once the special keyword has been handled.
            break
          fi

          if _run_module_upgrade "${module}"; then
            log "Module '${module}' upgraded successfully (attempt ${attempt})."
          else
            log "Module '${module}' failed to upgrade (attempt ${attempt})."
            attempted_failures+=("${module}")
          fi
        done

        # Prepare list for next iteration (only modules that are still failing)
        failed_modules=("${attempted_failures[@]}")

        if (( ${#failed_modules[@]} > 0 )) && (( attempt < max_attempts )); then
          log "Retrying failed modules after short delay: ${failed_modules[*]}"
          sleep 5
        fi

        ((attempt++))
      done

      # Evaluate final outcome
      if (( ${#failed_modules[@]} == 0 )); then
        log "All modules upgraded successfully."
        # Update timestamp file only when upgrade completed fully
        if ! update_timestamp_file; then
          log "Failed to update timestamp file."
        fi
      else
        # Determine if *every* module failed (fatal) or only a subset (warning)
        local total_modules=${#modules_array[@]}
        if (( ${#failed_modules[@]} == total_modules )); then
          log "ERROR: Every module failed to upgrade after ${max_attempts} attempts. Failing startup."
          release_upgrade_lock
          return 1
        else
          log "WARNING: The following modules failed to upgrade after ${max_attempts} attempts and will be skipped: ${failed_modules[*]}"
          # Considered overall success – update the timestamp to prevent
          # re-running a lengthy upgrade loop on every start-up.
          if ! update_timestamp_file; then
            log "Failed to update timestamp file."
          fi
          # Successful (non-fatal) exit continues.
        fi
      fi

    else
      log "No update needed. Skipping module upgrade."
    fi
    # Release the lock
    release_upgrade_lock

  else
    # Failed to acquire lock, wait for module upgrade to complete
    log "Upgrade lock not acquired. Waiting for module upgrade to complete..."
    if lock-handler wait "${UPGRADE_LOCK}"; then
      log "Module upgrade completed."
      return 0
    else
      log "Failed to wait for module upgrade to complete."
      exit 1
    fi
  fi
}

# Function to release the upgrade lock
release_upgrade_lock() {
  if [[ "$UPGRADE_LOCK_HELD" == true ]]; then
    log "Releasing upgrade lock '${UPGRADE_LOCK}'..."
    lock-handler release "${UPGRADE_LOCK}"
    UPGRADE_LOCK_HELD=false
  else
    log "Upgrade lock '${UPGRADE_LOCK}' not held, no need to release."
  fi
}

# Step 5: Check that the "scaffolded" semaphore exists
check_scaffolded_semaphore() {
  if [[ ! -f "${SCAFFOLDED_SEMAPHORE}" ]]; then
    log "Scaffolded semaphore not found. Exiting."
    exit 3
  fi
}

# Step 6: Set the master database password
set_admin_password() {
  log "Setting master database password..."
  odoo-config --set-admin-password || {
    log "Failed to set master database password."
    exit 1
  }
}

# Step 6.5: Set the database configuration
set_db_config() {
  log "Setting database configuration..."
  local db_host db_port db_user db_password db_sslmode

  if [[ -n "${PGBOUNCER_HOST}" ]]; then
    db_host="${PGBOUNCER_HOST}"
    db_port="${PGBOUNCER_PORT:-5432}"
    db_user="${POSTGRES_USER:-odoo}"
    db_password="${POSTGRES_PASSWORD:-odoo}"
    db_sslmode="${PGBOUNCER_SSL_MODE:-disable}"
  else
    db_host="${POSTGRES_HOST:-postgres}"
    db_port="${POSTGRES_PORT:-5432}"
    db_user="${POSTGRES_USER:-odoo}"
    db_password="${POSTGRES_PASSWORD:-odoo}"
    db_sslmode="${POSTGRES_SSL_MODE:-disable}"
  fi

  odoo-config set options db_host "${db_host}"
  odoo-config set options db_port "${db_port}"
  odoo-config set options db_user "${db_user}"
  odoo-config set options db_password "${db_password}"
  odoo-config set options db_sslmode "${db_sslmode}"
}

# Step 7: Set the Redis configuration
set_redis_config() {
  log "Setting Redis configuration..."
  odoo-config --set-redis-config || {
    log "Failed to set Redis configuration."
    exit 1
  }
}

# Step 7.5: Set the addons path configuration
set_addons_path_config() {
  log "Setting addons path configuration..."
  local addon_paths_str
  addon_paths_str="$(get_addons_paths)"
  odoo-config set options addons_path "${addon_paths_str}" || {
    log "Failed to set addons_path in configuration."
    exit 1
  }
  log "Addons path set to: ${addon_paths_str}"
}

# Step 8: Calculate the number of workers
calculate_workers() {
  local cpu_count
  cpu_count=$(nproc)
  WORKERS=$((cpu_count * 2 - 1))
  log "Calculated workers: ${WORKERS}"
}

# Step 9: Set the listen interface based on Odoo version
set_listen_interface() {
  local odoo_major_version
  odoo_major_version=$(gosu odoo /usr/bin/odoo --version | awk '{print $3}' | cut -d '.' -f1)
  if [[ "${odoo_major_version}" -ge 17 ]]; then
    LISTEN_INTERFACE="::"
  else
    LISTEN_INTERFACE="0.0.0.0"
  fi
  log "Set listen interface to '${LISTEN_INTERFACE}'"
}

# Function to check if an option is present in the provided arguments
# This function checks if the given option is present among the arguments.
# Globals:
#   None
# Arguments:
#   $1: The option to check for (e.g., --workers)
#   ...: The list of arguments to check
# Returns:
#   0 (success) if the option is found, 1 (failure) otherwise
option_in_args() {
  local option="$1"
  shift
  for arg in "$@"; do
    if [[ "$arg" == "$option" ]] || [[ "$arg" == "$option="* ]]; then
      return 0
    fi
  done
  return 1
}

# Step 10: Start Odoo via gosu as the odoo user
start_odoo() {
  log "Starting Odoo..."

  local odoo_cmd
  odoo_cmd=(gosu odoo /usr/bin/odoo server)

  local db_host db_port db_user db_password db_sslmode

  if [[ -n "${PGBOUNCER_HOST}" ]]; then
    db_host="${PGBOUNCER_HOST}"
    db_port="${PGBOUNCER_PORT:-5432}"
    db_user="${POSTGRES_USER:-odoo}"
    db_password="${POSTGRES_PASSWORD:-odoo}"
    db_sslmode="${PGBOUNCER_SSL_MODE:-disable}"
  else
    db_host="${POSTGRES_HOST:-postgres}"
    db_port="${POSTGRES_PORT:-5432}"
    db_user="${POSTGRES_USER:-odoo}"
    db_password="${POSTGRES_PASSWORD:-odoo}"
    db_sslmode="${POSTGRES_SSL_MODE:-disable}"
  fi

  # Include user-provided arguments
  odoo_cmd+=("$@")

  # Add default options if not already provided

  # --database option
  if ! option_in_args "--database" "$@"; then
    odoo_cmd+=(--database="${POSTGRES_DB}")
  fi

  # --unaccent option
  if ! option_in_args "--unaccent" "$@"; then
    odoo_cmd+=(--unaccent)
  fi

  # --workers option
  if ! option_in_args "--workers" "$@"; then
    odoo_cmd+=(--workers="${WORKERS}")
  fi

  # --http-interface option
  if ! option_in_args "--http-interface" "$@"; then
    odoo_cmd+=(--http-interface="${LISTEN_INTERFACE}")
  fi

  # --config option
  if ! option_in_args "--config" "$@"; then
    odoo_cmd+=(--config=/etc/odoo/odoo.conf)
  fi

  # Set database connection parameters
  if ! option_in_args "--db_host" "$@"; then
    odoo_cmd+=(--db_host="${db_host}")
  fi
  if ! option_in_args "--db_port" "$@"; then
    odoo_cmd+=(--db_port="${db_port}")
  fi
  if ! option_in_args "--db_user" "$@"; then
    odoo_cmd+=(--db_user="${db_user}")
  fi
  if ! option_in_args "--db_password" "$@"; then
    odoo_cmd+=(--db_password="${db_password}")
  fi
  if ! option_in_args "--db_sslmode" "$@"; then
    odoo_cmd+=(--db_sslmode="${db_sslmode}")
  fi

  # --addons-path option
  if ! option_in_args "--addons-path" "$@"; then
    local addon_paths_str
    addon_paths_str="$(get_addons_paths)"
    odoo_cmd+=(--addons-path="${addon_paths_str}")
    log "Using addons path: ${addon_paths_str}"
  fi

  # Execute the command
  exec "${odoo_cmd[@]}"
}

main() {
  # Modify UID/GID if required
  modify_uid_gid

  # Handle custom commands
  if [[ $# -gt 0 ]]; then
    case "$1" in
    odoo | odoo.py | --*)
      # Proceed with Odoo initialization
      ;;
    *)
      # Execute custom command
      handle_custom_command "$@"
      ;;
    esac
  fi

  # Ensure correct permissions
  ensure_permissions

  wait_for_redis
  wait_for_postgres

  if acquire_init_lock; then
    handle_initialization
  else
    log "Waiting for initialization to complete..."
    wait_for_init_lock || {
      log "Initialization did not complete successfully."
      exit 1
    }
  fi

  # Ensure odoo.conf exists before upgrade.
  # Other helpers like set_admin_password will create the file later,
  # but upgrade_odoo runs first and requires it to exist.
  odoo-config --defaults || {
    log "Failed to ensure Odoo configuration defaults."
    exit 1
  }

  check_scaffolded_semaphore
  upgrade_odoo
  set_admin_password
  set_redis_config
  set_addons_path_config
  set_db_config
  calculate_workers
  set_listen_interface
  start_odoo "$@"
}

# Start the main function with all passed arguments
main "$@"
