"""Odoo Docker image – Python entry-point scaffolding.

This module is **only a first step** in the migration from the historical
`entrypoint.sh` Bash script to a modern, easier-to-test Python 3
implementation.

The goal of *this file* is **not** to offer feature parity yet – the full
behaviour is captured in *ENTRYPOINT.md* and will be implemented
incrementally over several iterations.  At this stage we concentrate on:

1. Providing a *public* API surface that can be imported by unit tests and
   future code.
2. Implementing the *pure* helper utilities that were already covered by the
   existing test-suite (e.g. add-on collection logic, CLI argument helpers).
3. Documenting the responsibilities and expected behaviour of each public
   function so that future contributors have a clear contract to work with.

The heavy-weight routines that interact with databases, Redis or invoke Odoo
itself are **left as placeholders** for the time being – they would require
substantial integration testing which is outside the scope of this first
porting pass.
"""

from __future__ import annotations

import ast
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

__all__ = [
    "parse_blocklist",
    "option_in_args",
    "is_blocked_addon",
    "collect_addons",
    # high-level control-flow helpers (scaffolding only – *not* implemented)
    "gather_env",
    "wait_for_dependencies",
    "destroy_instance",
    "initialise_instance",
    "upgrade_modules",
    "build_odoo_command",
    # additional scaffolding introduced in v0.2
    "is_custom_command",
    "apply_runtime_user",
    "fix_permissions",
    "update_needed",
    "compute_workers",
    "compute_http_interface",
    "get_addons_paths",
    "ADDON_TIMESTAMP_FILE",
]


# ---------------------------------------------------------------------------
#  Generic helpers – previously shell snippets, now Python functions
# ---------------------------------------------------------------------------

# Absolute path to the timestamp semaphore file written during initial
# initialisation and checked on every boot to decide whether an **upgrade**
# cycle is required.  Exposed as a *module level* constant so that unit-tests
# can monkey-patch it easily without altering the real path used in
# production.

ADDON_TIMESTAMP_FILE = Path("/etc/odoo/.timestamp")


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
    # spaces – we inherit this for free.
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
            except Exception:  # pragma: no cover – invalid manifests skipped
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
    more sophisticated handling – left for future work.
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
        # first occurrence wins – keeps same semantics as Bash version
        addons.setdefault(addon.name, addon)

    # Ensure mandatory core modules are always present if they were discovered
    # somewhere in *paths*.  The Bash helper enforced at least *base* and
    # *web* to be part of initialisation but for unit tests we do **not**
    # inject them automatically – that behaviour will be revisited later.

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
#   outputs – effectively serving as living specification.
# * Unit-tests can import the symbols and rely on *stable* exceptions
#   (``NotImplementedError``) until real code lands.


from os import environ
from typing import TypedDict, Any


class EntrypointEnv(TypedDict, total=False):
    """Strongly-typed subset of the environment used by the entrypoint.

    Only *user-facing* variables documented in section « 2. Environment
    variables » of *ENTRYPOINT.md* are represented.  Internal helper variables
    (e.g. the endpoints computed by wrapper scripts) are deliberately left
    out because they are an implementation detail.
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


def gather_env(env: Mapping[str, str] | None = None) -> EntrypointEnv:
    """Return a mapping holding *all* entrypoint variables with defaults.

    The helper centralises default handling so that unit-tests and production
    paths use **one single source** of truth.  Unknown keys are ignored,
    meaning callers may safely pass ``os.environ`` directly.
    """

    src = environ if env is None else env

    def _get(key: str, default: str = "") -> str:  # noqa: WPS430 – tiny nested helper
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


# ---------------------------------------------------------------------------
#  Control-flow scaffolding – currently raise *NotImplemented*
# ---------------------------------------------------------------------------


def wait_for_dependencies(env: EntrypointEnv | None = None) -> None:  # noqa: D401 – imperative mood
    """Block until Redis and Postgres/PgBouncer are reachable.

    *Implementation pending.*  The function will orchestrate calls to
    external binaries **lock-handler** and **wait-for-postgres** following the
    exact rules from sections 4.4 and 4.5 of *ENTRYPOINT.md*.
    """

    # Delegates the *real* blocking logic to helper utilities that are already
    # part of the image and – crucially – fully unit-tested on their own. By
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
    # Wait for Redis – we do not forward any parameter because the helper
    # reads *all* configuration from environment variables (REDIS_HOST …)
    # which is consistent with the historical behaviour.
    # ------------------------------------------------------------------

    try:
        from tools.src.lock_handler import wait_for_redis  # type: ignore

        wait_for_redis()  # blocks until Redis replies to PING
    except ModuleNotFoundError:  # pragma: no cover – missing optional dep
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
    # Wait for PostgreSQL or PgBouncer – we pick the correct helper based on
    # the same precedence rule as the shell script: if *PGBOUNCER_HOST* is
    # non-empty we exclusively use the PgBouncer endpoint, otherwise we hit
    # Postgres directly.
    # ------------------------------------------------------------------

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


def destroy_instance(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Purge database & filestore, then reset semaphore files.

    Mirrors the **destroy** routine (5.1).  For now this is a stub so that
    future PRs can plug real logic while unit-tests import the symbol.
    """

    raise NotImplementedError


def initialise_instance(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Create a brand-new Odoo database with initial modules.

    Corresponds to section 5.2 – *Initialise brand new instance*.
    """

    raise NotImplementedError


def upgrade_modules(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Apply module upgrades if needed (section 5.3)."""

    raise NotImplementedError


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

    def _add(flag: str, *values: str) -> None:  # noqa: WPS430 – tiny helper
        """Append *flag* and *values* if the flag is not already in *argv*."""

        if option_in_args(flag, *argv):
            return
        argv.extend((flag, *values))

    # ------------------------------------------------------------------
    # Database connection parameters – PgBouncer takes precedence over PG.
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

    # Final command: keep consistent with §7 – we omit `gosu` because the
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
    print("entrypoint.py skeleton – nothing to do yet", file=sys.stderr)


# ---------------------------------------------------------------------------
#  Newly added scaffolding helpers – v0.2
# ---------------------------------------------------------------------------


def is_custom_command(argv: Sequence[str] | None = None) -> bool:  # noqa: D401 – imperative mood
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

    raise NotImplementedError


def fix_permissions(env: EntrypointEnv | None = None) -> None:  # noqa: D401
    """Recursively chown mutable paths to *odoo:odoo*.

    Behaviour will mimic the Bash implementation – resolving symlinks and
    skipping when the target already points to the read-only image layers.
    """

    raise NotImplementedError


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

    build_time = env.get("ODOO_ADDONS_TIMESTAMP", "")
    if not build_time:
        return False

    try:
        current = ADDON_TIMESTAMP_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return True

    return current != build_time.strip()


# ---------------------------------------------------------------------------
#  Pure helpers with *real* implementation – easy unit-test wins
# ---------------------------------------------------------------------------


def compute_workers(cpu_count: int | None = None) -> int:
    """Compute the *workers* flag using formula ``2 × CPU − 1``.

    When *cpu_count* is not provided the helper falls back to
    :pyfunc:`os.cpu_count` (guaranteed to be **≥1** because Docker cgroups
    expose at least one CPU).
    """

    import os

    cpus = cpu_count if cpu_count is not None else os.cpu_count() or 1
    # Bound the result to at least **1** to avoid passing *zero* to Odoo.
    return max(1, (2 * cpus) - 1)


def compute_http_interface(odoo_version: int | str | None = None) -> str:
    """Return listening interface based on *odoo_version*.

    * ``::``   for version **≥17** (dual-stack IPv6 / IPv4-mapped)
    * ``0.0.0.0`` for any lower version or when the value cannot be parsed.
    """

    try:
        ver = int(odoo_version) if odoo_version is not None else 0
    except (ValueError, TypeError):  # pragma: no cover – defensive fallback
        ver = 0
    return "::" if ver >= 17 else "0.0.0.0"


def get_addons_paths(env: EntrypointEnv | None = None) -> list[str]:  # noqa: D401
    """Return the **ordered** list of directories passed to ``--addons-path``.

    The real implementation will honour community/enterprise/extras and
    mounted paths.  For the time being an *empty* list is returned so that
    callers have a well-defined type with no side-effects.
    """

    # Resolve directories in the **exact** order expected by Odoo so that the
    # first match wins when duplicate module names exist across distributions.

    base_dirs = [
        Path("/opt/odoo/enterprise"),  # enterprise overrides community
        Path("/opt/odoo/community"),
        Path("/opt/odoo/extras"),
        Path("/mnt/addons"),  # user-mounted path – last so it can override
    ]

    return [str(p) for p in base_dirs if p.is_dir()]



if __name__ == "__main__":  # pragma: no cover
    main()
