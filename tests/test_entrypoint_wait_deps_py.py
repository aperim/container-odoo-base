"""Unit tests for entrypoint.wait_for_dependencies().

Only the *routing* logic belongs to the entry-point – the heavy-lifting is
delegated to helper utilities that already have their own dedicated test-
suite.  Here we therefore focus on ensuring that:

1. The correct helper (PostgreSQL vs PgBouncer) is invoked based on the
   content of the environment mapping.
2. Arguments are forwarded verbatim so that the entry-point does not alter
   semantics along the way.

Actual network connectivity is **not** exercised; the helper callables are
replaced by test doubles via *monkeypatch*.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

import entrypoint.entrypoint as ep


class _Recorder:  # noqa: D101 – minimal helper
    def __init__(self) -> None:  # noqa: D401 – imperative mood
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        self.calls.append((args, kwargs))


@pytest.fixture()
def env_base() -> Dict[str, str]:  # noqa: D103 – pytest fixture
    return {
        "POSTGRES_USER": "odoo",
        "POSTGRES_PASSWORD": "secret",
        "POSTGRES_HOST": "postgres.example",
        "POSTGRES_PORT": "5433",
        "POSTGRES_DB": "prod",
        "POSTGRES_SSL_MODE": "verify-full",
        "POSTGRES_SSL_CERT": "/cert.pem",
        "POSTGRES_SSL_KEY": "/key.pem",
        "POSTGRES_SSL_ROOT_CERT": "/ca.pem",
        "POSTGRES_SSL_CRL": "",
    }


def test_waits_for_postgres(monkeypatch: pytest.MonkeyPatch, env_base: dict[str, str]) -> None:  # noqa: D103
    redis_rec = _Recorder()
    pg_rec = _Recorder()

    monkeypatch.setattr("tools.src.lock_handler.wait_for_redis", redis_rec)
    monkeypatch.setattr("tools.src.wait_for_postgres.wait_for_postgres", pg_rec)
    # we patch PgBouncer helper to ensure it is *not* called
    monkeypatch.setattr("tools.src.wait_for_postgres.wait_for_pgbouncer", lambda *a, **k: (_ for _ in ()).throw(AssertionError))

    ep.wait_for_dependencies(env=env_base)

    # Redis helper always called once with no parameters
    assert len(redis_rec.calls) == 1
    assert redis_rec.calls[0] == ((), {})

    # PostgreSQL helper must be invoked with parameters mirroring *env_base*
    assert len(pg_rec.calls) == 1
    args, kwargs = pg_rec.calls[0]
    assert not args  # all named
    assert kwargs == {
        "user": "odoo",
        "password": "secret",
        "host": "postgres.example",
        "port": 5433,
        "dbname": "prod",
        "ssl_mode": "verify-full",
        "ssl_cert": "/cert.pem",
        "ssl_key": "/key.pem",
        "ssl_root_cert": "/ca.pem",
        "ssl_crl": None,
    }


def test_waits_for_pgbouncer(monkeypatch: pytest.MonkeyPatch, env_base: dict[str, str]) -> None:  # noqa: D103
    env: dict[str, str] = {
        **env_base,
        "PGBOUNCER_HOST": "pgbouncer.lan",
        "PGBOUNCER_PORT": "6543",
        "PGBOUNCER_SSL_MODE": "disable",
    }

    redis_rec = _Recorder()
    pgb_rec = _Recorder()

    monkeypatch.setattr("tools.src.lock_handler.wait_for_redis", redis_rec)
    monkeypatch.setattr("tools.src.wait_for_postgres.wait_for_pgbouncer", pgb_rec)
    # Ensure Postgres helper not called
    monkeypatch.setattr("tools.src.wait_for_postgres.wait_for_postgres", lambda *a, **k: (_ for _ in ()).throw(AssertionError))

    ep.wait_for_dependencies(env=env)

    assert len(redis_rec.calls) == 1
    assert len(pgb_rec.calls) == 1

    kwargs = pgb_rec.calls[0][1]
    assert kwargs == {
        "user": "odoo",
        "password": "secret",
        "host": "pgbouncer.lan",
        "port": 6543,
        "dbname": "prod",
        "ssl_mode": "disable",
    }

