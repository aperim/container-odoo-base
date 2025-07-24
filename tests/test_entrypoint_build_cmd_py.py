"""Tests for *build_odoo_command*, *get_addons_paths* and *update_needed*."""

from __future__ import annotations

from pathlib import Path

import entrypoint as ep


# ---------------------------------------------------------------------------
#  update_needed
# ---------------------------------------------------------------------------


def test_update_needed_when_file_missing(tmp_path, monkeypatch):
    env = {
        "ODOO_ADDONS_TIMESTAMP": "1234567890",
    }

    # Redirect the constant used by the helper to our temp dir.
    ts_file = tmp_path / ".timestamp"
    # Patch *inside* the real implementation module rather than the package
    # level re-export so that the helper picks up the overridden path.
    import sys

    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "ADDON_TIMESTAMP_FILE", ts_file, raising=False)

    assert ep.update_needed(env) is True


def test_update_needed_match_no_upgrade(tmp_path, monkeypatch):
    """When the *current* value matches the build-time timestamp no upgrade is needed."""

    env = {
        "ODOO_ADDONS_TIMESTAMP": "111",
    }

    ts_file = tmp_path / ".timestamp"
    ts_file.write_text("111", "utf-8")
    import sys
    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "ADDON_TIMESTAMP_FILE", ts_file, raising=False)

    assert ep.update_needed(env) is False


def test_update_needed_mismatch(tmp_path, monkeypatch):
    env = {
        "ODOO_ADDONS_TIMESTAMP": "222",
    }

    ts_file = tmp_path / ".timestamp"
    ts_file.write_text("333", "utf-8")
    import sys
    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "ADDON_TIMESTAMP_FILE", ts_file, raising=False)

    assert ep.update_needed(env) is True


# ---------------------------------------------------------------------------
#  Additional edge-case: mechanism disabled when env variable missing/empty
# ---------------------------------------------------------------------------


def test_update_needed_disabled_when_env_empty(monkeypatch):
    """An *empty* build-time timestamp must disable the upgrade mechanism."""

    env = {
        "ODOO_ADDONS_TIMESTAMP": " ",  # explicit blank value
    }

    # Even if the timestamp file is absent we expect *False* because the
    # mechanism is considered disabled.

    import sys
    monkeypatch.setattr(
        sys.modules["entrypoint.entrypoint"],
        "ADDON_TIMESTAMP_FILE",
        ep.ADDON_TIMESTAMP_FILE,
        raising=False,
    )

    assert ep.update_needed(env) is False


# ---------------------------------------------------------------------------
#  get_addons_paths
# ---------------------------------------------------------------------------


def test_get_addons_paths_order_and_filter(monkeypatch):
    # Pretend only *community* and *extras* dirs exist.
    present = {
        "/opt/odoo/community",
        "/opt/odoo/extras",
    }

    original_is_dir = Path.is_dir

    def fake_is_dir(self: Path) -> bool:  # noqa: D401
        if str(self) in present:
            return True
        return original_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", fake_is_dir, raising=False)

    paths = ep.get_addons_paths({})  # type: ignore[arg-type]

    # Expected order: enterprise, community, extras, mnt/addons, but enterprise
    # is absent so it should be skipped.
    assert paths == [
        "/opt/odoo/community",
        "/opt/odoo/extras",
    ]


# ---------------------------------------------------------------------------
#  build_odoo_command
# ---------------------------------------------------------------------------


def test_build_odoo_command_defaults(monkeypatch):
    env = {
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_SSL_MODE": "disable",
        # Provide a bogus Odoo version to force IPv6 path
        "ODOO_ADDONS_TIMESTAMP": "",
    }

    # Freeze CPU count to a deterministic value.
    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 2, raising=False)

    # Stub addons-path helper.
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: ["/opt/odoo/community"])

    cmd = ep.build_odoo_command(["--workers=99", "--some-arg"], env=env)

    # Flag --workers should be kept at user-provided value (no extra duplicate)
    assert any(arg.startswith("--workers=99") or arg == "--workers" for arg in cmd)
    assert "--database" in cmd and "db" in cmd
    # Database host defaults should be present
    assert "--db_host" in cmd and "pg" in cmd
# addon-path default injection is not implemented yet.
