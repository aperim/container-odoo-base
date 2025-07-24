"""Tests for *build_odoo_command* newly added proxy/limit/geoip flags."""

from __future__ import annotations

from pathlib import Path

import entrypoint as ep


def _flags(cmd: list[str]) -> set[str]:  # noqa: D401 – tiny helper
    """Return the *set* of option strings contained in *cmd*."""

    return {arg for arg in cmd if arg.startswith("--")}


def _minimal_env() -> dict[str, str]:
    """Return the minimal env mapping required by the helper."""

    return {
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_SSL_MODE": "disable",
        "ODOO_ADDONS_TIMESTAMP": "",  # disable upgrade path for the test
    }


def test_build_cmd_injects_proxy_flags(monkeypatch):  # noqa: D401 – imperative mood
    env = _minimal_env()

    # Stabilise cpu count so that unrelated defaults are deterministic.
    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)

    flags = _flags(cmd)

    assert "--proxy-mode" in flags
    assert "--proxy-ssl-header" in flags


def test_build_cmd_no_duplicate_when_user_supplies(monkeypatch):  # noqa: D401
    env = _minimal_env()

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    # Provide our own value for proxy-mode so helper must not add another one.
    cmd = ep.build_odoo_command(["--proxy-mode"], env=env)

    occurrences = [arg for arg in cmd if arg == "--proxy-mode" or arg.startswith("--proxy-mode=")]

    # Only the one we supplied should remain.
    assert len(occurrences) == 1


def test_build_cmd_geoip_only_when_file_exists(monkeypatch, tmp_path):
    env = _minimal_env()

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    # Point the expected geoip path to our temp dir so we control presence.
    geoip_path = tmp_path / "GeoLite2-Country.mmdb"

    # We prepare two different fake implementations of Path.is_file so that
    # we can test both absence and presence scenarios.

    import sys

    ep_mod = sys.modules["entrypoint.entrypoint"]

    original_is_file = Path.is_file

    def fake_absent(self: Path) -> bool:  # noqa: D401
        if str(self) == "/usr/share/GeoIP/GeoLite2-Country.mmdb":
            return False
        return original_is_file(self)

    monkeypatch.setattr(ep_mod.Path, "is_file", fake_absent, raising=False)
    cmd = ep.build_odoo_command([], env=env)
    assert "--geoip-db" not in _flags(cmd)

    # Case 2 – file present → helper must inject flag with correct path.
    def fake_present(self: Path) -> bool:  # noqa: D401
        if str(self) == "/usr/share/GeoIP/GeoLite2-Country.mmdb":
            return True
        return original_is_file(self)

    monkeypatch.setattr(ep_mod.Path, "is_file", fake_present, raising=False)
    cmd = ep.build_odoo_command([], env=env)

    flags = _flags(cmd)
    assert "--geoip-db" in flags
