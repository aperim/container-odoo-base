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

# ---------------------------------------------------------------------------
#  Helpers – we inject dummy *psycopg2* and *redis* modules so that importing
#  the helper utilities from *tools.src* does not fail on systems where the
#  real native drivers are missing (CI pipeline, dev laptop, …).
# ---------------------------------------------------------------------------

from typing import Any, Dict

import sys
import types

# Stub modules *before* importing the entrypoint so that any transitive import
# performed at module initialisation time can safely resolve them.

if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")

    class _OpErr(Exception):
        """Stub for psycopg2.OperationalError."""

    def _connect(*_a: Any, **_kw: Any) -> object:  # noqa: D401 – stub
        return object()

    psycopg2_stub.OperationalError = _OpErr  # type: ignore[attr-defined]
    psycopg2_stub.connect = _connect  # type: ignore[attr-defined]
    sys.modules["psycopg2"] = psycopg2_stub


if "redis" not in sys.modules:
    redis_stub = types.ModuleType("redis")

    class _Redis:  # noqa: D101 – stub class
        _store: dict[str, str] = {}

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 – stub
            pass

        # Minimal subset of redis.Redis API used by lock_handler.py
        def ping(self) -> bool:  # noqa: D401 – stub
            return True

        def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool:  # noqa: D401 – stub
            if nx and name in self._store:
                return False
            self._store[name] = value
            return True

        def delete(self, name: str) -> int:  # noqa: D401 – stub
            return int(self._store.pop(name, None) is not None)

        def exists(self, name: str) -> bool:  # noqa: D401 – stub
            return name in self._store

    redis_stub.Redis = _Redis  # type: ignore[attr-defined]
    redis_stub.ConnectionError = Exception  # type: ignore[attr-defined]
    redis_stub.TimeoutError = Exception  # type: ignore[attr-defined]
    sys.modules["redis"] = redis_stub


import pytest

import entrypoint.entrypoint as ep


if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")

    class _OpErr(Exception):
        """Stub for psycopg2.OperationalError."""

    def _connect(*_a: Any, **_kw: Any) -> object:  # noqa: D401 – stub
        return object()

    psycopg2_stub.OperationalError = _OpErr  # type: ignore[attr-defined]
    psycopg2_stub.connect = _connect  # type: ignore[attr-defined]
    sys.modules["psycopg2"] = psycopg2_stub


if "redis" not in sys.modules:
    redis_stub = types.ModuleType("redis")

    class _Redis:  # noqa: D101 – stub class
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401 – stub
            pass

    redis_stub.Redis = _Redis  # type: ignore[attr-defined]
    redis_stub.ConnectionError = Exception  # type: ignore[attr-defined]
    redis_stub.TimeoutError = Exception  # type: ignore[attr-defined]
    sys.modules["redis"] = redis_stub


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
