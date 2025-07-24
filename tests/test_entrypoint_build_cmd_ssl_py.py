"""Additional tests for *build_odoo_command* covering SSL flags support."""

from __future__ import annotations

import entrypoint as ep



def _flags_after(cmd: list[str]) -> set[str]:
    """Return the *set* of option strings present in *cmd* for easy asserts."""

    return {arg for arg in cmd if arg.startswith("--")}



def test_build_cmd_adds_postgres_ssl(monkeypatch):  # noqa: D401 – imperative mood
    """Helper must inject client-side TLS flags when env variables are set."""

    env = {
        # Minimal required PG vars
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_SSL_MODE": "require",
        # Optional TLS material
        "POSTGRES_SSL_CERT": "/tls/client.crt",
        "POSTGRES_SSL_KEY": "/tls/client.key",
        "POSTGRES_SSL_ROOT_CERT": "/tls/root.crt",
        "POSTGRES_SSL_CRL": "/tls/root.crl",
        # Disable upgrade component which is unrelated to this test
        "ODOO_ADDONS_TIMESTAMP": "",
    }

    # Stabilise CPU count so that the helper produces deterministic output.
    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command(argv=[], env=env)

    flags = _flags_after(cmd)

    # Basic ssl flags + optional extras must be present.
    expected = {
        "--db_sslmode",
        "--db_sslcert",
        "--db_sslkey",
        "--db_sslrootcert",
        "--db_sslcrl",
    }

    assert expected.issubset(flags)



def test_build_cmd_user_overrides_ssl(monkeypatch):  # noqa: D401 – imperative mood
    """User-provided flags must take precedence, no duplicates produced."""

    env = {
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_SSL_MODE": "require",
        "POSTGRES_SSL_CERT": "/tls/client.crt",
        # disable upgrade path
        "ODOO_ADDONS_TIMESTAMP": "",
    }

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    # Pass our own sslmode so helper must *not* add another one.
    cmd = ep.build_odoo_command(argv=["--db_sslmode", "verify-full"], env=env)

    # Only *one* occurrence of the flag allowed.
    occurrences = [arg for arg in cmd if arg == "--db_sslmode" or arg.startswith("--db_sslmode=")]

    assert len(occurrences) == 1



def test_build_cmd_pgbouncer_tls(monkeypatch):  # noqa: D401 – imperative mood
    """When PgBouncer is used the helper must inject only supported flags."""

    env = {
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",  # should be ignored in favour of pgbouncer
        "POSTGRES_PORT": "5432",
        "POSTGRES_SSL_ROOT_CERT": "/tls/root.crt",  # may be forwarded
        "PGBOUNCER_HOST": "pool",
        "PGBOUNCER_PORT": "6432",
        "PGBOUNCER_SSL_MODE": "require",
        "ODOO_ADDONS_TIMESTAMP": "",
    }

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)

    flags = _flags_after(cmd)

    # PgBouncer path should include host/port and sslmode flags.
    assert "--db_host" in flags and "--db_port" in flags
    assert "--db_sslmode" in flags

    # Client sslcert/key must *not* be present, only root cert may appear.
    for forbidden in ("--db_sslcert", "--db_sslkey"):
        assert forbidden not in flags
