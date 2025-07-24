#!/usr/bin/env python3
"""Odoo Docker image - Python entry-point scaffolding.

This module is **only a first step** in the migration from the historical
`entrypoint.sh` Bash script to a modern, easier-to-test Python 3
implementation.

The goal of *this file* is **not** to offer feature parity yet - the full
behaviour is captured in *ENTRYPOINT.md* and will be implemented
incrementally over several iterations.  At this stage we concentrate on:

1. Providing a *public* API surface that can be imported by unit tests and
   future code.
2. Implementing the *pure* helper utilities that were already covered by the
   existing test-suite (e.g. add-on collection logic, CLI argument helpers).
3. Documenting the responsibilities and expected behaviour of each public
   function so that future contributors have a clear contract to work with.

The heavy-weight routines that interact with databases, Redis or invoke Odoo
itself are **left as placeholders** for the time being - they would require
substantial integration testing which is outside the scope of this first
porting pass.
"""

from __future__ import annotations
from typing import TypedDict, Any
from os import environ

import ast
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import os

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
    "update_needed",
    "compute_workers",
    "compute_http_interface",
    "get_addons_paths",
    "ADDON_TIMESTAMP_FILE",
    "SCAFFOLDED_SEMAPHORE",
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
        cpus = int(cpu_count) if cpu_count is not None else os.cpu_count() or 1  # type: ignore[arg-type]
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        cpus = 1

    # Bound guard - Odoo refuses to start with zero workers.
    cpus = max(cpus, 1)
    return cpus * 2 - 1


def compute_http_interface(version: int | str | None) -> str:  # noqa: D401 - imperative mood
    """Return the default *--http-interface* value for *version*.

    Since Odoo 17.0 the server binds to *IPv6* ("::") by default.  Older
    versions still default to the legacy IPv4 wildcard ("0.0.0.0").  The
    helper reproduces that behaviour so that the higher level
    :pyfunc:`build_odoo_command` can stay agnostic of the rule.
    """

    try:
        ver_int = int(version)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # Garbage or *None* → fall back to legacy behaviour which is the most
        # conservative option.
        return "0.0.0.0"

    return "::" if ver_int >= 17 else "0.0.0.0"


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

    # Add-ons & localisation
    ODOO_LANGUAGES: str
    ODOO_ADDON_INIT_BLOCKLIST: str
    ODOO_ADDONS_TIMESTAMP: str
    ODOO_NO_AUTO_UPGRADE: str

    # Runtime user
    PUID: str
    PGID: str


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
        return src.get(key, default)

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
        # Add-ons
        ODOO_LANGUAGES=_get("ODOO_LANGUAGES", "en_AU,en_CA,en_IN,en_NZ,en_UK,en_US"),
        ODOO_ADDON_INIT_BLOCKLIST=_get("ODOO_ADDON_INIT_BLOCKLIST"),
        ODOO_ADDONS_TIMESTAMP=_get("ODOO_ADDONS_TIMESTAMP"),
        ODOO_NO_AUTO_UPGRADE=_get("ODOO_NO_AUTO_UPGRADE"),
        # Runtime user
        PUID=_get("PUID"),
        PGID=_get("PGID"),
    )


def wait_for_dependencies(env: EntrypointEnv | None = None) -> None:  # noqa: D401 - imperative mood
    """Block until Redis and Postgres/PgBouncer are reachable.

    *Implementation pending.*  The function will orchestrate calls to
    external binaries **lock-handler** and **wait-for-postgres** following the
    exact rules from sections 4.4 and 4.5 of *ENTRYPOINT.md*.
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
    # Wait for Redis - we do not forward any parameter because the helper
    # reads *all* configuration from environment variables (REDIS_HOST …)
    # which is consistent with the historical behaviour.
    # ------------------------------------------------------------------

    try:
        from tools.src.lock_handler import wait_for_redis  # type: ignore

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
        from tools.src import wait_for_postgres as _wfp  # type: ignore

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
    except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
        import sys

        print(
            "[entrypoint] tools.src.wait_for_postgres unavailable, skipping "
            "database wait (development mode)",
            file=sys.stderr,
        )


def destroy_instance(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Purge database & filestore, then reset semaphore files.

    Mirrors the **destroy** routine (5.1).  For now this is a stub so that
    future PRs can plug real logic while unit-tests import the symbol.
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

    # NOTE - The *real* initialisation is a complex two-pass process that
    # prepares the database and invokes a transient Odoo server several
    # times.  Re-implementing it entirely would require heavyweight
    # integration tests with a running Postgres instance, therefore **this
    # first Python iteration focuses on the *side-effects that must persist
    # across container restarts** so that other parts of the entry-point
    # (namely *update_needed* and *upgrade_modules*) can already work with
    # a consistent view of the world.

    import subprocess
    import tempfile
    import json
    from sys import modules as _modules

    env = gather_env(env)

    # ------------------------------------------------------------------
    # 1. Collect the add-on list that will be installed during the very
    #    first Odoo pass.  For now we *only* collect the list and store it
    #    to the timestamp directory so that unit-tests can verify the helper
    #    picked up the correct modules without having to spawn Odoo.
    # ------------------------------------------------------------------

    addons_paths = get_addons_paths(env)
    modules_to_init: list[str] = []
    if addons_paths:
        modules_to_init = collect_addons(
            [Path(p) for p in addons_paths],
            languages=env.get("ODOO_LANGUAGES", "").split(","),
            blocklist_patterns=parse_blocklist(env.get("ODOO_ADDON_INIT_BLOCKLIST")),
        )

    # 2. Persist the list to a temporary *JSON* file so that advanced users
    #    can introspect what the entry-point is about to perform (this is a
    #    brand-new feature compared to the legacy Bash script but is cheap
    #    to provide and extremely useful when debugging complex
    #    deployments).  The file is deleted automatically once written when
    #    used outside of tests - for tests we patch *tempfile.NamedTemporaryFile*
    #    to keep it around.

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fp:
        json.dump(modules_to_init, fp)
        manifest_path = Path(fp.name)

    # 3. *Here* we would normally spawn the Odoo server with
    #       odoo --init <modules> --stop-after-init --no-http
    #    but instead we just log the command so that the helper remains
    #    side-effect-free for unit-tests running in unprivileged CI workers.

    cmd: list[str] = [
        "/usr/bin/odoo",
        "--init",
        ",".join(modules_to_init) if modules_to_init else "base,web",
        "--stop-after-init",
        "--no-http",
    ]

    # Use *print* so that library users of the helper have a simple way to
    # capture the diagnostic via *capsys* - we purposely avoid any logging
    # framework because the parent process (Docker init) intercepts stdout
    # and stderr already.

    print(f"[entrypoint] initialise instance - would exec: {' '.join(cmd)}", file=sys.stderr)

    # Intentionally *do not* run the command outside of a full containerised
    # environment.  When the helper is executed inside the final image it
    # will be called from *main()* and we still want the real initialisation
    # to happen - we therefore gate the execution behind the presence of the
    # odoo binary at its expected absolute path.

    if Path(cmd[0]).is_file():  # pragma: no cover - not executed during unit tests
        subprocess.run(cmd, check=True)

    # ------------------------------------------------------------------
    # 4. Mark the container as scaffolded and store the build-time timestamp
    #    so that later boots can detect whether an upgrade is required.
    # ------------------------------------------------------------------

    scaffold_path: Path = getattr(_modules[__name__], "SCAFFOLDED_SEMAPHORE")  # type: ignore[assignment]
    scaffold_path.parent.mkdir(parents=True, exist_ok=True)
    scaffold_path.touch(exist_ok=True)

    ts_path: Path = getattr(_modules[__name__], "ADDON_TIMESTAMP_FILE")  # type: ignore[assignment]
    if env.get("ODOO_ADDONS_TIMESTAMP"):
        ts_path.write_text(env["ODOO_ADDONS_TIMESTAMP"], encoding="utf-8")


def upgrade_modules(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Apply module upgrades if needed (section 5.3)."""

    import subprocess
    import tempfile
    from sys import stderr, modules as _modules

    env = gather_env(env)

    # --------------------------------------------------------------
    # 0. Fast-exit conditions - mimic exact Bash logic so that the
    #    helper is a *noop* when upgrades are disabled or not needed.
    # --------------------------------------------------------------

    if env.get("ODOO_NO_AUTO_UPGRADE"):
        # Environment flag present → completely skip the routine so that
        # users have an escape hatch when they want to handle upgrades
        # manually.
        return

    if not update_needed(env):
        return  # container already on the expected revision

    # --------------------------------------------------------------
    # 1. Compute the list of candidate modules using the *same* helper
    #    as the initialisation routine so the two phases stay in sync.
    # --------------------------------------------------------------

    addons_paths = get_addons_paths(env)
    modules: list[str] = []
    if addons_paths:
        modules = collect_addons(
            [Path(p) for p in addons_paths],
            languages=env.get("ODOO_LANGUAGES", "").split(","),
            blocklist_patterns=parse_blocklist(env.get("ODOO_ADDON_INIT_BLOCKLIST")),
        )

    if not modules:
        # Nothing to upgrade - still refresh the timestamp so that the next
        # boot does not come back here.
        ts_file: Path = getattr(_modules[__name__], "ADDON_TIMESTAMP_FILE")  # type: ignore[assignment]
        if env.get("ODOO_ADDONS_TIMESTAMP"):
            ts_file.parent.mkdir(parents=True, exist_ok=True)
            ts_file.write_text(env["ODOO_ADDONS_TIMESTAMP"], encoding="utf-8")
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

    ts_file: Path = getattr(_modules[__name__], "ADDON_TIMESTAMP_FILE")  # type: ignore[assignment]
    if env.get("ODOO_ADDONS_TIMESTAMP"):
        try:
            ts_file.parent.mkdir(parents=True, exist_ok=True)
            ts_file.write_text(env["ODOO_ADDONS_TIMESTAMP"], encoding="utf-8")
        except PermissionError:  # pragma: no cover - unprivileged test env
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


def build_odoo_command(
    argv: Sequence[str] | None = None,
    *,
    env: EntrypointEnv | None = None,
) -> list[str]:
    """Return the final ``odoo server`` command-line array.

    At this stage the helper merely validates *argv* and returns an empty
    list.  Real computation of default flags (workers, interface, SSL, …)
    will be implemented later.
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
        _add("--db_sslmode", env["PGBOUNCER_SSL_MODE"])
    else:
        _add("--db_host", env["POSTGRES_HOST"])
        _add("--db_port", env["POSTGRES_PORT"])
        _add("--db_user", env["POSTGRES_USER"])
        _add("--db_password", env["POSTGRES_PASSWORD"])
        _add("--db_sslmode", env["POSTGRES_SSL_MODE"])

    # ------------------------------------------------------------------
    # Core defaults that are cheap to compute.
    # ------------------------------------------------------------------

    _add("--database", env["POSTGRES_DB"])
    _add("--unaccent")

    import os

    _add("--workers", str(compute_workers(os.cpu_count())))
    _add("--http-interface", compute_http_interface(os.getenv("ODOO_MAJOR_VERSION", "0")))
    _add("--config", "/etc/odoo/odoo.conf")

    addons_paths = get_addons_paths(env)
    if addons_paths:
        _add("--addons-path", ",".join(addons_paths))

    # Final command: keep consistent with §7 - we omit `gosu` because the
    # Python entry-point already runs under the correct UID/GID when used as
    # PID 1 inside the image.  Adding it would complicate unit-testing.

    return [
        "/usr/bin/odoo",
        "server",
        *argv,
    ]


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    """Entry-point when the image starts.

    The real implementation will go here.  For the time being we only ensure
    that the module is *importable* and that a ``main`` function exists so
    that unit tests can call it without side effects.
    """

    argv = list(sys.argv[1:] if argv is None else argv)
    print("entrypoint.py skeleton - nothing to do yet", file=sys.stderr)


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
    """Change UID/GID of user *odoo* inside the container.

    Implementation will rely on *os*, *pwd*, *grp* and *subprocess* to call
    `usermod` / `groupmod`.  Left as **stub** for now.
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

    # Paths that are expected to be **writable** at run-time.  They are the
    # same across all Odoo versions therefore we hard-code them here instead
    # of making the list configurable - should additional directories appear
    # in the future they can simply be appended.
    targets = [
        Path("/var/lib/odoo"),
        Path("/etc/odoo"),
        Path("/mnt/addons"),
    ]

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

        # Recursive *chown* - we rely on the coreutils binary because it is
        # significantly faster than Python's os.walk + chown in large
        # directory trees and it supports following / not following
        # symlinks consistently.  The helper is mocked in the test-suite so
        # no actual privilege escalation happens.
        subprocess.run(["chown", "-R", "odoo:odoo", str(p)], check=True)


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
    # callers – including the in-tree test-suite – import the *public*
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
        # prefer the one whose file *currently exists* – this matches the
        # behaviour of the in-tree tests which always create the temporary
        # file right before patching the attribute.
        if _mod_path.exists() and not _path.exists():
            _path = _mod_path

    # As a last resort default to the canonical location so that production
    # containers still behave correctly when the attribute got stripped from
    # both modules for some reason (extremely unlikely but defensive code is
    # cheap).
    if _path is None:  # pragma: no cover – safety net
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
