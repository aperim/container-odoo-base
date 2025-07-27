"""Tests for *fix_permissions* early-exit when *ODOO_SKIP_CHOWN* is set."""

from __future__ import annotations

import builtins
from types import SimpleNamespace

import entrypoint as ep


def test_skip_chown(monkeypatch):  # noqa: D401 – imperative mood
    """Ensure *fix_permissions* returns immediately when asked to skip."""

    # Pretend we run as *root* so the function does not bail out early.
    import os as _os

    monkeypatch.setattr(_os, "geteuid", lambda: 0, raising=False)

    # Provide a minimal *pwd.getpwnam* implementation so that *fix_permissions*
    # can resolve the *odoo* user's home directory without touching the real
    # system database.
    dummy_pw = SimpleNamespace(pw_dir="/home/odoo")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        ep, "pwd", SimpleNamespace(getpwnam=lambda _: dummy_pw),  # type: ignore[arg-type]
        raising=False,
    )

    # Intercept calls to *subprocess.run* so we can assert **no** command is
    # executed when the skip flag is active.
    calls: list[tuple[list[str], dict[str, object]]] = []

    def _fake_run(cmd, **kwargs):  # noqa: D401 – nested helper
        calls.append((cmd, kwargs))

    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", _fake_run, raising=False)

    # Trigger the helper with the opt-out environment variable.
    env = {"ODOO_SKIP_CHOWN": "yes"}
    ep.fix_permissions(env)

    # The function must have returned *before* issuing any system call.
    assert not calls
