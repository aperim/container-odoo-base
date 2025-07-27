"""Tests for newly supported flags added to *build_odoo_command* (TODO #2)."""

from __future__ import annotations

import entrypoint as ep


def _minimal_env() -> dict[str, str]:  # noqa: D401 – tiny helper
    """Return a minimal environment mapping accepted by *build_odoo_command*."""

    return {
        # Mandatory database variables so that helper does not fallback to defaults
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_SSL_MODE": "disable",
        # Avoid entering upgrade path during unit-tests
        "ODOO_ADDONS_TIMESTAMP": "",
    }


def _flags(cmd: list[str]) -> set[str]:  # noqa: D401 – tiny helper
    """Return the *set* of option strings contained in *cmd*."""

    return {arg for arg in cmd if arg.startswith("--")}


def test_data_dir_injection(monkeypatch):  # noqa: D401 – imperative mood
    env = _minimal_env()
    env["ODOO_DATA_DIR"] = "/mnt/data"

    # Stabilise cpu count so unrelated defaults are deterministic.
    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)
    flags = _flags(cmd)

    assert "--data-dir" in flags
    # Ensure the value follows the flag.
    idx = cmd.index("--data-dir")
    assert cmd[idx + 1] == "/mnt/data"


def test_dbfilter_injection(monkeypatch):  # noqa: D401
    env = _minimal_env()
    env["ODOO_DBFILTER"] = "%d$"

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)
    flags = _flags(cmd)
    assert "--dbfilter" in flags


def test_debug_flag(monkeypatch):  # noqa: D401
    env = _minimal_env()
    env["ODOO_DEBUG"] = "true"

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)

    # Either --debug or --debug-mode (or both) must be present.
    flags = _flags(cmd)
    assert "--debug" in flags or "--debug-mode" in flags


def test_email_from(monkeypatch):  # noqa: D401
    env = _minimal_env()
    env["ODOO_EMAIL_FROM"] = "no-reply@example.com"

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)
    flags = _flags(cmd)
    assert "--email-from" in flags


def test_log_level(monkeypatch):  # noqa: D401
    env = _minimal_env()
    env["ODOO_LOG_LEVEL"] = "debug"

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)
    flags = _flags(cmd)
    assert "--log-level" in flags


def test_max_cron_threads(monkeypatch):  # noqa: D401
    env = _minimal_env()
    env["ODOO_MAX_CRON_THREADS"] = "4"

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)
    flags = _flags(cmd)
    assert "--max-cron-threads" in flags

