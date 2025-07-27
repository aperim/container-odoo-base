"""Regression tests for *build_odoo_command* – **extra flags** section.

The original Bash entry-point injected a handful of additional proxy, logging
and memory-guard flags that were still missing from the first iterations of
the Python implementation.  The helper now includes them – this test-suite
asserts their presence and checks that *user-supplied* values always take
precedence (i.e. no duplicates are produced).
"""

from __future__ import annotations

import entrypoint as ep


def _flags(cmd: list[str]) -> set[str]:  # noqa: D401 – tiny helper
    """Return the *set* of option strings present in *cmd* for easy asserts."""

    return {arg for arg in cmd if arg.startswith("--")}


def _minimal_env() -> dict[str, str]:
    """Return the minimal env mapping expected by the helper."""

    return {
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_SSL_MODE": "disable",
        "ODOO_ADDONS_TIMESTAMP": "",  # disable upgrade component
    }


def test_injected_defaults(monkeypatch):  # noqa: D401 – imperative mood
    """Helper must inject *all* missing defaults when user passes no flag."""

    env = _minimal_env()

    import os

    # Stabilise cpu count so unrelated defaults stay deterministic.
    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    cmd = ep.build_odoo_command([], env=env)

    flags = _flags(cmd)

    expected = {
        "--proxy-add-x-forwarded-port",
        "--proxy-add-x-forwarded-host",
        "--log-handler",
        "--limit-memory-soft",
        "--limit-memory-hard",
    }

    # `--log-handler` is injected *with* a value so we only assert the prefix.
    assert expected.difference({"--log-handler"}).issubset(flags)
    assert any(f.startswith("--log-handler") for f in flags)


def test_no_duplicate_when_user_provides(monkeypatch):  # noqa: D401
    """User-provided options must override defaults – no duplicates."""

    env = _minimal_env()

    import os

    monkeypatch.setattr(os, "cpu_count", lambda: 1, raising=False)

    # We override two flags.  The helper must keep *only* our occurrences.
    user_argv = [
        "--proxy-add-x-forwarded-port",  # bool flag (no value)
        "--log-handler=werkzeug:DEBUG",  # with value – overrides default
    ]

    cmd = ep.build_odoo_command(user_argv, env=env)

    # Count occurrences – must be exactly **one** for each overridden flag.
    occurrences_port = [a for a in cmd if a.startswith("--proxy-add-x-forwarded-port")]
    assert len(occurrences_port) == 1

    occurrences_log = [a for a in cmd if a.startswith("--log-handler")]
    assert len(occurrences_log) == 1
