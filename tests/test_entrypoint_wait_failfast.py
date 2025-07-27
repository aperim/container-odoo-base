"""Additional tests for *wait_for_dependencies* fail-fast behaviour.

The helper was recently updated to **abort** when the Redis / Postgres
waiting utilities are missing in a production context.  The legacy,
permissive behaviour is still available when either *PYTEST_CURRENT_TEST*
or *ENTRYPOINT_DEV_MODE* is set.

This test-suite validates the *fail-fast* branch by clearing those escape
hatches and asserting that the function raises :class:`RuntimeError` when
the required helper modules cannot be imported.
"""

from __future__ import annotations

import importlib
import os
import sys
from types import ModuleType

import pytest


import entrypoint as ep


@pytest.fixture(autouse=True)
def _ensure_clean_helpers(monkeypatch: pytest.MonkeyPatch):  # noqa: D401 – fixture
    """Remove helper modules so that *wait_for_dependencies* cannot import them."""

    # Stash previous module references so we can restore them afterwards to
    # avoid side effects on unrelated test-modules executed later in the
    # session.
    previous: dict[str, ModuleType | None] = {}

    for mod in (
        "tools.src.lock_handler",
        "tools.src.wait_for_postgres",
    ):
        previous[mod] = sys.modules.pop(mod, None)  # remove if present

    # Invalidate caches so that subsequent *import_module* attempts really
    # trigger a fresh lookup and therefore raise *ModuleNotFoundError*.
    importlib.invalidate_caches()

    yield  # run the actual test

    # Restore prior state so other test-cases that monkey-patch those helpers
    # continue to work unaffected.
    for mod, val in previous.items():
        if val is not None:
            sys.modules[mod] = val


# ---------------------------------------------------------------------------
# Utility helper – force *import* to fail for the targeted helper modules so
# that the production branch inside *wait_for_dependencies* is exercised
# deterministically without hanging on real imports from the code-base.
# ---------------------------------------------------------------------------


def _patch_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401 – internal helper
    """Override *__import__* so that specific modules raise *ModuleNotFoundError*."""

    import builtins

    real_import = builtins.__import__  # keep reference to original builtin

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: D401 – nested stub
        if name in {"tools.src.lock_handler", "tools.src.wait_for_postgres"}:
            raise ModuleNotFoundError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


def test_wait_for_dependencies_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """Helper must raise when helper modules are missing in production mode."""

    # Simulate *production* by clearing the development heuristics.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("ENTRYPOINT_DEV_MODE", raising=False)

    _patch_import_failure(monkeypatch)

    with pytest.raises(RuntimeError):
        ep.wait_for_dependencies({})
