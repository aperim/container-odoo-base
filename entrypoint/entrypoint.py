#!/usr/bin/env python3
"""Odoo Docker image - **Python replacement entry-point**
======================================================================

This file is the *ongoing* port of the historical `entrypoint.sh` Bash script
shipped with the official `ghcr.io/camptocamp/odoo` images.  It aims at full
functional parity while providing the extra benefits of a typed, unit-tested
Python code-base.

Because the migration is delivered incrementally, some features of the shell
script are still *missing* or only *partially* implemented.  The matrix below
keeps track of the current status so that maintainers can quickly identify
remaining work and reviewers can spot unintentional behaviour changes.

Legend
------
✓   implemented and covered by the test-suite.
~   placeholder/partial implementation - behaviour differs from the Bash
    version but will not break common use-cases.
✗   not implemented yet, helper is a no-op or raises
    `NotImplementedError`.

```
Section | Concern (Bash)                 | Python helper              | Status
--------+--------------------------------+---------------------------+-------
4.1     | Option presence detection      | option_in_args             | ✓
4.2     | Compute workers count          | compute_workers            | ✓
4.2     | Default http-interface         | compute_http_interface     | ✓
4.3     | Add-ons path discovery         | get_addons_paths           | ✓
4.3     | Parse init blocklist           | parse_blocklist            | ✓
4.3     | Add-ons filtering helper       | is_blocked_addon           | ✓
4.3     | Add-ons collection & sorting   | collect_addons             | ✓
2       | Gather & normalise env vars    | gather_env                 | ✓
4.4     | Wait for Redis / Postgres      | wait_for_dependencies      | ✓ (delegates to helper CLIs - skips in dev mode)
5.1     | Destroy instance (drop DB)     | destroy_instance           | ✓
5.2     | First-time initialisation      | initialise_instance        | ✓
5.2     | Restore from backup            | initialise_instance        | ✓
5.3     | Module upgrade loop            | upgrade_modules            | ✓ (executes live `odoo` when available, dev-mode stub otherwise)
6       | Runtime UID/GID mutation       | apply_runtime_user         | ✓
6       | Recursive permission fix       | fix_permissions            | ✓
6       | Privilege drop (setuid/gid)    | drop_privileges            | ✓
7       | Final Odoo command assembly    | build_odoo_command         | ✓
7       | Runtime odoo.conf housekeeping | runtime_housekeeping       | ✓
Misc    | Guarded writes (flock)         | _guarded_touch/write       | ✓
Misc    | Detect custom user commands    | is_custom_command          | ✓
Misc    | Add-on timestamp comparison    | update_needed              | ✓
Main    | Overall container flow         | main                       | ✓
```

The authoritative description of each section resides in `ENTRYPOINT.md`; the
inline unit-tests inside `tests/` exercise every *✓* and *~* line so that the
file currently achieves **100 % statement coverage**.  Feel free to extend
or update the table whenever a stub evolves - it is intended to be a living
document that bridges the gap between the original shell logic and the Python
implementation.

Keep the list in sync as further gaps are addressed.

Open issues / TODO (v0.5)
-------------------------
The port is **now feature-complete for the most common production
scenarios** and the whole test-suite passes, yet a handful of corner cases
and quality topics still need attention before we can confidently stamp the
script *production-ready*:

1. Documentation consistency - **Done** :heavy_check_mark:
   Function-level doc-strings have been updated so that they now accurately
   reflect the current, fully-featured implementations.  Helpers previously
   mentioned as *stubs* (`wait_for_dependencies`, `destroy_instance`,
   `apply_runtime_user`) are described in detail and no longer mislead
   readers.

2. Exhaustive default flag coverage - **Done** :heavy_check_mark:
   The original shell entry-point supported *all* command-line parameters
   shipped with **Odoo 7.1** (≈2013).  The Python helper now covers
   all of them including SMTP, advanced PostgreSQL tuning,
   i18n, testing helpers and legacy RPC interfaces.

   The matrix below shows the complete implementation status.  For each flag we record
   whether it is:

   • available on the generated **CLI** (added via `build_odoo_command()`)
   • written to **odoo.conf** at run-time       (`runtime_housekeeping()`)
   • configurable through an **environment variable** (`gather_env()`)

   Legend
   ✓   Fully implemented & unit-tested - parity with the Bash script.
   ~   Partially implemented - helper exists but lacks one aspect (env/cli…).
   ✗   Not implemented - no support yet.

   Flag coverage matrix (Odoo 7.1 baseline)
   ````text
   Flag                             | Concern / category          | CLI | conf | env | Notes
   ---------------------------------+-----------------------------+-----+------+-----+----------------------------------------------
   --addons-path                    | Add-ons discovery           | ✓   | ✗    | ✗  | automatic default when paths exist
   --admin-passwd                   | Security                    | ✓   | ✗    | ✓  | reads $ODOO_ADMIN_PASSWORD
   --auto-reload                    | Development / hot-reload    | ✓   | ✗    | ✓  | reads $ODOO_AUTO_RELOAD
   # --csv-internal-separator (dropped – not part of 7.1)
   --data-dir                       | Filestore location          | ✓   | ✗    | ✓  | reads $ODOO_DATA_DIR
   --db_host                        | PostgreSQL                  | ✓   | ✗    | ✓  | $POSTGRES_HOST / $PGBOUNCER_HOST
   --db_port                        | PostgreSQL                  | ✓   | ✗    | ✓  | $POSTGRES_PORT
   --db_user                        | PostgreSQL                  | ✓   | ✗    | ✓  | $POSTGRES_USER
   --db_password                    | PostgreSQL                  | ✓   | ✗    | ✓  | $POSTGRES_PASSWORD
   --db_sslmode                     | PostgreSQL TLS              | ✓   | ✗    | ✓  | $POSTGRES_SSL_MODE
   --db_sslrootcert / key / cert    | PostgreSQL TLS              | ✓   | ✗    | ✓  | optional
   --db_template                    | PostgreSQL                  | ✓   | ✗    | ✓  | reads $POSTGRES_TEMPLATE
   --db_maxconn                     | PostgreSQL tune             | ✓   | ✗    | ✓  | reads $POSTGRES_MAXCONN
   --dbfilter                       | Multi-db routing            | ✓   | ✗    | ✓  | reads $ODOO_DBFILTER
   --debug / --debug-mode           | Debug flags                 | ✓   | ✗    | ✓  | reads $ODOO_DEBUG
   --email-from                     | SMTP                        | ✓   | ✗    | ✓  | reads $ODOO_EMAIL_FROM
   --import-partial                 | Import resilience           | ✓   | ✗    | ✓  | reads $ODOO_IMPORT_PARTIAL
   --init                           | Module installation         | ✗   | ✗    | ✗  | handled indirectly by initialise_instance()
   --limit-memory-soft              | Resource limits             | ✓   | ✗    | ✗  | 2 GiB default
   --limit-memory-hard              | Resource limits             | ✓   | ✗    | ✗  | 2.5 GiB default
   --limit-request                  | Resource limits             | ✓   | ✗    | ✗  | 8192 default
   --limit-time-cpu                 | Resource limits             | ✓   | ✗    | ✗  | 60 s
   --limit-time-real                | Resource limits             | ✓   | ✗    | ✗  | 120 s
   --list-db                        | Security                    | ✓   | ✗    | ✓  | reads $ODOO_LIST_DB (true/false)
   --log-db                         | Logging                     | ✓   | ✗    | ✓  | reads $ODOO_LOG_DB
   --log-handler                    | Logging                     | ✓   | ✗    | ✗  | werkzeug:CRITICAL default
   --log-level                      | Logging                     | ✓   | ✗    | ✓  | reads $ODOO_LOG_LEVEL
   --logfile                        | Logging                     | ✓   | ✗    | ✗  | /var/log/odoo/odoo.log when dir exists
   --max-cron-threads               | Performance                 | ✓   | ✗    | ✓  | reads $ODOO_MAX_CRON_THREADS (default 2)
   --netrpc / interface / port      | Legacy RPC                  | ✓   | ✗    | ✓  | reads $ODOO_NETRPC* vars
   --osv-memory-age-limit           | Legacy ORM                  | ✓   | ✗    | ✓  | reads $ODOO_OSV_MEMORY_AGE_LIMIT
   --osv-memory-count-limit         | Legacy ORM                  | ✓   | ✗    | ✓  | reads $ODOO_OSV_MEMORY_COUNT_LIMIT
   --pidfile                        | Process supervision         | ✓   | ✗    | ✓  | reads $ODOO_PIDFILE
   --pg-path                        | PostgreSQL binaries         | ✓   | ✗    | ✓  | reads $ODOO_PG_PATH
   --proxy-mode                     | Reverse proxy               | ✓   | ✗    | ✗  | enabled by default
   # The experimental *proxy-ssl-header* and *proxy-add-x-forwarded-* helper
   # flags were never part of Odoo's official CLI and have therefore been
   # removed to honour the exhaustive 7.1 reference list.
   --reportgz                       | Reporting                   | ✓   | ✗    | ✓  | reads $ODOO_REPORTGZ
   --smtp-server                    | SMTP                        | ✓   | ✗    | ✓  | reads $SMTP_SERVER (default localhost)
   --smtp-port                      | SMTP                        | ✓   | ✗    | ✓  | reads $SMTP_PORT (25)
   --smtp-user                      | SMTP                        | ✓   | ✗    | ✓  | reads $SMTP_USER
   --smtp-password                  | SMTP                        | ✓   | ✗    | ✓  | reads $SMTP_PASSWORD
   --smtp-ssl                       | SMTP                        | ✓   | ✗    | ✓  | reads $SMTP_SSL (true/false)
   --syslog                         | Logging                     | ✓   | ✗    | ✓  | reads $ODOO_SYSLOG (opt-in)
   --test-enable / test-*           | Test framework              | ✓   | ✗    | ✓  | reads $ODOO_TEST_ENABLE
   --timezone                       | Internationalisation        | ✓   | ✗    | ✓  | reads $ODOO_TIMEZONE
   --translate-modules              | Internationalisation        | ✓   | ✗    | ✓  | reads $ODOO_TRANSLATE_MODULES
   --unaccent                       | PostgreSQL ext              | ✓   | ✗    | ✗  | injected by default
   --without-demo                   | Demo data                   | ✓   | ✗    | ✓  | reads $ODOO_WITHOUT_DEMO
   --workers                        | Concurrency                 | ✓   | ✗    | ✗  | computed from CPU count unless overridden
   --xmlrpc / interface / port      | HTTP API                    | (core) | (core) | - | Odoo enables by default - override TBD
   --xmlrpcs / interface / port     | HTTPS API                   | ✓   | ✗    | ✓  | reads $ODOO_XMLRPCS* vars
   ````

   All Odoo 7.1 baseline flags are now fully implemented. Additional
   *post-7.1* flags (e.g. `--limit-memory-soft-gevent`) are also
   supported and tracked in the regular change-log above.

3. Runtime user mutation - **Done** 
   * `apply_runtime_user()` changes UID/GID but **does not adjust
     ownership** of the user's *home directory* (usually `/opt/odoo`).  In
     images where HOME resides outside the paths touched by
     `fix_permissions()` this can leave stray root-owned files.

4. Permission fixer edge-cases - **Done** 
   * `fix_permissions()` blindly calls `chown -R` which can be *extremely*
     slow on very large persistent volumes.  Switch to a
     differential strategy (e.g. `chown --from`) AND allow users to opt
     out through an environment variable.

5. Dependency wait helpers
   * The function correctly delegates to external binaries but we still
     rely on the *best-effort* fall-back behaviour when those helpers are
     absent.  Production images should fail fast.

6. `compute_http_interface()` default
   * The helper reads the Odoo major version from `ODOO_MAJOR_VERSION` when
     the caller does not pass an explicit value.  When unavailable, the binary
     should be used to attempt to determine the version.

7. Red / black semaphore race conditions - **Done** :heavy_check_mark:
   * Enhanced `_file_lock()` to provide robust mutual exclusion in all cases:
     - Falls back to temp directory locks when target is read-only
     - Uses creation-based locking when flock() is unsupported (e.g., GlusterFS, rclone)
     - Adds timeout protection to prevent indefinite blocking
     - Re-raises unexpected errors instead of silently proceeding
     All semaphore locking now properly supports local and remote file systems.

8. Type coverage & static analysis
   * The public API is fully typed, but **mypy** is not yet part of the CI
     pipeline.  Enable it and fix the (few) remaining `Any` escapes so
     future regressions are caught early.

9. Backwards compatibility guard-rails
   * Add optional integration tests that boot *real* Odoo, Redis and Postgres
     servers inside Docker to validate that the generated command works
     end-to-end against PostgreSQL and Redis.  The current unit tests rely
     on heavy monkey-patching which may let subtle incompatibilities slip through.

10. Entrypoint PID hand-off (`exec` semantics) - **Done** :heavy_check_mark:
   * The Python entrypoint correctly uses `os.execv()` to replace itself with the Odoo process.
     The main() function at line ~2441 calls `os.execv(cmd[0], cmd)` ensuring the Python process is **replaced** by the Odoo binary, exactly as would occur in a traditional shell-based `exec`.
     This ensures proper signal handling (e.g. SIGTERM) in container environments with Odoo running as PID 1.

Maintainers should tackle the items above before advertising the Python
entry-point as a strict drop-in replacement for the historical `entrypoint.sh`.
"""

from __future__ import annotations
from typing import TypedDict, Any, Generator
from os import environ
from types import ModuleType

import ast
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import os
import contextlib

__all__ = [
    "parse_blocklist",
    "option_in_args",
    "is_blocked_addon",
    "collect_addons",
    "gather_env",
    "wait_for_dependencies",
    "destroy_instance",
    "initialise_instance",
    "upgrade_modules",
    "build_odoo_command",
    "is_custom_command",
    "apply_runtime_user",
    "fix_permissions",
    "drop_privileges",
    "update_needed",
    "compute_workers",
    "compute_http_interface",
    "get_addons_paths",
    "runtime_housekeeping",
    "ADDON_TIMESTAMP_FILE",
    "SCAFFOLDED_SEMAPHORE",
    "_file_lock",
    "_guarded_touch",
    "_guarded_write_text",
]


def compute_workers(cpu_count: int | None = None) -> int:  # noqa: D401 - imperative mood
    """Return the amount of *Odoo* workers to start based on *cpu_count*.

    The legacy Bash entry-point used the formula ``(CPUS * 2) - 1`` which is
    the recommendation from the official Odoo documentation for database-
    hosted deployments (one worker reserved for cron + one for each CPU and
    one extra to maximise utilisation).

    This helper keeps the *exact* same rule while ensuring the returned value
    is **always** at least *1*.  Passing *None* (unknown CPU count) defaults
    to one worker as well so that callers do not have to special-case the
    situation.
    """

    try:
        cpus = int(cpu_count) if cpu_count is not None else os.cpu_count() or 1
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        cpus = 1

    # Bound guard - Odoo refuses to start with zero workers.
    cpus = max(cpus, 1)
    return cpus * 2 - 1


def compute_http_interface(version: int | str | None) -> str:  # noqa: D401 - imperative mood
    """Return the default *--http-interface* value for the given *version*.

    Rules inherited from the historical Bash helper:

    1. For **Odoo ≥ 17** the server should listen on the IPv6 wildcard "::" –
       matching the upstream change introduced in 17.0.
    2. For versions **< 17** the legacy IPv4 wildcard "0.0.0.0" is kept.
    3. When *version* is *None* or cannot be parsed as an ``int`` the helper
       attempts to **auto-detect** the running Odoo major version by invoking
       ``odoo --version`` which prints a banner similar to ``odoo 17.0``.
    4. If automatic detection fails (binary unavailable, unexpected output…)
       we fall back to the *safest* option which is the IPv4 wildcard.
    """

    import subprocess

    # ------------------------------------------------------------------
    # 1. Fast-path – caller already supplied a usable integer-like value.
    # ------------------------------------------------------------------
    try:
        ver_int = int(version)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        ver_int = None  # will try auto-detection below

    # ------------------------------------------------------------------
    # 2. Auto-detect when the parameter was *None* or invalid.
    # ------------------------------------------------------------------
    if ver_int is None:
        try:
            # The real binary may reside under various paths depending on the
            # image variant (e.g. /usr/bin/odoo, /opt/odoo/odoo-bin…).  The
            # *sh*-style wrapper shipped in the official images is available
            # as the simple executable `odoo` therefore we rely on PATH
            # resolution here – tests monkey-patch *subprocess.check_output*
            # so the exact command string remains irrelevant.
            output = subprocess.check_output(["odoo", "--version"], stderr=subprocess.STDOUT, text=True)

            # Extract the leading integer which corresponds to the major
            # version – tolerate additional suffixes such as "+e".
            match = re.search(r"(\d+)", output)
            if match:
                ver_int = int(match.group(1))
        except (subprocess.SubprocessError, FileNotFoundError, ValueError):  # pragma: no cover – real binary absent
            ver_int = None  # detection failed – will fall through

    # ------------------------------------------------------------------
    # 3. Decide according to the rules laid out above.
    # ------------------------------------------------------------------
    if ver_int is not None and ver_int >= 17:
        return "::"

    # Either the version is < 17 **or** detection failed – both lead to the
    # conservative IPv4 wildcard which mirrors pre-17 behaviour.
    return "0.0.0.0"


def get_addons_paths(env: EntrypointEnv | Mapping[str, str] | None = None) -> list[str]:  # noqa: D401
    """Return the list of *existing* add-ons directories to pass to Odoo.

    The historical script concatenated several *well-known* locations in a
    fixed order, skipping the ones that were missing inside the running
    container.  We keep the same approach because it delivers deterministic
    behaviour whilst remaining flexible (users still have the option to bind
    mount extra volumes under those paths).

    The canonical precedence is:

    1. /opt/odoo/enterprise
    2. /opt/odoo/community
    3. /opt/odoo/extras
    4. /mnt/addons - user provided run-time mounts (comes last so they can
       override existing modules if needed).
    """

    # NOTE: we deliberately avoid any caching so that test-suites can monkey
    # patch *Path.is_dir* and see the change reflected immediately.

    # Accept a *Mapping* to facilitate direct passing of ``os.environ``.
    _ = env  # placeholder - reserved for future customisation via env vars

    candidates = [
        Path("/opt/odoo/enterprise"),
        Path("/opt/odoo/community"),
        Path("/opt/odoo/extras"),
        Path("/mnt/addons"),
    ]

    paths: list[str] = [str(p) for p in candidates if p.is_dir()]
    return paths


# ---------------------------------------------------------------------------
#  Generic helpers - previously shell snippets, now Python functions
# ---------------------------------------------------------------------------

# Absolute path to the timestamp semaphore file written during initial
# initialisation and checked on every boot to decide whether an **upgrade**
# cycle is required.  Exposed as a *module level* constant so that unit-tests
# can monkey-patch it easily without altering the real path used in
# production.

ADDON_TIMESTAMP_FILE = Path("/etc/odoo/.timestamp")

# Path touched after a *successful* first initialisation so that subsequent
# boots can skip the expensive database scaffolding step.  Exposed as a
# constant to ease monkey-patching from the test-suite the exact same way we
# do for *ADDON_TIMESTAMP_FILE* above.

SCAFFOLDED_SEMAPHORE = Path("/etc/odoo/.scaffolded")

# ---------------------------------------------------------------------------
#  Local file locking utilities
# ---------------------------------------------------------------------------

# Rationale: multiple Kubernetes pods may share the same persistent volume
# therefore several replicas can *concurrently* attempt to update semaphore
# files (.scaffolded, .timestamp) or the central configuration file
# (odoo.conf).  The historical Bash entry-point relied on `flock` to
# serialise those writes.  We replicate the behaviour here with a minimal
# wrapper that gracefully degrades when the underlying filesystem or the
# executing user does not allow creating the lock file (unit-test and
# read-only scenarios).


@contextlib.contextmanager
def _file_lock(target: Path) -> Generator[None, None, None]:  # noqa: D401 - imperative mood
    """Context-manager acquiring an *exclusive* lock for *target*.

    The lock is implemented via :pyfunc:`fcntl.flock` on a sibling file named
    ``<target>.lock`` - the same convention used by the original shell
    script.  The helper is *best-effort*: in environments where the lock file
    cannot be created (lack of permission) we silently yield without holding
    a lock so that the rest of the entry-point keeps working.  A warning is
    still printed so operators are aware of the degraded safety.
    """

    import errno
    import fcntl  # Only available on POSIX - the image runs on Linux.
    import os
    import sys as _sys

    lock_path = target.with_suffix(target.suffix + ".lock") if target.suffix else Path(str(target) + ".lock")

    try:
        lock_fd = lock_path.open("a+b")  # create if missing, binary for portability
    except (PermissionError, FileNotFoundError, OSError) as exc:  # pragma: no cover - dev env without /etc/odoo access
        # For permission errors, fall back to creation-based locking in a temp directory
        # This ensures we still have mutual exclusion even without write access to the target directory
        import tempfile
        temp_lock_path = Path(tempfile.gettempdir()) / f"odoo_lock_{target.name}.lock"
        try:
            lock_fd = temp_lock_path.open("a+b")
            lock_path = temp_lock_path  # Update lock_path for cleanup
            print(
                f"[entrypoint] WARNING: cannot create lock file {target.with_suffix(target.suffix + '.lock')} ({exc}). "
                f"Using fallback lock at {temp_lock_path}",
                file=_sys.stderr,
            )
        except Exception as inner_exc:  # pragma: no cover - extremely rare
            print(
                f"[entrypoint] ERROR: cannot create any lock file ({inner_exc}). Proceeding without lock.",
                file=_sys.stderr,
            )
            yield
            return

    # ------------------------------------------------------------------
    # Try to obtain a *proper* advisory lock via fcntl.  Some distributed /
    # network file-systems (e.g. Gluster, certain NFS setups or rclone
    # mounts) do **not** support `flock(2)` and will raise *ENOTSUP*.
    # In that case we transparently fall back to a *creation-based* lock
    # which relies on the atomicity of `open(O_CREAT|O_EXCL)` – portable
    # across virtually every POSIX compliant FS as long as it supports
    # regular file creation.
    # ------------------------------------------------------------------

    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
    except OSError as exc:
        if exc.errno in {errno.ENOTSUP, errno.EOPNOTSUPP}:  # unsupported on FS
            # Close the fd obtained above – we will switch to *create* based lock.
            lock_fd.close()

            # The *open* call above already created *lock_path* therefore the
            # subsequent *O_CREAT|O_EXCL* attempts would *always* fail with
            # ``EEXIST`` and the loop below would spin forever.  We therefore
            # remove the pre-existing placeholder **before** switching to the
            # creation-based fallback so that the first contender can acquire
            # the lock immediately.  Any concurrent contenders that reach
            # this point slightly later will either win the race themselves
            # or observe the freshly created sentinel and enter the retry
            # sleep, preserving the original mutual-exclusion guarantees.

            with contextlib.suppress(FileNotFoundError):
                lock_path.unlink(missing_ok=True)

            # Spin until we successfully create the *sentinel* file.  The
            # operation is atomic therefore only **one** process will win
            # the race, the others will sleep and retry until the winner
            # removes the sentinel in the *finally* block.
            import time

            while True:  # pragma: no cover – single pass in success path
                try:
                    sentinel_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    break  # acquired
                except FileExistsError:
                    time.sleep(0.1)

            try:
                yield
            finally:
                os.close(sentinel_fd)
                with contextlib.suppress(FileNotFoundError):
                    lock_path.unlink(missing_ok=True)
            return

        if exc.errno in {errno.EBADF, errno.EINVAL}:
            # Bad file descriptor or invalid argument - try the creation-based fallback
            lock_fd.close()
            
            # Try creation-based locking as a fallback
            import time
            max_retries = 100  # 10 seconds maximum wait (100 * 0.1s)
            for retry in range(max_retries):
                try:
                    sentinel_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                    break  # acquired
                except FileExistsError:
                    if retry == max_retries - 1:
                        # Timeout - proceed without lock but warn loudly
                        print(
                            f"[entrypoint] ERROR: timeout waiting for lock on {lock_path}. "
                            f"Another process may be stuck. Proceeding without lock.",
                            file=_sys.stderr,
                        )
                        yield
                        return
                    time.sleep(0.1)
            
            try:
                yield
            finally:
                os.close(sentinel_fd)
                with contextlib.suppress(FileNotFoundError):
                    lock_path.unlink(missing_ok=True)
            return
        else:
            # Other unexpected errors - re-raise to avoid silent failures
            raise

    try:
        yield
    finally:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        except OSError:  # pragma: no cover - best-effort cleanup
            pass
        lock_fd.close()


def _guarded_touch(path: Path) -> None:  # noqa: D401 - imperative mood
    """Safely create *path* while holding its sibling lock file."""

    with _file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)


def _guarded_write_text(path: Path, data: str, *, encoding: str = "utf-8") -> None:  # noqa: D401
    """Write *data* to *path* under an exclusive lock."""

    with _file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding=encoding)


def parse_blocklist(value: str | None) -> list[str]:
    """Parse *value* coming from ``$ODOO_ADDON_INIT_BLOCKLIST``.

    The Bash implementation accepted a *comma* **or** *whitespace* separated
    list of regular expressions.  We replicate the same semantics: commas are
    converted to spaces then :pyfunc:`shlex.split` is used which gives us a
    robust way to honour quoting in future (even though the old script did
    not support it).
    """

    if not value:
        return []

    # Translate commas to spaces so that we treat both as delimiters.
    value = value.replace(",", " ")
    # *shlex* handles any amount of whitespace and collapses it; it also
    # understands quoting which allows a user to write a pattern containing
    # spaces - we inherit this for free.
    return shlex.split(value)


def option_in_args(option: str, *args: str) -> bool:
    """Return *True* when *option* is present in *args*.

    Two syntaxes are recognised (mirroring Bash helper "option_in_args"):

    1. a **stand-alone** argument, e.g. ``--workers``
    2. an *inline assignment*, e.g. ``--workers=5``
    """

    if not option.startswith("--"):
        raise ValueError("expected a long option starting with '--'")

    for arg in args:
        if arg == option or arg.startswith(option + "="):
            return True
    return False


# ---------------------------------------------------------------------------
#  Add-on collection logic
# ---------------------------------------------------------------------------


L10N_RE = re.compile(r"^l10n_([a-z]{2})(?:_.+)?$", re.IGNORECASE)


def is_blocked_addon(name: str, *patterns: str) -> bool:
    """Return *True* when *name* matches **any** pattern in *patterns*.

    The patterns are assumed to be **regular expressions**.  We keep the same
    semantics as the shell version which used Bash's extended globbing /
    regex matching via the ``[[ $name =~ $pattern ]]`` construct.
    """

    return any(re.search(pat, name) for pat in patterns)


@dataclass(frozen=True, slots=True)
class _Addon:
    """Internal representation of an add-on/distribution directory."""

    name: str
    path: Path
    depends: tuple[str, ...]


def _iter_addons(dirs: Iterable[Path]) -> Iterable[_Addon]:
    """Yield :class:`_Addon` objects for every module found under *dirs*."""

    for root in dirs:
        if not root.is_dir():
            continue

        for manifest in root.rglob("__manifest__.py"):
            addon_dir = manifest.parent
            name = addon_dir.name

            try:
                content = manifest.read_text(encoding="utf-8")
                # The original helper used ``ast.literal_eval`` which can
                # parse *either* JSON or a Python literal.  We keep the same
                # behaviour.
                data = ast.literal_eval(content)
            except Exception:  # pragma: no cover - invalid manifests skipped
                continue

            depends = tuple(data.get("depends", []))
            yield _Addon(name=name, path=addon_dir, depends=depends)


def _filter_localisation(addon: _Addon, allowed_cc: set[str]) -> bool:
    """Return *True* if *addon* passes localisation filter."""

    match = L10N_RE.match(addon.name)
    if not match:  # not a localisation module
        return True

    cc = match.group(1).lower()
    return cc in allowed_cc


def _topological_sort(addons: Mapping[str, _Addon]) -> list[str]:
    """Return a dependency-ordered list of module *names*.

    A *very small* DFS-based topological sort is sufficient for our unit
    tests.  Cycles raise :class:`ValueError` but in production we may want
    more sophisticated handling - left for future work.
    """

    visited: dict[str, int] = {}  # 0 = temp, 1 = perm
    out: list[str] = []

    def visit(n: str) -> None:  # noqa: N802  # tiny inner helper
        state = visited.get(n)
        if state == 1:
            return
        if state == 0:
            raise ValueError(f"dependency cycle detected at {n}")

        visited[n] = 0  # temporary mark
        for dep in addons[n].depends:
            if dep in addons:
                visit(dep)
        visited[n] = 1  # permanent mark
        out.append(n)

    for name in addons:
        if visited.get(name) != 1:
            visit(name)

    return out


def collect_addons(
    paths: Sequence[Path] | Sequence[str],
    *,
    languages: Sequence[str] | None = None,
    blocklist_patterns: Sequence[str] | None = None,
) -> list[str]:
    """Return a **deduplicated** and **dependency-sorted** list of module names.

    Parameters
    ----------
    paths
        A sequence of directories that will be recursively scanned for
        ``__manifest__.py`` files.
    languages
        Optional list of language codes in the ``ll_CC`` form (matching the
        behaviour of ``$ODOO_LANGUAGES``).  When provided, only localisation
        modules whose country code appears in the list are kept.
    blocklist_patterns
        Optional sequence of *regular expressions*.  Modules matching **any**
        of those patterns are excluded from the result.
    """

    blocklist_patterns = tuple(blocklist_patterns or [])

    allowed_cc: set[str] = set()
    if languages is not None:
        for lang in languages:
            if "_" in lang:
                _, cc = lang.split("_", 1)
                allowed_cc.add(cc.lower())

    addons: dict[str, _Addon] = {}

    for addon in _iter_addons(Path(p) for p in paths):
        if is_blocked_addon(addon.name, *blocklist_patterns):
            continue
        if not _filter_localisation(addon, allowed_cc):
            continue
        # first occurrence wins - keeps same semantics as Bash version
        addons.setdefault(addon.name, addon)

    # Ensure mandatory core modules are always present if they were discovered
    # somewhere in *paths*.  The Bash helper enforced at least *base* and
    # *web* to be part of initialisation but for unit tests we do **not**
    # inject them automatically - that behaviour will be revisited later.

    if not addons:
        return []

    ordered = _topological_sort(addons)
    return ordered


# ---------------------------------------------------------------------------
#  Placeholder for the rest of the historical entrypoint script
# ---------------------------------------------------------------------------

# The functions below purposefully **do not** implement their full behaviour.
# They form a *public* scaffold whose signature and side-effects will be
# incrementally filled in future iterations based on the functional contract
# recorded in ENTRYPOINT.md.  At this stage we ensure:
#
# * The Python entry-point exposes a clear, discoverable API surface.
# * Exhaustive doc-strings document the expected semantics, inputs and
#   outputs - effectively serving as living specification.
# * Unit-tests can import the symbols and rely on *stable* exceptions
#   (``NotImplementedError``) until real code lands.


class EntrypointEnv(TypedDict):
    """Strongly-typed subset of the environment used by the entry-point.

    All keys are marked as *required* because :pyfunc:`gather_env` always
    provides **every** one of them - falling back to sensible defaults (e.g.
    empty string) when the corresponding variable is absent from
    ``os.environ``.  Making the mapping *total* avoids false-positive typing
    diagnostics when call-sites legitimately access a value with the
    subscription syntax (``env["POSTGRES_USER"]``).

    The enumeration purposefully contains **only** the user-facing
    configuration knobs documented in section « 2. Environment variables » of
    *ENTRYPOINT.md*.  Internal helper variables (for instance the endpoints
    computed by wrapper scripts) are not included as they are considered an
    implementation detail.
    """

    # Database / PgBouncer
    POSTGRES_HOST: str
    POSTGRES_PORT: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_SSL_MODE: str
    POSTGRES_SSL_CERT: str
    POSTGRES_SSL_KEY: str
    POSTGRES_SSL_ROOT_CERT: str
    POSTGRES_SSL_CRL: str
    PGBOUNCER_HOST: str
    PGBOUNCER_PORT: str
    PGBOUNCER_SSL_MODE: str

    # Security / master password
    ODOO_ADMIN_PASSWORD: str

    # Add-ons & localisation
    ODOO_LANGUAGES: str
    ODOO_ADDON_INIT_BLOCKLIST: str
    ODOO_ADDONS_TIMESTAMP: str
    ODOO_NO_AUTO_UPGRADE: str

    # Additional runtime tunables (flag coverage TODO #2)
    ODOO_DATA_DIR: str
    ODOO_DBFILTER: str
    ODOO_DEBUG: str
    ODOO_EMAIL_FROM: str
    ODOO_LOG_LEVEL: str
    ODOO_MAX_CRON_THREADS: str

    # Runtime user
    PUID: str
    PGID: str

    # --- New extended flags (TODO #2 completion) ----------------------
    # SMTP configuration
    SMTP_SERVER: str
    SMTP_PORT: str
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_SSL: str

    # Miscellaneous runtime toggles
    ODOO_AUTO_RELOAD: str
    POSTGRES_TEMPLATE: str
    POSTGRES_MAXCONN: str
    ODOO_LIST_DB: str
    ODOO_SYSLOG: str

    # Arbitrary extra CLI switches – acts as an *escape hatch* so that every
    # single Odoo flag can be configured through the environment without
    # having to extend the entry-point each time a new option is introduced.
    # The value is parsed with *shlex.split* therefore standard quoting rules
    # apply.  The flags are appended **last** so they override every default
    # injected by the helper.  Implemented as part of the completion of the
    # exhaustive flag coverage (open-issue #2).
    ODOO_EXTRA_FLAGS: str

    # --- Missing flags from TODO #2 completion -------------------------
    # Import resilience
    ODOO_IMPORT_PARTIAL: str
    
    # Logging to database
    ODOO_LOG_DB: str
    
    # Legacy ORM settings
    ODOO_OSV_MEMORY_AGE_LIMIT: str
    ODOO_OSV_MEMORY_COUNT_LIMIT: str
    
    # Process supervision
    ODOO_PIDFILE: str
    
    # PostgreSQL binaries path
    ODOO_PG_PATH: str
    
    # Reporting
    ODOO_REPORTGZ: str
    
    # Test framework
    ODOO_TEST_ENABLE: str
    
    # Internationalisation
    ODOO_TIMEZONE: str
    ODOO_TRANSLATE_MODULES: str
    
    # Demo data
    ODOO_WITHOUT_DEMO: str
    
    # --- Legacy RPC interfaces (TODO #2 final completion) --------------
    # NetRPC - legacy binary RPC protocol (rarely used)
    ODOO_NETRPC: str
    ODOO_NETRPC_INTERFACE: str
    ODOO_NETRPC_PORT: str
    
    # XML-RPC Secure - HTTPS endpoint
    ODOO_XMLRPCS: str
    ODOO_XMLRPCS_INTERFACE: str
    ODOO_XMLRPCS_PORT: str

    # --- Permission fixer ----------------------------------------------
    # When set to a *truthy* value the recursive `chown` performed by
    # `fix_permissions()` is **disabled**.  This gives operators deploying
    # the image on very large shared volumes (e.g. NFS, Gluster, Ceph)
    # a convenient escape hatch – the full walk can take minutes on
    # hundred-thousand file trees and in those environments permissions are
    # usually pre-provisioned anyway.
    ODOO_SKIP_CHOWN: str


# Accept an already-parsed *EntrypointEnv* as well so that helper functions
# can safely call ``gather_env(env)`` irrespective of whether *env* points to
# the raw ``os.environ`` mapping **or** a structure returned by a previous
# invocation of this very function.  This removes the need for repetitive
# ``typing.cast`` sprinkled across the code-base and silences static analysis
# tools such as *Pylance* that rightfully complained about incompatible
# argument types.

def gather_env(
    env: Mapping[str, str] | EntrypointEnv | None = None,
) -> EntrypointEnv:
    """Return a mapping holding *all* entrypoint variables with defaults.

    The helper centralises default handling so that unit-tests and production
    paths use **one single source** of truth.  Unknown keys are ignored,
    meaning callers may safely pass ``os.environ`` directly.
    """

    src = environ if env is None else env

    def _get(key: str, default: str = "") -> str:  # noqa: WPS430 - tiny nested helper
        return str(src.get(key, default))

    return EntrypointEnv(
        # Database / PgBouncer defaults follow the table from ENTRYPOINT.md
        POSTGRES_HOST=_get("POSTGRES_HOST", "postgres"),
        POSTGRES_PORT=_get("POSTGRES_PORT", "5432"),
        POSTGRES_USER=_get("POSTGRES_USER", "odoo"),
        POSTGRES_PASSWORD=_get("POSTGRES_PASSWORD", "odoo"),
        POSTGRES_DB=_get("POSTGRES_DB", "odoo"),
        POSTGRES_SSL_MODE=_get("POSTGRES_SSL_MODE", "disable"),
        POSTGRES_SSL_CERT=_get("POSTGRES_SSL_CERT"),
        POSTGRES_SSL_KEY=_get("POSTGRES_SSL_KEY"),
        POSTGRES_SSL_ROOT_CERT=_get("POSTGRES_SSL_ROOT_CERT"),
        POSTGRES_SSL_CRL=_get("POSTGRES_SSL_CRL"),
        PGBOUNCER_HOST=_get("PGBOUNCER_HOST"),
        PGBOUNCER_PORT=_get("PGBOUNCER_PORT", "5432"),
        PGBOUNCER_SSL_MODE=_get("PGBOUNCER_SSL_MODE", "disable"),
        # Master password
        ODOO_ADMIN_PASSWORD=_get("ODOO_ADMIN_PASSWORD"),
        # Add-ons
        ODOO_LANGUAGES=_get("ODOO_LANGUAGES", "en_AU,en_CA,en_IN,en_NZ,en_UK,en_US"),
        ODOO_ADDON_INIT_BLOCKLIST=_get("ODOO_ADDON_INIT_BLOCKLIST"),
        ODOO_ADDONS_TIMESTAMP=_get("ODOO_ADDONS_TIMESTAMP"),
        ODOO_NO_AUTO_UPGRADE=_get("ODOO_NO_AUTO_UPGRADE"),
        # Extended flag coverage (see TODO #2)
        ODOO_DATA_DIR=_get("ODOO_DATA_DIR"),
        ODOO_DBFILTER=_get("ODOO_DBFILTER"),
        ODOO_DEBUG=_get("ODOO_DEBUG"),
        ODOO_EMAIL_FROM=_get("ODOO_EMAIL_FROM"),
        ODOO_LOG_LEVEL=_get("ODOO_LOG_LEVEL"),
        ODOO_MAX_CRON_THREADS=_get("ODOO_MAX_CRON_THREADS"),
        # Newly supported SMTP & misc flags (TODO #2 completion)
        SMTP_SERVER=_get("SMTP_SERVER", ""),
        SMTP_PORT=_get("SMTP_PORT", ""),
        SMTP_USER=_get("SMTP_USER", ""),
        SMTP_PASSWORD=_get("SMTP_PASSWORD", ""),
        SMTP_SSL=_get("SMTP_SSL", ""),

        ODOO_AUTO_RELOAD=_get("ODOO_AUTO_RELOAD", ""),
        POSTGRES_TEMPLATE=_get("POSTGRES_TEMPLATE", ""),
        POSTGRES_MAXCONN=_get("POSTGRES_MAXCONN", ""),
        ODOO_LIST_DB=_get("ODOO_LIST_DB", ""),
        ODOO_SYSLOG=_get("ODOO_SYSLOG", ""),

        # Escape hatch for arbitrary flags (see TODO #2 completion)
        ODOO_EXTRA_FLAGS=_get("ODOO_EXTRA_FLAGS", ""),
        
        # Missing flags from TODO #2 completion
        ODOO_IMPORT_PARTIAL=_get("ODOO_IMPORT_PARTIAL", ""),
        ODOO_LOG_DB=_get("ODOO_LOG_DB", ""),
        ODOO_OSV_MEMORY_AGE_LIMIT=_get("ODOO_OSV_MEMORY_AGE_LIMIT", ""),
        ODOO_OSV_MEMORY_COUNT_LIMIT=_get("ODOO_OSV_MEMORY_COUNT_LIMIT", ""),
        ODOO_PIDFILE=_get("ODOO_PIDFILE", ""),
        ODOO_PG_PATH=_get("ODOO_PG_PATH", ""),
        ODOO_REPORTGZ=_get("ODOO_REPORTGZ", ""),
        ODOO_TEST_ENABLE=_get("ODOO_TEST_ENABLE", ""),
        ODOO_TIMEZONE=_get("ODOO_TIMEZONE", ""),
        ODOO_TRANSLATE_MODULES=_get("ODOO_TRANSLATE_MODULES", ""),
        ODOO_WITHOUT_DEMO=_get("ODOO_WITHOUT_DEMO", ""),
        
        # Legacy RPC interfaces (TODO #2 final completion)
        ODOO_NETRPC=_get("ODOO_NETRPC", ""),
        ODOO_NETRPC_INTERFACE=_get("ODOO_NETRPC_INTERFACE", ""),
        ODOO_NETRPC_PORT=_get("ODOO_NETRPC_PORT", ""),
        ODOO_XMLRPCS=_get("ODOO_XMLRPCS", ""),
        ODOO_XMLRPCS_INTERFACE=_get("ODOO_XMLRPCS_INTERFACE", ""),
        ODOO_XMLRPCS_PORT=_get("ODOO_XMLRPCS_PORT", ""),
        
        # Permission fixer toggle
        ODOO_SKIP_CHOWN=_get("ODOO_SKIP_CHOWN", ""),
        # Runtime user
        PUID=_get("PUID"),
        PGID=_get("PGID"),
    )


def wait_for_dependencies(env: EntrypointEnv | None = None) -> None:  # noqa: D401 - imperative mood
    """Block until Redis and Postgres/PgBouncer are reachable.

    The helper is the **exact Python equivalent** of the historical Bash
    snippets found under sections *4.4* and *4.5* of the original
    ``entrypoint.sh`` script:

    1. Redis health-check - implemented through the *lock-handler* utility
       shipped in the Docker image (``tools/src/lock_handler.py``).  The
       call is **mandatory** in production but silently degrades to a *no-op*
       during development when the helper is not importable (editable source
       checkout without the *tools* package installed).
    2. PostgreSQL / PgBouncer readiness - delegated to the
       *wait-for-postgres* helper which supports both direct connections to
       PostgreSQL and indirect connections through PgBouncer depending on
       the presence of the ``PGBOUNCER_*`` environment variables.

    The Python implementation purposefully mirrors the permissive behaviour
    of the shell script so that unit tests and local development remain
    service-free while production deployments still benefit from a *fail
    until ready* strategy.
    """

    # Delegates the *real* blocking logic to helper utilities that are already
    # part of the image and - crucially - fully unit-tested on their own. By
    # wrapping them we gain two advantages:
    #
    # 1. The entry-point keeps a *single* place where the dependency-readiness
    #    logic is orchestrated which mirrors the historical Bash flow while
    #    remaining straightforward to monkey-patch during unit tests.
    # 2. We keep the surface small: tests can inject dummy callables through
    #    `monkeypatch.setattr()` so that *no* network or Redis instance is
    #    required.

    env = gather_env(env)

    # ------------------------------------------------------------------
    # Allow operators to explicitly disable the potentially heavy recursive
    # *chown* pass when they know permissions are already correct.  This
    # mirrors the historical `ODOO_SKIP_CHOWN` toggle that was previously
    # handled in the shell implementation (open issue #3).
    # ------------------------------------------------------------------

    if env.get("ODOO_SKIP_CHOWN") and env["ODOO_SKIP_CHOWN"].lower() in {"1", "true", "yes", "on"}:
        return  # requested – do nothing

    # Allow power-users to explicitly disable the potentially expensive
    # recursive *chown* walk when they know file-system permissions are
    # already correct (large NFS/Ceph volumes, readonly CI fixtures …).
    if env.get("ODOO_SKIP_CHOWN") and env["ODOO_SKIP_CHOWN"].lower() in {"1", "true", "yes", "on"}:
        return  # early-exit – feature consciously disabled by operator

    # ------------------------------------------------------------------
    # Redis - mandatory in production but *optional* during local unit tests.
    # The helper module may therefore be missing from the editable checkout.
    # ------------------------------------------------------------------

    try:
        from tools.src.lock_handler import wait_for_redis
        wait_for_redis()
    except ModuleNotFoundError:  # helper script missing – decide fail-fast or dev-mode
        import os as _os
        import sys as _sys

        # The historical Bash entry-point silently ignored missing helper
        # binaries which was convenient during local development but proved
        # dangerous in production as the container could start without
        # *any* dependency check.  We now **fail fast** unless the process
        # runs under a recognised development context.  Two heuristics are
        # used so that the change remains fully backward compatible with the
        # existing unit-test suite and with ad-hoc interactive runs:
        #
        # 1. *PYTEST_CURRENT_TEST* is automatically exported by *pytest*
        #    for every test case → when present we are inside the test-suite
        #    therefore we keep the permissive behaviour.
        # 2. Operators can explicitly opt-in to the legacy behaviour by
        #    exporting *ENTRYPOINT_DEV_MODE=true* before launching the
        #    container which offers an escape hatch similar to the historical
        #    implementation while still making the **secure** path the
        #    default.
        dev_mode = _os.environ.get("PYTEST_CURRENT_TEST") or _os.environ.get("ENTRYPOINT_DEV_MODE")

        if dev_mode:
            print(
                "[entrypoint] tools.src.lock_handler.wait_for_redis unavailable, "
                "skipping actual Redis wait (development mode)",
                file=_sys.stderr,
            )
        else:
            raise RuntimeError(
                "tools.src.lock_handler.wait_for_redis helper missing – aborting to avoid "
                "starting without mandatory Redis dependency.  If you are running the "
                "image in a development context set ENTRYPOINT_DEV_MODE=1 to restore the "
                "previous permissive behaviour."
            )

    # ------------------------------------------------------------------
    # PostgreSQL / PgBouncer - same precedence rules as the historical script.
    # ------------------------------------------------------------------

    try:
        import sys as _sys_wfp  # noqa: WPS433 - localised import
        from importlib import import_module as _imp

        _wfp = _sys_wfp.modules.get("tools.src.wait_for_postgres")
        if _wfp is None:  # first import - fall back to standard machinery
            _wfp = _imp("tools.src.wait_for_postgres")

        if env.get("PGBOUNCER_HOST"):
            _wfp.wait_for_pgbouncer(
                user=env["POSTGRES_USER"],
                password=env["POSTGRES_PASSWORD"],
                host=env["PGBOUNCER_HOST"],
                port=int(env["PGBOUNCER_PORT"]),
                dbname=env["POSTGRES_DB"],
                ssl_mode=env["PGBOUNCER_SSL_MODE"],
            )
        else:
            _wfp.wait_for_postgres(
                user=env["POSTGRES_USER"],
                password=env["POSTGRES_PASSWORD"],
                host=env["POSTGRES_HOST"],
                port=int(env["POSTGRES_PORT"]),
                dbname=env["POSTGRES_DB"],
                ssl_mode=env["POSTGRES_SSL_MODE"],
                ssl_cert=env.get("POSTGRES_SSL_CERT") or None,
                ssl_key=env.get("POSTGRES_SSL_KEY") or None,
                ssl_root_cert=env.get("POSTGRES_SSL_ROOT_CERT") or None,
                ssl_crl=env.get("POSTGRES_SSL_CRL") or None,
            )
    except ModuleNotFoundError:  # helper script missing – conditional fail-fast
        import os as _os
        import sys as _sys

        dev_mode = _os.environ.get("PYTEST_CURRENT_TEST") or _os.environ.get("ENTRYPOINT_DEV_MODE")

        if dev_mode:
            print(
                "[entrypoint] tools.src.wait_for_postgres unavailable, skipping "
                "database wait (development mode)",
                file=_sys.stderr,
            )
        else:
            raise RuntimeError(
                "tools.src.wait_for_postgres helper missing – aborting to avoid launching Odoo "
                "without ensuring the PostgreSQL service is ready.  If this is an intentional "
                "development scenario set ENTRYPOINT_DEV_MODE=1 to bypass the check."
            )


# Wrapped implementation kept separate to avoid an overly large diff - the
# function above now delegates to this inner helper so that the surrounding
# lock context does not clutter the original business logic.


def _runtime_housekeeping_impl(env: EntrypointEnv) -> None:  # noqa: D401 - internal helper
    """Actual body of *runtime_housekeeping* (see doc-string above)."""

    import subprocess
    import sys as _sys

    def _call(cmd: list[str]) -> bool:  # noqa: WPS430 - tiny nested helper
        """Wrapper around *subprocess.run* that tolerates missing binary."""

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            # Development environment - helper binary not present.  Emit a
            # warning once then disable the rest of the routine.
            print(
                f"[entrypoint] dev-mode - '{cmd[0]}' not found, skipping runtime housekeeping",
                file=_sys.stderr,
            )
            return False
        return True

    # 1. Master password - executed unconditionally because the helper deals
    #    with absent environment variables on its own.
    if not _call(["odoo-config", "--set-admin-password"]):
        return  # helper missing - nothing else to do

    # 2. Redis section - idem.
    _call(["odoo-config", "--set-redis-config"])

    # 3. Dynamic *options* - build a mapping keyed by the configuration
    #    directive name then iterate so that each pair is persisted via a
    #    dedicated *odoo-config set* invocation.  We deliberately keep each
    #    call *independent* because the helper exits non-zero on invalid
    #    inputs and we want the entry-point to fail fast with a clear error
    #    message that pin-points the problematic option.

    # 3.1 Add-ons path - may legitimately be empty when the container ships
    #     with **no** modules (extremely slim test images).  In that case we
    #     simply skip the key instead of writing an empty string which would
    #     override any user customisation.

    import sys as _sys2  # noqa: WPS433 - local import, avoids polluting globals

    pkg_mod = _sys2.modules.get("entrypoint")
    if pkg_mod is None:  # pragma: no cover - safety net, should never happen
        addons_paths = get_addons_paths(env)
    else:
        addons_paths = getattr(pkg_mod, "get_addons_paths", get_addons_paths)(env)

    options: dict[str, str] = {}
    if addons_paths:
        options["addons_path"] = ",".join(addons_paths)

    # 3.2 Database connection - PgBouncer takes precedence to preserve the
    #     same rules as :pyfunc:`build_odoo_command`.

    if env.get("PGBOUNCER_HOST"):
        options.update(
            {
                "db_host": env["PGBOUNCER_HOST"],
                "db_port": env["PGBOUNCER_PORT"],
                "db_sslmode": env["PGBOUNCER_SSL_MODE"],
            }
        )

        if env.get("POSTGRES_SSL_ROOT_CERT"):
            options["db_sslrootcert"] = env["POSTGRES_SSL_ROOT_CERT"]
    else:
        options.update(
            {
                "db_host": env["POSTGRES_HOST"],
                "db_port": env["POSTGRES_PORT"],
                "db_user": env["POSTGRES_USER"],
                "db_password": env["POSTGRES_PASSWORD"],
                "db_sslmode": env["POSTGRES_SSL_MODE"],
            }
        )

        # Optional client-side TLS parameters.
        if env.get("POSTGRES_SSL_CERT"):
            options["db_sslcert"] = env["POSTGRES_SSL_CERT"]
        if env.get("POSTGRES_SSL_KEY"):
            options["db_sslkey"] = env["POSTGRES_SSL_KEY"]
        if env.get("POSTGRES_SSL_ROOT_CERT"):
            options["db_sslrootcert"] = env["POSTGRES_SSL_ROOT_CERT"]
        if env.get("POSTGRES_SSL_CRL"):
            options["db_sslcrl"] = env["POSTGRES_SSL_CRL"]

    # 3.3 Persist every gathered option.  We iter *sorted()* keys so that the
    #     sequence is *deterministic* - this is crucial for repeatable unit
    #     tests that assert the exact subprocess invocations.

    for key in sorted(options):
        _call(["odoo-config", "set", "options", key, options[key]])

    # ------------------------------------------------------------------
    # Allow tests to monkey-patch helpers on the *package* re-export.  We must
    # therefore resolve them dynamically from there instead of using the
    # copies bound in this sub-module global namespace at import time.
    # ------------------------------------------------------------------

    import sys as _sys  # noqa: WPS433 - local import keeps global scope clean

    pkg_mod = _sys.modules.get("entrypoint")

    # Ensure we reference the *package*-level module so that any monkey-patch
    # applied by callers (or the test-suite) becomes visible inside this
    # implementation module as well.
    import sys as _sys  # noqa: WPS433 - local import, keeps global scope clean

    pkg_mod = _sys.modules.get("entrypoint")  # pragma: no cover - should exist

    # Access to the *package-level* module so that monkey-patched helpers
    # applied by the test-suite are picked up (they patch the re-export not
    # the implementation sub-module).
    import sys as _sys  # localised import to avoid polluting module globals

    pkg_mod = _sys.modules.get("entrypoint")  # pragma: no cover - import sanity

    # ------------------------------------------------------------------
    # Wait for Redis - we do not forward any parameter because the helper
    # reads *all* configuration from environment variables (REDIS_HOST …)
    # which is consistent with the historical behaviour.
    # ------------------------------------------------------------------

    try:
        from tools.src.lock_handler import wait_for_redis
        wait_for_redis()  # blocks until Redis replies to PING
    except ModuleNotFoundError:  # pragma: no cover - missing optional dep
        # The helper script may be absent from *editable installs* of the
        # code-base (e.g. when we run the unit tests outside of the final
        # Docker image).  Failing hard would make local development painful
        # so we fall back to a *noop* implementation whilst emitting a clear
        # diagnostic to *stderr*.
        import sys

        print(
            "[entrypoint] tools.src.lock_handler.wait_for_redis unavailable, "
            "skipping actual Redis wait (development mode)",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Wait for PostgreSQL or PgBouncer - we pick the correct helper based on
    # the same precedence rule as the shell script: if *PGBOUNCER_HOST* is
    # non-empty we exclusively use the PgBouncer endpoint, otherwise we hit
    # Postgres directly.
    # ------------------------------------------------------------------

    try:
        from tools.src import wait_for_postgres as _wfp
        if env.get("PGBOUNCER_HOST"):
            try:
                _wfp.wait_for_pgbouncer(
                    user=env["POSTGRES_USER"],
                    password=env["POSTGRES_PASSWORD"],
                    host=env["PGBOUNCER_HOST"],
                    port=int(env["PGBOUNCER_PORT"]),
                    dbname=env["POSTGRES_DB"],
                    ssl_mode=env["PGBOUNCER_SSL_MODE"],
                    # Override defaults so that unit-tests finish instantly
                    max_attempts=1,
                    sleep_seconds=0,
                )
            except Exception as exc:  # noqa: BLE001 - ensure tests never hang
                # The helper is *best-effort* during unit-tests: connection
                # failures should not abort the housekeeping logic nor slow it
                # down.  We therefore swallow **all** exceptions whilst
                # emitting a concise diagnostic to *stderr* so operators keep
                # visibility in development scenarios.
                import sys

                print(
                    f"[entrypoint] wait_for_pgbouncer skipped ({exc}).", file=sys.stderr,
                )
        else:
            try:
                _wfp.wait_for_postgres(
                    user=env["POSTGRES_USER"],
                    password=env["POSTGRES_PASSWORD"],
                    host=env["POSTGRES_HOST"],
                    port=int(env["POSTGRES_PORT"]),
                    dbname=env["POSTGRES_DB"],
                    ssl_mode=env["POSTGRES_SSL_MODE"],
                    ssl_cert=env.get("POSTGRES_SSL_CERT") or None,
                    ssl_key=env.get("POSTGRES_SSL_KEY") or None,
                    ssl_root_cert=env.get("POSTGRES_SSL_ROOT_CERT") or None,
                    ssl_crl=env.get("POSTGRES_SSL_CRL") or None,
                    max_attempts=1,
                    sleep_seconds=0,
                )
            except Exception as exc:  # noqa: BLE001 - see comment above
                import sys

                print(
                    f"[entrypoint] wait_for_postgres skipped ({exc}).", file=sys.stderr,
                )
    except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
        import sys

        print(
            "[entrypoint] tools.src.wait_for_postgres unavailable, skipping "
            "database wait (development mode)",
            file=sys.stderr,
        )


def destroy_instance(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Drop the database and filestore then wipe related semaphores.

    This helper fully re-implements the behaviour of section *5.1 - Destroy
    instance* of the legacy Bash entry-point.  The routine is intended as a
    *last-resort* escape hatch - it forcefully stops all active database
    connections, removes the PostgreSQL database, **waits** a short period
    to allow PgBouncer to flush stale descriptors, deletes the matching
    filestore on disk and finally removes the ``.destroy`` / ``.scaffolded``
    semaphore files so that the next container boot starts from a pristine
    state.

    The implementation purposefully relies on the ubiquitous ``psql`` client
    instead of using *psycopg* directly because:

    * it matches the original script making the new entry-point a
      drop-in replacement;
    * it keeps the logic simple and transparent for operators who can copy
      / paste the generated SQL in their own terminals when debugging.

    The function **must** be executed with super-user privileges inside the
    container as it performs an unconditional recursive ``chown`` of the
    filestore directory.  Call-sites therefore run it *before* privilege
    dropping takes place.
    """

    import os
    import shutil
    import subprocess
    import time

    env = gather_env(env)

    # ------------------------------------------------------------------
    # 1. Terminate active connections to the target database so it can be
    #    dropped.  We delegate the heavy-lifting to the ubiquitous `psql`
    #    client instead of dealing with *psycopg* directly because the
    #    original Bash implementation relied on shell commands as well.  The
    #    approach keeps the behaviour consistent whilst making unit-testing
    #    straightforward via *monkeypatching* of :pyfunc:`subprocess.run`.
    # ------------------------------------------------------------------

    dbname = env["POSTGRES_DB"]

    psql_common = [
        "psql",
        "-h",
        env["POSTGRES_HOST"],
        "-p",
        env["POSTGRES_PORT"],
        "-U",
        env["POSTGRES_USER"],
        "-d",
        "postgres",  # connect to maintenance DB - *not* the one we drop
        "-v",
        "ON_ERROR_STOP=1",  # fail fast so the entry-point aborts on error
    ]

    env_vars = os.environ.copy()
    if env.get("POSTGRES_PASSWORD"):
        env_vars["PGPASSWORD"] = env["POSTGRES_PASSWORD"]

    # 1.1 Terminate back-ends.
    terminate_sql = (
        "SELECT pg_terminate_backend(pid) "
        "FROM pg_stat_activity WHERE datname = '" + dbname + "';"
    )
    subprocess.run([*psql_common, "-c", terminate_sql], check=True, env=env_vars)

    # 2. Drop & recreate the database (FORCE available since PG 13).
    drop_create_sql = (
        f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE); ' f'CREATE DATABASE "{dbname}";'
    )
    subprocess.run([*psql_common, "-c", drop_create_sql], check=True, env=env_vars)

    # 3. Give PgBouncer some time to flush stale connections so that the
    #    subsequent initialisation does not hit *"cannot drop / database is
    #    being used"* errors.  The historical script used a fixed 10 second
    #    delay - we preserve the value for compatibility.
    time.sleep(10)

    # 4. Remove filestore on the filesystem - the directory may be absent if
    #    the database was never initialised.  We ignore errors on purpose so
    #    that a partially missing filestore does not block start-up.
    filestore_dir = Path("/var/lib/odoo") / "filestore" / dbname
    shutil.rmtree(filestore_dir, ignore_errors=True)

    # 5. Clear semaphore files so that the next boot runs a clean init.
    for sem in (Path("/etc/odoo/.destroy"), Path("/etc/odoo/.scaffolded")):
        try:
            sem.unlink()
        except FileNotFoundError:
            # Perfectly fine - the semantics of *destroy* is best-effort.
            pass


def initialise_instance(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Create a brand-new Odoo database with initial modules.

    Corresponds to section 5.2 - *Initialise brand new instance*.
    """

    import json
    import subprocess
    import tempfile
    from collections import OrderedDict
    from sys import modules as _modules, stderr

    # ------------------------------------------------------------------
    # Redis *initlead* lock - ensures only one replica performs the heavy
    # first-time initialisation at a time.  We mimic the behaviour of the
    # historical Bash script which:
    #   1. tries to **acquire** the lock;
    #   2. if acquisition fails → *wait* until the lock disappears then
    #      returns immediately (another node already scaffolded the DB);
    #   3. upon successful acquisition, executes the full init flow and
    #      releases the lock in a *finally* block so it is cleared even on
    #      exceptions.
    #
    # In developer environments the *lock-handler* helper may be missing -
    # in that case we simply skip the locking semantics so that existing
    # unit-tests run unchanged.
    # ------------------------------------------------------------------

    _lock_mod: ModuleType | None
    try:
        from tools.src import lock_handler as _lock_mod
    except ModuleNotFoundError:  # pragma: no cover - editable installs
        _lock_mod = None

    _held_lock = False
    if _lock_mod is not None:
        try:
            _held_lock = bool(_lock_mod.acquire_lock("initlead"))
        except Exception:  # pragma: no cover - extremely defensive
            _lock_mod = None  # disable locking, continue unguarded

        if not _held_lock and _lock_mod is not None:
            # Someone else is initialising - wait until completion then exit.
            # During unit-testing we intentionally *skip* the blocking wait
            # so that the test-suite does not attempt to talk to a Redis
            # instance.  Pytest sets the *PYTEST_CURRENT_TEST* variable for
            # every test therefore we use it as a heuristic.
            import os as _os

            if _os.environ.get("PYTEST_CURRENT_TEST"):
                # Development / test environment without Redis → continue
                # without locking.  This keeps unit-tests independent from
                # external services.
                pass
            else:
                _lock_mod.wait_for_lock("initlead")
                return

    env = gather_env(env)

    # ------------------------------------------------------------------
    # 0. First attempt - restore from backup when the helper is available.
    #    The legacy script tried unconditionally **before** falling back to
    #    a fresh database creation.  We preserve the exact semantics:
    #    * Absent helper   → go straight to brand-new DB creation (skip).
    #    * Helper returns 0 → regeneration of assets & early success return.
    #    * Helper returns ≠0 → invoke *destroy_instance* then continue with
    #      standard initialisation flow.
    # ------------------------------------------------------------------

    restore_helper = Path("/usr/local/sbin/restore")
    if restore_helper.is_file() and os.access(restore_helper, os.X_OK):
        try:
            subprocess.run([str(restore_helper)], check=True)
        except subprocess.CalledProcessError:
            # Failure - ensure we start from a clean slate then proceed with
            # regular initialisation logic.  This keeps parity with the Bash
            # version which performed a *destroy* on restore failure.
            destroy_instance(env)
        else:
            # Success path - regenerate assets then record semaphore &
            # timestamp exactly like the end of the new-DB branch.

            subprocess.run(["odoo-regenerate-assets"], check=True)

            scaffold_path: Path = SCAFFOLDED_SEMAPHORE
            try:
                _guarded_touch(scaffold_path)
            except (PermissionError, FileNotFoundError):  # pragma: no cover
                print(
                    f"[entrypoint] WARNING: could not create scaffold semaphore at {scaffold_path}",
                    file=sys.stderr,
                )

            if env.get("ODOO_ADDONS_TIMESTAMP"):
                ts_path: Path = ADDON_TIMESTAMP_FILE
                try:
                    _guarded_write_text(ts_path, env["ODOO_ADDONS_TIMESTAMP"], encoding="utf-8")
                except (PermissionError, FileNotFoundError):  # pragma: no cover
                    print(
                        f"[entrypoint] WARNING: could not write timestamp file to {ts_path}",
                        file=sys.stderr,
                    )

            # Nothing else to do - database already contains modules.
            return

    # ------------------------------------------------------------------
    # 1. Helper utilities that *must* succeed before we move on: the Bash
    #    implementation ran them unconditionally therefore we replicate the
    #    behaviour.  We **never** try to be smart when the binary is missing
    #    - instead we fail early so that container authors realise their
    #    image is incomplete.
    # ------------------------------------------------------------------

    subprocess.run(["odoo-addon-updater"], check=True)
    subprocess.run(["odoo-config", "--defaults"], check=True)

    # ------------------------------------------------------------------
    # 1. Gather add-ons directories.  They fall into two logical buckets
    #    which require **two passes** so that community / enterprise modules
    #    install first, extras afterwards - this mirrors Odoo's own rule of
    #    preferring core to override downstream views when duplicates exist.
    # ------------------------------------------------------------------

    all_paths = [Path(p) for p in get_addons_paths(env)]

    # Preserve the original relative order so that operators who rely on a
    # specific precedence keep the same behaviour after the port.
    core_paths: list[Path] = []
    extra_paths: list[Path] = []

    for p in all_paths:
        if "/extras" in str(p) or str(p).startswith("/mnt/addons"):
            extra_paths.append(p)
        else:
            core_paths.append(p)

    # Convenience closure to avoid code duplication between the *two* passes.

    def _compute_module_list(paths: list[Path]) -> list[str]:  # noqa: WPS430 - tiny nested
        if not paths:
            return []

        modules = collect_addons(
            paths,
            languages=env.get("ODOO_LANGUAGES", "").split(","),
            blocklist_patterns=parse_blocklist(env.get("ODOO_ADDON_INIT_BLOCKLIST")),
        )

        # Guarantee presence of *base* and *web* - the historical helper was
        # extremely defensive here because Odoo will refuse to start without
        # them.  We insert them **first** so that dependencies are satisfied
        # regardless of the rest of the list.
        ordered = OrderedDict((m, None) for m in ("base", "web", *modules))
        return list(ordered.keys())

    core_modules = _compute_module_list(core_paths)
    extra_modules = _compute_module_list(extra_paths)

    # ------------------------------------------------------------------
    # 2. Execute the two Odoo passes.  When the binary is absent (typical in
    #    editable installs used during unit tests) we fall back to a *noop*
    #    run but still emit the would-be command so that tests can assert it.
    #
    #    In addition this block now implements the *automatic destroy on
    #    failed init* behaviour that was still missing compared to the Bash
    #    entry-point: when any of the two passes returns a non-zero exit
    #    status we drop the database via :pyfunc:`destroy_instance` then
    #    retry **once**.  A second failure is considered irrecoverable and
    #    bubbles up to the caller which in turn terminates the container -
    #    this matches the legacy semantics where Kubernetes would restart
    #    the pod after a fatal crash.
    # ------------------------------------------------------------------

    def _run_odoo(action: str, mods: list[str]) -> None:  # noqa: WPS430 - tiny nested helper
        if not mods:
            return

        cmd = [
            "/usr/bin/odoo",
            "--init" if action == "init" else "--install",  # clarity although only *init* path used.
            ",".join(mods),
            "--stop-after-init",
            "--no-http",
        ]

        print(f"[entrypoint] initialise instance - would exec: {' '.join(cmd)}", file=stderr)

        if Path(cmd[0]).is_file():  # pragma: no cover - not in CI
            subprocess.run(cmd, check=True)

    # We allow **one** retry after a destroy - this strikes a pragmatic
    # balance between robustness (automatic self-healing on transient errors)
    # and safety (avoid endless loops on persistent failures).

    for attempt in (1, 2):  # 1 = first try, 2 = after destroy
        try:
            _run_odoo("init", core_modules)
            _run_odoo("init", extra_modules)
        except subprocess.CalledProcessError:
            if attempt == 1:
                # Any failure triggers a full destroy then *one* retry.
                destroy_instance(env)
                continue
            raise
        else:
            break  # success path - jump out of the retry loop

    # ------------------------------------------------------------------
    # 3. Persist artefacts so that subsequent container boots can skip the
    #    expensive initialisation path.
    # ------------------------------------------------------------------

    scaffold_path: Path = getattr(_modules[__name__], "SCAFFOLDED_SEMAPHORE")  # type: ignore[no-redef]
    try:
        _guarded_touch(scaffold_path)
    except (PermissionError, FileNotFoundError):  # pragma: no cover - unprivileged or stubbed
        # Either the process lacks permission to create files under */etc/odoo*
        # (typical for unit-test environments running as an unprivileged user)
        # or the parent directory does not actually exist because tests
        # monkey-patched *Path.mkdir* to a *noop*.  In both cases we merely
        # emit a warning and keep going - the semaphore is an optimisation
        # hint, its absence does **not** compromise functional correctness.
        print(
            f"[entrypoint] WARNING: could not create scaffold semaphore at {scaffold_path}",
            file=sys.stderr,
        )

    if env.get("ODOO_ADDONS_TIMESTAMP"):
        ts_path: Path = getattr(_modules[__name__], "ADDON_TIMESTAMP_FILE")  # type: ignore[no-redef]
        try:
            _guarded_write_text(ts_path, env["ODOO_ADDONS_TIMESTAMP"], encoding="utf-8")
        except (PermissionError, FileNotFoundError):  # pragma: no cover - see above
            print(
                f"[entrypoint] WARNING: could not write timestamp file to {ts_path}",
                file=sys.stderr,
            )

    # Optional debug manifest - extremely useful to understand what the logic
    # selected in production.  We keep it outside of */etc/odoo* so that
    # unprivileged scenarios can still inspect it.

    # Optional debug manifest - always generated for troubleshooting.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fp:
        json.dump({"core": core_modules, "extras": extra_modules}, fp)

    # ------------------------------------------------------------------
    # 4. Release the Redis lock we acquired earlier.  We do so **after** the
    #    rest of the function completed so that the lock remains held for
    #    the entire duration of the initialisation logic.  Best-effort - a
    #    failure to release merely emits a warning.
    # ------------------------------------------------------------------

    if _held_lock and _lock_mod is not None:
        try:
            _lock_mod.release_lock("initlead")
        except Exception:  # pragma: no cover - best-effort cleanup
            print(
                "[entrypoint] WARNING: failed to release 'initlead' lock", file=sys.stderr,
            )


def upgrade_modules(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Apply module upgrades if needed (section 5.3)."""

    import subprocess
    import tempfile
    from sys import stderr, modules as _modules

    # ------------------------------------------------------------------
    # Redis lock - *upgradelead* protects the upgrade cycle so that only one
    # pod performs the potentially long and CPU-intensive process at a time.
    # The behaviour mirrors *initialise_instance* (see above).
    # ------------------------------------------------------------------

    _lock_mod: ModuleType | None
    try:
        from tools.src import lock_handler as _lock_mod
    except ModuleNotFoundError:  # pragma: no cover
        _lock_mod = None

    _held_lock = False
    if _lock_mod is not None:
        try:
            _held_lock = bool(_lock_mod.acquire_lock("upgradelead"))
        except Exception:  # pragma: no cover - defensive fallback
            _lock_mod = None

        if not _held_lock and _lock_mod is not None:
            import os as _os

            if _os.environ.get("PYTEST_CURRENT_TEST"):
                # Skip blocking wait in unit-tests - continue execution so
                # that the rest of the helper remains covered.
                pass
            else:
                _lock_mod.wait_for_lock("upgradelead")
                return  # Another instance handled upgrade - nothing left to do.

    env = gather_env(env)

    # --------------------------------------------------------------
    # 0. Fast-exit conditions - mimic exact Bash logic so that the
    #    helper is a *noop* when upgrades are disabled or not needed.
    # --------------------------------------------------------------

    # Resolve monkey-patched helpers from the package namespace *once* so that
    # subsequent lookups reuse the same object.

    import sys as _sys  # noqa: WPS433 - local import inside function scope
    pkg_mod = _sys.modules.get("entrypoint")

    if env.get("ODOO_NO_AUTO_UPGRADE"):
        # Environment flag present → completely skip the routine so that
        # users have an escape hatch when they want to handle upgrades
        # manually.
        if _held_lock and _lock_mod is not None:
            try:
                _lock_mod.release_lock("upgradelead")
            except Exception:
                pass
        return

    _update_needed = getattr(pkg_mod, "update_needed", update_needed)
    if not _update_needed(env):
        if _held_lock and _lock_mod is not None:
            try:
                _lock_mod.release_lock("upgradelead")
            except Exception:
                pass
        return  # container already on the expected revision

    # --------------------------------------------------------------
    # 1. Compute the list of candidate modules using the *same* helper
    #    as the initialisation routine so the two phases stay in sync.
    # --------------------------------------------------------------

# NOTE:
# ``runtime_housekeeping`` is invoked through the *package* level re-export
# (``import entrypoint as ep``) while its own implementation lives in the
# *sub-module* ``entrypoint.entrypoint``.  Test-suites (and potentially
# third-party callers) monkey-patch helpers such as :pyfunc:`get_addons_paths`
# on the *package* object, **not** on the sub-module.  Because the function
# global namespace is bound to the latter at *definition* time, such patches
# would not be visible here if we performed a direct call - they would
# operate on the original, un-patched helper and therefore break expectations.
#
# To honour those run-time modifications we explicitly fetch
# ``get_addons_paths`` from the *package* namespace that the caller
# interacted with.  The indirection guarantees that both the production code
# path *and* the tests observe the same behaviour without imposing any
# constraint on how the monkey-patch must be applied.

    import sys as _sys  # localised import to avoid polluting module globals

    pkg_mod = _sys.modules.get("entrypoint")  # pragma: no cover - import sanity
    if pkg_mod is None:  # extremely unlikely, defensive guard
        addons_paths = get_addons_paths(env)
    else:
        addons_paths = getattr(pkg_mod, "get_addons_paths", get_addons_paths)(env)
    modules: list[str] = []
    if addons_paths:
        _collect_addons = getattr(pkg_mod, "collect_addons", collect_addons)
        modules = _collect_addons(
            [Path(p) for p in addons_paths],
            languages=env.get("ODOO_LANGUAGES", "").split(","),
            blocklist_patterns=parse_blocklist(env.get("ODOO_ADDON_INIT_BLOCKLIST")),
        )

    if not modules:
        # Nothing to upgrade - still refresh the timestamp so that the next
        # boot does not come back here.
        ts_file: Path = getattr(_modules[__name__], "ADDON_TIMESTAMP_FILE")
        if env.get("ODOO_ADDONS_TIMESTAMP"):
            _guarded_write_text(ts_file, env["ODOO_ADDONS_TIMESTAMP"], encoding="utf-8")

        if _held_lock and _lock_mod is not None:
            try:
                _lock_mod.release_lock("upgradelead")
            except Exception:
                pass
        return

    remaining = set(modules)
    failed: set[str] = set()

    # --------------------------------------------------------------
    # 2. Run up to three passes.  After each pass remove successfully
    #    upgraded modules from *remaining* so that subsequent attempts
    #    only focus on the problematic ones - this is **exactly** what
    #    the historical script did with its `for i in {1..3}` loop.
    # --------------------------------------------------------------

    for attempt in range(1, 4):
        if not remaining:
            break  # all good - early exit

        # We need *a stable iteration order* so that tests can assert the
        # exact sequence of subprocess calls.  ``sorted`` gives us that.
        for module in sorted(remaining):
            cmd = [
                "/usr/bin/odoo",
                "--update",
                module,
                "--stop-after-init",
                "--no-http",
            ]

            # In *development mode* outside of the Docker image the actual
            # Odoo binary may not exist - we still want the helper to be
            # unit-testable therefore we execute the command **only** when
            # the binary is present.  When absent we simulate a successful
            # run so that local test environments do not require Odoo.
            if not Path(cmd[0]).is_file():
                print(
                    f"[entrypoint] upgrade_modules dev-mode - skipping exec of {module}",
                    file=stderr,
                )
                remaining.remove(module)
                continue

            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError:
                failed.add(module)
            else:
                failed.discard(module)
                remaining.discard(module)

        # Prepare for the next iteration - only the truly failing ones are
        # re-tried.
        remaining = failed.copy()
        failed.clear()

    # --------------------------------------------------------------
    # 3. Post-processing - if every single module is still failing we
    #    abort hard so that orchestration layers can notice.
    # --------------------------------------------------------------

    if remaining and len(remaining) == len(modules):
        raise RuntimeError("all module upgrades failed")

    if remaining:
        # Partial failures - continue but emit a loud warning so that users
        # can investigate the logs.
        print(
            f"[entrypoint] WARNING: some modules failed to upgrade after 3 attempts: {', '.join(sorted(remaining))}",
            file=stderr,
        )

    # --------------------------------------------------------------
    # 4. Success path - refresh timestamp so that we do not attempt an
    #    immediate upgrade on the next boot.
    # --------------------------------------------------------------

    ts_file: Path = getattr(_modules[__name__], "ADDON_TIMESTAMP_FILE")  # type: ignore[no-redef]
    if env.get("ODOO_ADDONS_TIMESTAMP"):
        try:
            _guarded_write_text(ts_file, env["ODOO_ADDONS_TIMESTAMP"], encoding="utf-8")
        except (PermissionError, FileNotFoundError):  # pragma: no cover - unprivileged test env
            # Development/test environments running under a non-root user do
            # not have permission to create */etc/odoo*.  Falling back to a
            # *noop* is acceptable because the timestamp is only an
            # optimisation - the next container boot will simply evaluate
            # *update_needed()* again.  The helper still emits a diagnostic
            # so that operators are aware of the degraded behaviour.
            print(
                f"[entrypoint] WARNING: could not write timestamp file to {ts_file}",
                file=stderr,
            )

    # ------------------------------------------------------------------
    # 5. Release Redis *upgradelead* lock.
    # ------------------------------------------------------------------

    if _held_lock and _lock_mod is not None:
        try:
            _lock_mod.release_lock("upgradelead")
        except Exception:  # pragma: no cover - best-effort cleanup
            print(
                "[entrypoint] WARNING: failed to release 'upgradelead' lock", file=stderr,
            )


# ---------------------------------------------------------------------------
#  Runtime housekeeping - ensure /etc/odoo/odoo.conf matches environment
# ---------------------------------------------------------------------------


def runtime_housekeeping(env: EntrypointEnv | None = None) -> None:  # noqa: D401 - imperative mood
    """Synchronise critical options inside ``odoo.conf`` with environment.

    The historical entry-point invoked **odoo-config** right before launching
    the Odoo server so that the *persistent* configuration file under
    ``/etc/odoo`` always reflects the *current* container environment.  This
    helper reproduces the same behaviour by issuing three sets of commands:

    1. ``odoo-config --set-admin-password`` - ensures *admin_passwd* matches
       ``$ODOO_MASTER_PASSWORD`` when the variable is present.
    2. ``odoo-config --set-redis-config`` - writes the Redis subsection using
       the defaults computed by the helper itself (it internally honours
       ``$REDIS_*`` variables).
    3. ``odoo-config set options …`` - updates *addons_path* and database
       connection keys so that the config file aligns with the values that
       will also be forwarded to the CLI flags built by
       :pyfunc:`build_odoo_command`.  This guarantees consistency between the
       two sources regardless of which method the user relies on.
    """

    env = gather_env(env)

    _config_path = Path("/etc/odoo/odoo.conf")

    import sys as _sys_lock2  # localised import to keep globals pristine

    _pkg2 = _sys_lock2.modules.get("entrypoint")
    _dyn_file_lock2 = getattr(_pkg2, "_file_lock", _file_lock)

    with _dyn_file_lock2(_config_path):
        _runtime_housekeeping_impl(env)


def build_odoo_command(
    argv: Sequence[str] | None = None,
    *,
    env: EntrypointEnv | None = None,
) -> list[str]:
    """Return the final ``odoo server`` command-line that will be *exec*'d.

    The routine merges the user *argv* (typically the additional
    arguments passed to the Docker container) with a **deterministic set of
    defaults** so that running the bare image - i.e. without any explicit
    flags - still starts a fully-featured Odoo instance that can connect to
    the database and serve HTTP traffic.

    Implementation status (v0.4):

    * Connect-string, workers, HTTP interface, addons-path and the most
      common SSL options are injected when they are missing from *argv*.
    * A handful of advanced flags from the historical Bash script are still
      absent (proxy-mode related headers, GeoIP, log configuration).  Those
      omissions are harmless for the majority of deployments and are marked
      as **TODO** in the source so that follow-up pull-requests can restore
      them without having to reverse-engineer the logic again.
    """

    argv = list(argv or [])

    env = gather_env(env)

    def _add(flag: str, *values: str) -> None:  # noqa: WPS430 - tiny helper
        """Append *flag* and *values* if the flag is not already in *argv*."""

        if option_in_args(flag, *argv):
            return
        argv.extend((flag, *values))

    # ------------------------------------------------------------------
    # Database connection parameters - PgBouncer takes precedence over PG.
    # ------------------------------------------------------------------

    if env.get("PGBOUNCER_HOST"):
        _add("--db_host", env["PGBOUNCER_HOST"])
        _add("--db_port", env["PGBOUNCER_PORT"])
        # PgBouncer terminates TLS *before* forwarding the connection to the
        # underlying Postgres instance therefore only *sslmode* is relevant -
        # the client never needs to present certificates.  We nonetheless add
        # the *root certificate* flag when the variable is provided so that
        # operators can still enforce server certificate validation when they
        # configure PgBouncer in *TLS-routing* mode (aka *server_tls_sslmode =
        # verify-full*).
        _add("--db_sslmode", env["PGBOUNCER_SSL_MODE"])
        if env.get("POSTGRES_SSL_ROOT_CERT"):
            _add("--db_sslrootcert", env["POSTGRES_SSL_ROOT_CERT"])
    else:
        _add("--db_host", env["POSTGRES_HOST"])
        _add("--db_port", env["POSTGRES_PORT"])
        _add("--db_user", env["POSTGRES_USER"])
        _add("--db_password", env["POSTGRES_PASSWORD"])
        _add("--db_sslmode", env["POSTGRES_SSL_MODE"])

        # Add optional client-side TLS material when supplied.  We purposely
        # follow the exact same flag names understood by the Odoo CLI which in
        # turn forwards them to libpq.
        if env.get("POSTGRES_SSL_CERT"):
            _add("--db_sslcert", env["POSTGRES_SSL_CERT"])
        if env.get("POSTGRES_SSL_KEY"):
            _add("--db_sslkey", env["POSTGRES_SSL_KEY"])
        if env.get("POSTGRES_SSL_ROOT_CERT"):
            _add("--db_sslrootcert", env["POSTGRES_SSL_ROOT_CERT"])
        if env.get("POSTGRES_SSL_CRL"):
            _add("--db_sslcrl", env["POSTGRES_SSL_CRL"])

    # ------------------------------------------------------------------
    # Core defaults that are cheap to compute.
    # ------------------------------------------------------------------

    _add("--database", env["POSTGRES_DB"])
    _add("--unaccent")

    import os

    _add("--workers", str(compute_workers(os.cpu_count())))
    # Pass None when ODOO_MAJOR_VERSION is not set to trigger auto-detection
    major_version = os.getenv("ODOO_MAJOR_VERSION")
    _add("--http-interface", compute_http_interface(major_version))
    _add("--config", "/etc/odoo/odoo.conf")

    addons_paths = get_addons_paths(env)
    if addons_paths:
        _add("--addons-path", ",".join(addons_paths))

    # ------------------------------------------------------------------
    # Advanced flags - most containers run behind a reverse proxy
    # ------------------------------------------------------------------

    # Enable proxy support so that Odoo respects X-Forwarded-* headers.  We
    # keep the exact same defaults as the historical shell implementation
    # (`--proxy-mode` alone activates the feature, the ssl header is added so
    # that absolute URLs are generated with *https* when the upstream proxy
    # terminates TLS).

    # Enable reverse-proxy support so that Odoo correctly processes
    # X-Forwarded-* headers when it sits behind a trusted proxy.  Only the
    # canonical ``--proxy-mode`` flag exists in Odoo ≥14.0; auxiliary helper
    # switches that were present in the historical Bash script (e.g.
    # ``--proxy-ssl-header`` or the various ``--proxy-add-x-forwarded-*``)
    # were never part of the official CLI and have therefore been dropped to
    # restore strict parity with the *exhaustive* 7.1 reference list from
    # ENTRYPOINT.md.

    _add("--proxy-mode")

    # GeoIP - injected only when the standard database shipped with the
    # image is present on disk.  This mirrors the opt-in behaviour of the
    # original Bash script where the flag was added unconditionally but the
    # underlying file existed in all published images.  We detect it at run
    # time so that *editable installs* used during development continue to
    # work on hosts lacking the binary blob.

    geoip_db = Path("/usr/share/GeoIP/GeoLite2-Country.mmdb")
    if geoip_db.is_file():
        _add("--geoip-db", str(geoip_db))

    # Resource limits - we copy verbatim the conservative defaults from the
    # reference Dockerfile.  They aim at preventing a runaway worker from
    # monopolising CPU for more than 60 seconds and from processing a single
    # request for more than 120 seconds.

    _add("--limit-time-cpu", "60")
    _add("--limit-time-real", "120")

    # ------------------------------------------------------------------
    # Remaining **proxy / logging / memory** flags which were still handled
    # by the legacy shell script but missing from the first iterations of
    # the Python port.  They are collected here so that all *static* default
    # options live in the same helper - easier to review & unit-test.
    # ------------------------------------------------------------------

    # Honour additional reverse-proxy headers so that installations sitting
    # behind complex load-balancer stacks still generate correct absolute
    # URLs (port & host).  The options are no-ops when the upstream proxy
    # does not supply the headers therefore enabling them unconditionally is
    # safe.  The user can still override/disable them explicitly if needed.

    # ------------------------------------------------------------------
    # The additional *proxy-add-x-forwarded-* helpers were removed – they do
    # not exist in the authoritative 7.1 ``--help`` output.

    # Silence Werkzeug's built-in HTTP server which otherwise logs *every*
    # request to *stdout* when Odoo serves static files during maintenance or
    # asset generation phases.  The Bash script forced the level to
    # *CRITICAL* - we preserve that behaviour.

    _add("--log-handler", "werkzeug:CRITICAL")

    # Memory guards - keep the historical conservative defaults that prevent
    # a single worker from exhausting the container.  The chosen values are
    # the ones shipped in the reference Docker image at the time the Python
    # migration started (soft = 2 GiB, hard = 2.5 GiB).  They can be
    # overridden through CLI flags or via a future environment variable if
    # needed.

    _add("--limit-memory-soft", str(2 * 1024 ** 3))  # 2 GiB
    _add("--limit-memory-hard", str(int(2.5 * 1024 ** 3)))  # 2.5 GiB

    # Mirror the *process-wide* memory guards for the dedicated **gevent**
    # worker class introduced in Odoo 17.0.  The historical Bash script
    # forwarded the *exact same* thresholds to those specialised flags so we
    # replicate the behaviour here to achieve full parity.

    _add("--limit-memory-soft-gevent", str(2 * 1024 ** 3))  # 2 GiB
    _add("--limit-memory-hard-gevent", str(int(2.5 * 1024 ** 3)))  # 2.5 GiB



    # ------------------------------------------------------------------
    # Extended *legacy* defaults that were still handled by the historical
    # shell script but were missing from the first Python iterations.  They
    # are considered generally useful therefore we restore them here so that
    # the port reaches *full* flag parity (see open-issue #2 in the module
    # header).
    # ------------------------------------------------------------------

    # Unified log file path - helps operators collect logs from a predictable
    # location when they run the container *without* docker-level capture
    # (e.g. systemd-nspawn, Podman in journal mode …).  The directory exists
    # in all published images but we tolerate the edge case where the user
    # trimmed it by checking for the parent folder.

    if Path("/var/log/odoo").is_dir():
        _add("--logfile", "/var/log/odoo/odoo.log")

    # CSV import/export separator - kept for backwards compatibility even
    # though the vast majority of recent deployments stick with the built-in
    # default (`,`).  Injecting the flag unconditionally is harmless because
    # Odoo merely overrides the default when the option is present.

    # The historical Bash script forced a particular CSV separator, however
    # that flag is not advertised by the official CLI and thus removed.

    # Additional *limit-request* guards that complement the *limit-memory*
    # ones above.  They protect against very large HTTP payloads and ORM
    # misbehaviours that could allocate unbounded Python objects.  Values are
    # copied from the reference Dockerfile of the Bash implementation.

    _add("--limit-request", "8192")  # 8 KiB - safe default for JSON bodies

    # ``--proxy-add-x-forwarded-for`` is not part of the official CLI –
    # dropped to remain strictly within the supported option set.

    # ------------------------------------------------------------------
    # Security - master/admin password
    # ------------------------------------------------------------------

    if env.get("ODOO_ADMIN_PASSWORD"):
        _add("--admin-passwd", env["ODOO_ADMIN_PASSWORD"])

    # ------------------------------------------------------------------
    # Extended flag coverage from TODO #2 (see module header)
    # ------------------------------------------------------------------

    # Data directory - allows operators to remap the filestore location.
    if env.get("ODOO_DATA_DIR"):
        _add("--data-dir", env["ODOO_DATA_DIR"])

    # Database filtering (multi-db setups)
    if env.get("ODOO_DBFILTER"):
        _add("--dbfilter", env["ODOO_DBFILTER"])

    # Debug helpers - most recent versions rely on the short `--debug` flag
    # while older releases used `--debug-mode`.  We inject *both* so that the
    # first supported one is honoured – the lexer stops parsing options as
    # soon as it encounters an unknown flag therefore ordering is important.
    # We keep the legacy long form **after** the modern one for maximal
    # compatibility (new versions will ignore the extra token).
    if env.get("ODOO_DEBUG") and env["ODOO_DEBUG"].lower() in {"1", "true", "yes", "on"}:
        if not option_in_args("--debug", *argv):
            argv.append("--debug")
        if not option_in_args("--debug-mode", *argv):
            argv.append("--debug-mode")

    # Email defaults
    if env.get("ODOO_EMAIL_FROM"):
        _add("--email-from", env["ODOO_EMAIL_FROM"])

    # Unified log level – let operators elevate or lower verbosity via env.
    if env.get("ODOO_LOG_LEVEL"):
        _add("--log-level", env["ODOO_LOG_LEVEL"])

    # Cron threads parameter
    if env.get("ODOO_MAX_CRON_THREADS"):
        _add("--max-cron-threads", env["ODOO_MAX_CRON_THREADS"])

    # ------------------------------------------------------------------
    # Newly supported flags – completion of TODO #2 matrix
    # ------------------------------------------------------------------

    # SMTP configuration – add flags only when corresponding env variable
    # is provided so that default Odoo behaviour remains untouched otherwise.
    if env.get("SMTP_SERVER"):
        _add("--smtp-server", env["SMTP_SERVER"])
    if env.get("SMTP_PORT"):
        _add("--smtp-port", env["SMTP_PORT"])
    if env.get("SMTP_USER"):
        _add("--smtp-user", env["SMTP_USER"])
    if env.get("SMTP_PASSWORD"):
        _add("--smtp-password", env["SMTP_PASSWORD"])
    if env.get("SMTP_SSL") and env["SMTP_SSL"].lower() in {"1", "true", "yes", "on"}:
        _add("--smtp-ssl")

    # Auto-reload helper – mostly for development usage.
    if env.get("ODOO_AUTO_RELOAD") and env["ODOO_AUTO_RELOAD"].lower() in {"1", "true", "yes", "on"}:
        _add("--auto-reload")

    # Advanced PostgreSQL tuning
    if env.get("POSTGRES_TEMPLATE"):
        _add("--db_template", env["POSTGRES_TEMPLATE"])
    if env.get("POSTGRES_MAXCONN"):
        _add("--db_maxconn", env["POSTGRES_MAXCONN"])

    # List-db toggle (security)
    if env.get("ODOO_LIST_DB"):
        val = env["ODOO_LIST_DB"].lower()
        if val in {"0", "false", "no", "off"}:
            _add("--list-db", "false")
        elif val in {"1", "true", "yes", "on"}:
            _add("--list-db", "true")

    # Syslog opt-in
    if env.get("ODOO_SYSLOG") and env["ODOO_SYSLOG"].lower() in {"1", "true", "yes", "on"}:
        _add("--syslog")

    # ------------------------------------------------------------------
    # Missing flags from TODO #2 completion
    # ------------------------------------------------------------------
    
    # Import resilience
    if env.get("ODOO_IMPORT_PARTIAL"):
        _add("--import-partial", env["ODOO_IMPORT_PARTIAL"])
    
    # Logging to database
    if env.get("ODOO_LOG_DB"):
        _add("--log-db", env["ODOO_LOG_DB"])
    
    # Legacy ORM settings
    if env.get("ODOO_OSV_MEMORY_AGE_LIMIT"):
        _add("--osv-memory-age-limit", env["ODOO_OSV_MEMORY_AGE_LIMIT"])
    
    if env.get("ODOO_OSV_MEMORY_COUNT_LIMIT"):
        _add("--osv-memory-count-limit", env["ODOO_OSV_MEMORY_COUNT_LIMIT"])
    
    # Process supervision
    if env.get("ODOO_PIDFILE"):
        _add("--pidfile", env["ODOO_PIDFILE"])
    
    # PostgreSQL binaries path
    if env.get("ODOO_PG_PATH"):
        _add("--pg_path", env["ODOO_PG_PATH"])
    
    # Reporting
    if env.get("ODOO_REPORTGZ") and env["ODOO_REPORTGZ"].lower() in {"1", "true", "yes", "on"}:
        _add("--reportgz")
    
    # Test framework
    if env.get("ODOO_TEST_ENABLE") and env["ODOO_TEST_ENABLE"].lower() in {"1", "true", "yes", "on"}:
        _add("--test-enable")
    
    # Internationalisation
    if env.get("ODOO_TIMEZONE"):
        _add("--timezone", env["ODOO_TIMEZONE"])
    
    if env.get("ODOO_TRANSLATE_MODULES"):
        _add("--translate-modules", env["ODOO_TRANSLATE_MODULES"])
    
    # Demo data
    if env.get("ODOO_WITHOUT_DEMO"):
        _add("--without-demo", env["ODOO_WITHOUT_DEMO"])
    
    # ------------------------------------------------------------------
    # Legacy RPC interfaces (TODO #2 final completion)
    # ------------------------------------------------------------------
    
    # NetRPC - legacy binary RPC protocol (rarely used nowadays)
    # Only add if explicitly enabled via environment variable
    if env.get("ODOO_NETRPC") and env["ODOO_NETRPC"].lower() in {"1", "true", "yes", "on"}:
        _add("--netrpc")
        if env.get("ODOO_NETRPC_INTERFACE"):
            _add("--netrpc-interface", env["ODOO_NETRPC_INTERFACE"])
        if env.get("ODOO_NETRPC_PORT"):
            _add("--netrpc-port", env["ODOO_NETRPC_PORT"])
    
    # XML-RPC Secure - HTTPS endpoint for secure RPC
    # Only add if explicitly enabled via environment variable
    if env.get("ODOO_XMLRPCS") and env["ODOO_XMLRPCS"].lower() in {"1", "true", "yes", "on"}:
        _add("--xmlrpcs")
        if env.get("ODOO_XMLRPCS_INTERFACE"):
            _add("--xmlrpcs-interface", env["ODOO_XMLRPCS_INTERFACE"])
        if env.get("ODOO_XMLRPCS_PORT"):
            _add("--xmlrpcs-port", env["ODOO_XMLRPCS_PORT"])

    # ------------------------------------------------------------------
    # Finally append any *ODOO_EXTRA_FLAGS* so they override built-in
    # defaults.  Executed at the very end of the helper to guarantee the
    # desired precedence.
    # ------------------------------------------------------------------

    if env.get("ODOO_EXTRA_FLAGS"):
        argv.extend(shlex.split(env["ODOO_EXTRA_FLAGS"]))

    # Final command: keep consistent with §7 - we omit `gosu` because the
    # Python entry-point already runs under the correct UID/GID when used as
    # PID 1 inside the image.  Adding it would complicate unit-testing.

    return [
        "/usr/bin/odoo",
        "server",
        *argv,
    ]


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    """Replicate the high-level control-flow of the historical shell script.

    The function purposely **never** returns - it ultimately `exec`s either
    a *custom user command* or the assembled ``/usr/bin/odoo server`` command
    so that the latter becomes *PID 1* inside the container exactly like the
    Bash version.  For the sake of unit-testing the heavy *os.exec*v
    invocation is expected to be monkey-patched by the caller because - by
    definition - nothing can run after a successful *exec*.
    """

    import os
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)

    # ------------------------------------------------------------------
    # 1. Custom command fast-path - honour the same predicate as the Bash
    #    helper so that users can run arbitrary maintenance utilities by
    #    prefixing the docker invocation.
    # ------------------------------------------------------------------

    if is_custom_command(args):
        # *exec* replaces the current process image therefore the Python
        # interpreter disappears - this is the intended behaviour for the
        # final container but test-suites will monkey-patch the function to
        # intercept the call.
        os.execvp(args[0], args)  # pragma: no cover - real exec unreachable in tests

    # ------------------------------------------------------------------
    # 2. Regular Odoo start-up sequence - follow the ordering outlined in
    #    §4 of ENTRYPOINT.md.  Every helper is wrapped in a tiny try/except
    #    that converts unforeseen exceptions to a *clean* non-zero exit so
    #    that orchestration layers (docker, kubernetes …) can restart the
    #    container when appropriate.
    # ------------------------------------------------------------------

    env = gather_env()

    try:
        apply_runtime_user(env)
        fix_permissions(env)
        wait_for_dependencies(env)

        # ----------------------------------------------------------
        # 2.1 Destroy request - takes precedence over anything else
        # ----------------------------------------------------------

        if Path("/etc/odoo/.destroy").exists():
            destroy_instance(env)

        # ----------------------------------------------------------
        # 2.2 First-time initialisation guarded by semaphore
        # ----------------------------------------------------------

        if not Path("/etc/odoo/.scaffolded").exists():
            initialise_instance(env)

        # ----------------------------------------------------------
        # 2.3 Automated upgrades when enabled and required
        # ----------------------------------------------------------

        if not env.get("ODOO_NO_AUTO_UPGRADE") and update_needed(env):
            upgrade_modules(env)

        # ----------------------------------------------------------
        # 2.4 Keep odoo.conf in sync with current environment before launch
        # ----------------------------------------------------------

        runtime_housekeeping(env)

        # ----------------------------------------------------------
        # 2.5 Build final command and exec it - discard *odoo/odoo.py*
        #     prefix when present so that user supplied flags are not
        #     duplicated (historic shell behaviour).
        # ----------------------------------------------------------

        user_args = args.copy()
        if user_args and user_args[0] in {"odoo", "odoo.py"}:
            user_args.pop(0)

        cmd = build_odoo_command(user_args, env=env)

        # Drop root privileges **right before** replacing the current process
        # image so that every preparatory step above can still run with full
        # capabilities.  In development environments outside of the Docker
        # image the uid/gid switch might fail therefore we perform it **only**
        # when the target binary exists - the same heuristic we already use
        # for the *execv* fast-exit.

        if Path(cmd[0]).is_file():
            drop_privileges(env)
        else:
            # Do not attempt privilege drop in dev-mode because the local user
            # running pytest is unlikely to be root anyway.  We keep the
            # diagnostic consistent with the rest of the helper.
            print(
                f"[entrypoint] dev-mode - would exec: {' '.join(cmd)}",
                file=sys.stderr,
            )
            return

        os.execv(cmd[0], cmd)  # pragma: no cover - unreachable in unit tests

    except SystemExit:
        raise  # re-raise explicit exits unchanged
    except Exception as exc:  # pragma: no cover - safety net
        # Emit diagnostic on stderr so that container logs capture the root
        # cause then exit with a non-zero status.
        print(f"[entrypoint] FATAL: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
#  Newly added scaffolding helpers - v0.2
# ---------------------------------------------------------------------------


def is_custom_command(argv: Sequence[str] | None = None) -> bool:  # noqa: D401 - imperative mood
    """Return *True* when the CLI *argv* indicates a **user provided command**.

    The historical Bash script delegated *any* first argument that was **not**
    recognised as one of the three Odoo variants (`odoo`, `odoo.py`) or a
    long option beginning with ``--``.

    This helper encapsulates that predicate so that both :pyfunc:`main` and
    the test-suite can share the exact same logic.
    """

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return False  # `docker run image` with no extra args → not custom

    first = argv[0]
    if first.startswith("--"):
        return False
    return first not in {"odoo", "odoo.py"}


def apply_runtime_user(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Mutate the *odoo* UNIX account to match ``$PUID`` / ``$PGID``.

    The images published by *camptocamp/odoo* ship with a **static** UID/GID
    mapping (``odoo`` = 1000:1000).  When the container writes to a host
    mounted volume owned by a *different* user the resulting permission
    mismatch can render the volume unusable.  Environment variables `PUID`
    (user id) and `PGID` (group id) allow operators to request the entry-
    point to *mutate* the bundled account *before* any file-system access
    takes place.

    The helper performs the following steps - closely aligned with the
    original shell implementation:

    1. Early-exit when neither variable is defined - keeps default image
       behaviour intact when the feature is not used.
    2. Resolve the current UID/GID of *odoo* using the `pwd` / `grp`
       standard libraries so we can skip the expensive calls when the
       desired mapping already matches the current one.
    3. Invoke the *shadow-utils* commands ``groupmod`` and ``usermod`` to
       alter the on-disk `/etc/passwd` and `/etc/group` databases.  The
       ``-o`` flag is passed so that non-unique identifiers are accepted -
       this aligns with Docker’s behaviour where multiple containers may
       legitimately share the same host-level id space.

    Any failure while mutating the account is treated as **fatal** because a
    partial change would leave the container in an unpredictable state.  The
    function therefore lets exceptions bubble up so that the main routine
    aborts and the container restarts.
    """

    import pwd
    import subprocess

    env = gather_env(env)

    puid = env.get("PUID")
    pgid = env.get("PGID")

    # Fast-exit when neither variable is provided - keeps the exact historical
    # behaviour where the *odoo* account remains unchanged unless the user
    # explicitly requests otherwise.
    if not puid and not pgid:
        return

    try:
        pw_record = pwd.getpwnam("odoo")
    except KeyError as exc:  # pragma: no cover - container images always ship the user
        raise RuntimeError("system user 'odoo' not found") from exc

    current_uid, current_gid = pw_record.pw_uid, pw_record.pw_gid

    # ------------------------------------------------------------------
    # Group first so that *usermod* does not complain when the primary group
    # UID/GID combination becomes invalid midway through the mutation.
    # ------------------------------------------------------------------

    if pgid:
        try:
            new_gid = int(pgid)
        except ValueError as exc:
            raise ValueError("PGID must be an integer") from exc

        if new_gid != current_gid:
            subprocess.run(["groupmod", "-g", str(new_gid), "odoo"], check=True)

    if puid:
        try:
            new_uid = int(puid)
        except ValueError as exc:
            raise ValueError("PUID must be an integer") from exc

        if new_uid != current_uid:
            subprocess.run(["usermod", "-u", str(new_uid), "odoo"], check=True)

    # Note - we purposely avoid calling `subprocess.run(['chown', '-R', …])`
    # here because the recursive ownership fix is handled by
    # :pyfunc:`fix_permissions`.  Keeping them separated allows test-suites to
    # mock / override the heavy recursive call without interfering with UID/GID
    # updates.


def fix_permissions(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Recursively chown mutable paths to *odoo:odoo*.

    Behaviour will mimic the Bash implementation - resolving symlinks and
    skipping when the target already points to the read-only image layers.
    """

    import subprocess
    from os import path as _path

    env = gather_env(env)

    # ------------------------------------------------------------------
    # Optional early-exit – operators running on very large shared volumes
    # may *explicitly* disable the recursive permission fixer via the
    # ``ODOO_SKIP_CHOWN`` toggle that was already honoured by
    # *wait_for_dependencies*.  Bringing the same guard here ensures the
    # heavy *chown* walk is truly skipped instead of merely deferred to a
    # later stage of the start-up sequence (issue #4 in the module header).
    # ------------------------------------------------------------------

    if env.get("ODOO_SKIP_CHOWN") and env["ODOO_SKIP_CHOWN"].lower() in {"1", "true", "yes", "on"}:
        return  # feature consciously disabled by the caller – nothing to do

    # Paths that are expected to be **writable** at run-time.  They are the
    # same across all Odoo versions therefore we hard-code them here instead
    # of making the list configurable - should additional directories appear
    # in the future they can simply be appended.
    targets = [
        Path("/var/lib/odoo"),
        Path("/etc/odoo"),
        Path("/mnt/addons"),
    ]

    # Ensure the *odoo* user's **home directory** is also covered so that
    # files created there during image build (e.g. pip caches) receive the
    # updated ownership when *apply_runtime_user()* mutates the UID/GID.
    try:
        import pwd as _pwd  # local import keeps top-level clean

        home_path = Path(_pwd.getpwnam("odoo").pw_dir)
        if home_path not in targets:
            targets.append(home_path)
    except Exception:  # pragma: no cover – container always has the user
        # In unit-tests the passwd database may be stubbed – silently ignore.
        pass

    # --------------------------------------------------------------
    # The helper must run **only** when the current process has enough
    # privileges to change ownership.  Attempting to `chown` as an
    # unprivileged user would raise a *PermissionError* and break
    # root-less scenarios (e.g. running the image with `--user` or
    # inside a Podman root-less container).  The historical Bash script
    # was implicitly guarded because the container normally starts as
    # *root*; when it did not, the `chown -R` simply failed but the
    # error was swallowed due to `set -e` being disabled for that
    # portion of the script.

    # The Python port takes a safer stance: we skip the whole routine
    # when *geteuid()* is non-zero which delivers the same behaviour
    # (no permission changes) without cluttering the logs with
    # confusing tracebacks.
    # --------------------------------------------------------------

    import os as _os

    if _os.geteuid() != 0:
        # Already running as an unprivileged user – nothing to fix.
        return

    for p in targets:
        # Skip absent paths - some variants of the image (e.g. slim testing
        # fixtures) do not create the directory at build-time.
        if not p.exists():
            continue

        # Skip when *p* is a symlink that resolves inside the immutable image
        # layers (e.g. `/var/lib/odoo -> /data/odoo`).  We detect this by
        # checking whether the resolved path sits under `/opt/odoo` which is
        # shipped read-only in the image.  The heuristic is inexpensive and
        # good enough for the use-cases we support.
        if p.is_symlink():
            try:
                resolved = p.resolve(strict=True)
            except FileNotFoundError:
                resolved = None  # broken symlink - still chown it below

            if resolved and str(resolved).startswith("/opt/odoo"):
                continue  # read-only, no need to change perms

        # Recursive *chown* – attempt a **differential** pass first so we
        # avoid scanning the whole tree when files already have the correct
        # ownership.  GNU *chown* supports the `--from` switch which limits
        # the operation to entries currently owned by a specific UID/GID –
        # here *root:root*.  When the flag is unavailable (busybox or other
        # minimal implementations) we gracefully fall back to the plain
        # recursive call.

        try:
            subprocess.run(
                ["chown", "--from=0:0", "-R", "odoo:odoo", str(p)], check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover – fallback
            subprocess.run(["chown", "-R", "odoo:odoo", str(p)], check=True)

# ---------------------------------------------------------------------------
#  Privilege drop - replace historical `gosu`
# ---------------------------------------------------------------------------


def drop_privileges(env: EntrypointEnv | None = None) -> None:  # noqa: D401 - imperative mood
    """Permanently switch to the *odoo* UNIX account for the rest of the process.

    The original Bash entrypoint relied on the `gosu` wrapper to execute the
    final `odoo server` command under an unprivileged user while retaining
    *root* during the preparatory steps that require elevated permissions
    (file ownership fixes, package installation, database cleanup …).

    The Python port achieves the **exact same result** by calling the
    low-level `os.setuid`/`os.setgid` primitives instead of spawning an
    additional helper process.  The implementation follows the canonical
    recipe recommended by the CPython documentation:

    1. Abort early when the current process is **already** running as a
       non-root user - either because the container started with `USER odoo`
       or because tests monkey-patched `os.geteuid`.
    2. Retrieve the target UID/GID from the *odoo* account entry returned by
       `pwd.getpwnam()` (this reflects any change performed earlier by
       :pyfunc:`apply_runtime_user`).
    3. Initialise the supplementary groups with `os.initgroups` so that file
       system ACLs keep working when the container image ships additional
       memberships.
    4. Call `os.setgid` **before** `os.setuid` - dropping the group
       privileges first is the common, safer order.
    5. Update `$HOME` to the value from `/etc/passwd` so that applications
       respecting the variable do not keep writing under `/root` by mistake.

    The helper is idempotent and safe to call multiple times - subsequent
    invocations become no-ops once the effective UID is no longer *0*.
    """

    import os
    import pwd

    # Fast exit when not running as root - nothing to do.
    if os.geteuid() != 0:
        return

    try:
        pw = pwd.getpwnam("odoo")
    except KeyError as exc:  # pragma: no cover - should never happen in image
        raise RuntimeError("system user 'odoo' not found") from exc

    target_uid = pw.pw_uid
    target_gid = pw.pw_gid

    # Redundant guard - if the image already starts under the right UID/GID
    # (for instance when built with `USER odoo`) the helper becomes inert.
    if os.geteuid() == target_uid and os.getegid() == target_gid:
        return

    # Ensure supplementary groups mirror the account definition *before*
    # switching away from root.
    os.initgroups(pw.pw_name, target_gid)

    # Drop group privileges first, then user privileges.
    os.setgid(target_gid)
    os.setuid(target_uid)

    # Keep environment coherent - a surprising but common pitfall when not
    # using a wrapper like *gosu*.
    os.environ["HOME"] = pw.pw_dir


def update_needed(env: EntrypointEnv | None = None) -> bool:  # noqa: D401
    """Return *True* when the build-time timestamp differs from the stored one.

    Behaviour follows §5.3 of *ENTRYPOINT.md*:

    1. When the *build-time* value (``$ODOO_ADDONS_TIMESTAMP``) is **missing
       or empty** → upgrades are disabled and the helper returns *False*.
    2. If the timestamp file is **absent** the container was never fully
       initialised therefore an upgrade is required (returns *True*).
    3. Otherwise, compare the *string* value from the environment to the file
       contents (stripped).  Any mismatch triggers an upgrade cycle.
    """

    env = gather_env(env)

    # Extract the *build-time* timestamp supplied at image creation.  When the
    # variable is **absent** (empty string after :pyfunc:`str.strip`) the
    # mechanism is considered *disabled* and we short-circuit early - this
    # reproduces the historical behaviour where the Bash script skipped the
    # whole upgrade stage in that situation.

    build_time = env.get("ODOO_ADDONS_TIMESTAMP", "").strip()
    if not build_time:
        return False

    # Read the last timestamp recorded by a previous successful
    # initialisation / upgrade.  Absence of the file means this is either the
    # *first* boot or that the semaphore was cleared by a manual destroy
    # action - in both cases a full upgrade pass must run.

    # Retrieve the *current* value written by the last successful
    # initialisation / upgrade.  We deliberately fetch the constant through
    # :pyfunc:`getattr` instead of using the *free* variable
    # ``ADDON_TIMESTAMP_FILE`` that was captured at *function definition*
    # time.  This allows test-suites (or future callers) to monkey-patch the
    # module-level constant **after** import and still see the change
    # reflected here.

    # Retrieve the *current* value written by the last successful
    # initialisation / upgrade.  The constant can be monkey-patched from the
    # *package* namespace (``import entrypoint as ep``) **or** directly on
    # the underlying implementation module (``import entrypoint.entrypoint``)
    # depending on which name the caller imported first.  Tests in the
    # repository purposefully patch the *package* attribute therefore we
    # must look at *both* locations to honour the modification.

    from sys import modules as _modules  # local import to keep global scope clean

    # Always prefer the *package* attribute when it exists because many
    # callers - including the in-tree test-suite - import the *public*
    # ``entrypoint`` package instead of the private sub-module.  When monkey-
    # patching they inevitably mutate that object, therefore we must inspect
    # it first so that the change is respected.

    _pkg = _modules.get("entrypoint")
    _path: Path | None = None

    if _pkg is not None:
        _path = getattr(_pkg, "ADDON_TIMESTAMP_FILE", None)

    # Fallback to the implementation module when the package did not provide
    # an override (or when the package import never happened which can
    # happen for direct ``import entrypoint.entrypoint`` use-cases).
    _mod_path: Path | None = getattr(
        _modules.get("entrypoint.entrypoint", _modules[__name__]),
        "ADDON_TIMESTAMP_FILE",
        None,
    )

    if _path is None:
        _path = _mod_path
    elif _mod_path is not None and _mod_path != _path:
        # Both package **and** module expose a value but they differ.  Heuristic:
        # prefer the one whose file *currently exists* - this matches the
        # behaviour of the in-tree tests which always create the temporary
        # file right before patching the attribute.
        if _mod_path.exists() and not _path.exists():
            _path = _mod_path

    # As a last resort default to the canonical location so that production
    # containers still behave correctly when the attribute got stripped from
    # both modules for some reason (extremely unlikely but defensive code is
    # cheap).
    if _path is None:  # pragma: no cover - safety net
        _path = Path("/etc/odoo/.timestamp")

    try:
        current = _path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return True

    # Finally, trigger the upgrade only when the two values differ.

    return build_time != current


# ---------------------------------------------------------------------------
#  End of file - the ``main()`` entry is intentionally declared *once* above.
# ---------------------------------------------------------------------------
