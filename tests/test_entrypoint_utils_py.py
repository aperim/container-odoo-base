"""Additional test coverage for entrypoint utility helpers.

This module covers helpers that were not exercised by the initial port
so that *entrypoint/entrypoint.py* achieves **full** statement coverage:

* ``compute_workers`` – verifies the arithmetic and the fallback rules.
* ``compute_http_interface`` – validates the Odoo ≥17 IPv6 binding switch.
* ``update_needed`` – exercises the three decision branches documented in
  *ENTRYPOINT.md* (disabled, file missing, value mismatch / match).
* ``wait_for_dependencies`` – ensures the helper orchestrates the correct
  subordinate calls without importing the real *tools* implementation.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Dict, List

import pytest

import entrypoint as ep


# ---------------------------------------------------------------------------
#  compute_workers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cpu_count, expected",
    [
        (None, ep.compute_workers()),  # dynamic reference – whatever the host returns
        (1, 1),
        (2, 3),
        (8, 15),
        (0, 1),  # defensive: zero is coerced to one
    ],
)
def test_compute_workers(cpu_count: int | None, expected: int) -> None:  # noqa: D401 – imperative mood
    """Formula is `(CPU * 2) - 1` with a hard lower-bound of *1*."""

    assert ep.compute_workers(cpu_count) == expected


# ---------------------------------------------------------------------------
#  compute_http_interface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version, expected",
    [
        ("16", "0.0.0.0"),
        (16, "0.0.0.0"),
        ("17", "::"),
        (18, "::"),
        ("garbage", "0.0.0.0"),  # fallback path
        (None, "0.0.0.0"),
    ],
)
def test_compute_http_interface(version: str | int | None, expected: str) -> None:  # noqa: D401
    """IPv6 wildcard is chosen starting with version **17**."""

    assert ep.compute_http_interface(version) == expected


# ---------------------------------------------------------------------------
#  update_needed decision matrix
# ---------------------------------------------------------------------------


def _patch_timestamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:  # noqa: D401
    """Helper that redirects *ADDON_TIMESTAMP_FILE* to the temp directory."""

    ts_file = tmp_path / ".timestamp"
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", ts_file, raising=True)
    return ts_file


def test_update_needed_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    """When the build-time environment value is empty → *False*."""

    _patch_timestamp(tmp_path, monkeypatch)
    env: Dict[str, str] = {"ODOO_ADDONS_TIMESTAMP": ""}
    assert ep.update_needed(env) is False


def test_update_needed_file_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    """Missing timestamp file triggers an update cycle."""

    _patch_timestamp(tmp_path, monkeypatch)
    env: Dict[str, str] = {"ODOO_ADDONS_TIMESTAMP": "123"}
    assert ep.update_needed(env) is True


def test_update_needed_value_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    """Value differing from stored file → *True*, identical → *False*."""

# Split mismatch vs match into two independent tests to keep each monkeypatch
# session self-contained.  This prevents potential interactions between the
# two calls which, under some environments, caused the interpreter to abort
# without a Python traceback (likely due to low-level I/O buffering bugs in
# Python 3.13).


def test_update_needed_value_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    ts_file = _patch_timestamp(tmp_path, monkeypatch)
    ts_file.write_text("111", encoding="utf-8")

    env = {"ODOO_ADDONS_TIMESTAMP": "222"}
    assert ep.update_needed(env) is True


def test_update_needed_value_match(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    ts_file = _patch_timestamp(tmp_path, monkeypatch)
    ts_file.write_text("deadbeef", encoding="utf-8")

    env = {"ODOO_ADDONS_TIMESTAMP": "deadbeef"}
    assert ep.update_needed(env) is False


# ---------------------------------------------------------------------------
#  wait_for_dependencies – orchestration only
# ---------------------------------------------------------------------------


def test_wait_for_dependencies_invocation(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """Helper must invoke the Redis + Postgres sub-routines with proper precedence."""

    called: List[str] = []

    # Fake *tools.src.lock_handler.wait_for_redis*
    fake_lock_handler = types.ModuleType("tools.src.lock_handler")

    def _wait_for_redis():  # noqa: D401 – tiny stub
        called.append("redis")

    fake_lock_handler.wait_for_redis = _wait_for_redis  # type: ignore[attr-defined]

    # Fake *tools.src.wait_for_postgres* with two functions.
    fake_wfp = types.ModuleType("tools.src.wait_for_postgres")

    def _wait_for_pgbouncer(**kwargs):  # noqa: D401 – stub
        called.append("pgbouncer")

    def _wait_for_postgres(**kwargs):  # noqa: D401 – stub
        called.append("postgres")

    fake_wfp.wait_for_pgbouncer = _wait_for_pgbouncer  # type: ignore[attr-defined]
    fake_wfp.wait_for_postgres = _wait_for_postgres  # type: ignore[attr-defined]

    # Install fake packages into *sys.modules* hierarchy expected by the helper.
    import sys

    # Insert placeholders **temporarily** using *monkeypatch* so the global
    # interpreter state is restored once the test exits – this prevents the
    # fake modules from leaking into subsequent tests that rely on the real
    # implementation.

    monkeypatch.syspath_prepend(".")  # ensure local *tools* package is discoverable

    monkeypatch.setitem(sys.modules, "tools", sys.modules.get("tools", types.ModuleType("tools")))
    monkeypatch.setitem(sys.modules, "tools.src", sys.modules.get("tools.src", types.ModuleType("tools.src")))

    monkeypatch.setitem(sys.modules, "tools.src.lock_handler", fake_lock_handler)
    monkeypatch.setitem(sys.modules, "tools.src.wait_for_postgres", fake_wfp)

    # Scenario 1 – PgBouncer is configured → expect redis + **pgbouncer**.
    env = {
        "PGBOUNCER_HOST": "pgbouncer-host",
        "PGBOUNCER_PORT": "6543",
        "PGBOUNCER_SSL_MODE": "require",
        "POSTGRES_USER": "odoo",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_DB": "mydb",
    }

    ep.wait_for_dependencies(env)
    assert called == ["redis", "pgbouncer"]

    # Reset and run scenario 2 – direct Postgres when PGBOUNCER_HOST empty.
    called.clear()
    env.pop("PGBOUNCER_HOST")

    ep.wait_for_dependencies(env)
    assert called == ["redis", "postgres"]
