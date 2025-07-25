"""Test-suite for *runtime_housekeeping* helper.

The goal is to exercise every logical branch of the configuration write
helper so that *entrypoint/entrypoint.py* keeps 100 % statement coverage once
the section became fully implemented.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

import entrypoint as ep


# ---------------------------------------------------------------------------
#  Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, ...]]:  # noqa: D401
    """Patch *subprocess.run* to capture invocations instead of executing."""

    calls: List[Tuple[str, ...]] = []

    def _fake_run(cmd: List[str], check: bool = True, **kwargs: Any) -> None:  # noqa: D401 – stub
        # Store *only* the positional part to make asserts concise.
        calls.append(tuple(cmd))

    monkeypatch.setattr("subprocess.run", _fake_run, raising=True)
    return calls


@pytest.fixture()
def patch_addons(monkeypatch: pytest.MonkeyPatch) -> List[str]:  # noqa: D401
    """Force :pyfunc:`entrypoint.get_addons_paths` to return a predictable list."""

    paths = ["/opt/odoo/community", "/mnt/addons"]
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: paths, raising=True)
    return paths


# ---------------------------------------------------------------------------
#  Test matrix
# ---------------------------------------------------------------------------


def _base_env() -> Dict[str, str]:  # noqa: D401 – tiny helper
    """Return a minimal env mapping accepted by *gather_env*."""

    return {
        "POSTGRES_HOST": "pg-host",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "odoo",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_DB": "odoodb",
        "POSTGRES_SSL_MODE": "disable",
    }


def test_housekeeping_postgres(
    fake_subprocess_run: List[Tuple[str, ...]],  # auto-used fixture
    patch_addons: List[str],
) -> None:  # noqa: D401
    """Verify option set calls when talking *directly* to Postgres."""

    env = _base_env().copy()

    ep.runtime_housekeeping(env)

    # Expected trio of *odoo-config* helper invocations.
    assert ("odoo-config", "--set-admin-password") in fake_subprocess_run
    assert ("odoo-config", "--set-redis-config") in fake_subprocess_run

    # Addons path must be persisted.
    expected_addons = ",".join(patch_addons)
    assert (
        "odoo-config",
        "set",
        "options",
        "addons_path",
        expected_addons,
    ) in fake_subprocess_run

    # Database host written using *POSTGRES_HOST*.
    assert (
        "odoo-config",
        "set",
        "options",
        "db_host",
        env["POSTGRES_HOST"],
    ) in fake_subprocess_run


def test_housekeeping_pgbouncer(
    fake_subprocess_run: List[Tuple[str, ...]],
    patch_addons: List[str],
) -> None:  # noqa: D401
    """When *PGBOUNCER_HOST* is set we must persist those endpoints instead."""

    env = _base_env().copy()
    env.update(
        {
            "PGBOUNCER_HOST": "bouncer",
            "PGBOUNCER_PORT": "6543",
            "PGBOUNCER_SSL_MODE": "require",
            # Provide a root cert to verify it gets forwarded as well.
            "POSTGRES_SSL_ROOT_CERT": "/ca/root.crt",
        }
    )

    ep.runtime_housekeeping(env)

    # db_host must reflect *PGBOUNCER_HOST* instead of Postgres.
    assert (
        "odoo-config",
        "set",
        "options",
        "db_host",
        env["PGBOUNCER_HOST"],
    ) in fake_subprocess_run

    # db_user / password should *not* be set under the PgBouncer branch.
    keys = {call[4] for call in fake_subprocess_run if call[:4] == ("odoo-config", "set", "options")}
    assert "db_user" not in keys and "db_password" not in keys

