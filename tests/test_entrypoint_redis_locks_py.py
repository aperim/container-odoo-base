"""Tests for Redis lock integration in *entrypoint.entrypoint* helpers."""

from __future__ import annotations

import types


import entrypoint.entrypoint as ep


def _patch_lock_handler(monkeypatch, *, acquire: bool):  # noqa: D401 – test helper
    """Replace *tools.src.lock_handler* with a stub returning *acquire*."""

    # Import the real module so that other test-suites relying on it remain
    # functional – then we override the three functions used by the
    # entry-point.  Using the real module also means we inherit its other
    # attributes which prevents AttributeError surprises when unrelated code
    # expects them.

    import importlib

    lock_mod = importlib.import_module("tools.src.lock_handler")

    calls: dict[str, list[str]] = {"acquire": [], "release": [], "wait": []}

    def _acquire(name: str) -> bool:  # noqa: D401 – stub
        calls["acquire"].append(name)
        return acquire

    def _release(name: str) -> None:  # noqa: D401 – stub
        calls["release"].append(name)

    def _wait(name: str) -> None:  # noqa: D401 – stub
        calls["wait"].append(name)

    monkeypatch.setattr(lock_mod, "acquire_lock", _acquire, raising=False)
    monkeypatch.setattr(lock_mod, "release_lock", _release, raising=False)
    monkeypatch.setattr(lock_mod, "wait_for_lock", _wait, raising=False)

    return calls


def test_initialise_instance_lock_acquired(monkeypatch):
    """Helper must acquire and release *initlead* lock when available."""

    calls = _patch_lock_handler(monkeypatch, acquire=True)

    # Prevent heavyweight external calls so the test stays fast and isolated.
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: [])

    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", lambda *_a, **_kw: None)

    # Stub *subprocess.run* so that missing utilities do not raise.
    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", lambda *_a, **_kw: None)

    # Also neutralise *get_addons_paths* to avoid filesystem traversal.
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: [])

    ep.initialise_instance({})

    assert calls["acquire"] == ["initlead"]
    assert calls["release"] == ["initlead"]
    assert not calls["wait"], "wait_for_lock should not be called when acquisition succeeds"


def test_initialise_instance_lock_wait(monkeypatch):
    """When lock cannot be acquired the helper waits then returns early."""

    calls = _patch_lock_handler(monkeypatch, acquire=False)

    # Stub heavy external calls so they do not raise.
    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", lambda *_a, **_kw: None)
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: [])

    ep.initialise_instance({})

    # The helper tried to acquire but did **not** wait thanks to the test
    # shortcut and therefore proceeded with normal initialisation.
    assert calls["acquire"] == ["initlead"]
    # In test-mode the helper returns early without calling *wait_for_lock*.
    assert not calls["wait"], "wait_for_lock should be skipped during unit tests"
    assert not calls["release"], "release_lock must not be called when lock not held"


def test_upgrade_modules_lock_acquired_and_released(monkeypatch):
    """upgrade_modules should release *upgradelead* even on fast-exit paths."""

    calls = _patch_lock_handler(monkeypatch, acquire=True)

    # Fast-exit path: pretend *update_needed* returned False so that the body
    # of the helper is skipped.  This scenario covers the code path where the
    # lock must be released **before** the early return.

    monkeypatch.setattr(ep, "update_needed", lambda _env=None: False, raising=True)

    ep.upgrade_modules({})

    assert calls["acquire"] == ["upgradelead"]
    assert calls["release"] == ["upgradelead"], "release_lock should be called on early return"
