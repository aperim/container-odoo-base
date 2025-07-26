"""Tests covering the *drop_privileges* helper.

The function manipulates low-level POSIX primitives.  We therefore monkeypatch
*os* and *pwd* so that the test-suite can verify the **intent** without
running with root capabilities on the host.
"""

from __future__ import annotations

from types import SimpleNamespace

from typing import List

import pytest

import entrypoint as ep


# ---------------------------------------------------------------------------
#  Fixtures / stubs
# ---------------------------------------------------------------------------


class _PwdRecord(SimpleNamespace):
    """Tiny substitute for the struct returned by ``pwd.getpwnam``."""


# ---------------------------------------------------------------------------
#  Test-cases
# ---------------------------------------------------------------------------


def test_drop_privileges_noop_when_already_unprivileged(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """The helper must return immediately when *geteuid* != 0."""

    import os

    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=True)

    # Guard against any accidental call to the dangerous syscalls.
    for name in ("initgroups", "setgid", "setuid"):
        monkeypatch.setattr(os, name, lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError()), raising=True)

    ep.drop_privileges({})  # should not raise


def test_drop_privileges_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """When run as root the helper must switch to the *odoo* account."""

    import os, pwd  # noqa: E401

    # Pretend we are root (uid 0).
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=True)
    monkeypatch.setattr(os, "getegid", lambda: 0, raising=True)

    # Fake passwd entry for *odoo*.
    pw = _PwdRecord(pw_uid=2000, pw_gid=3000, pw_name="odoo", pw_dir="/home/odoo")
    monkeypatch.setattr(pwd, "getpwnam", lambda _: pw, raising=True)

    calls: List[str] = []

    monkeypatch.setattr(os, "initgroups", lambda *a, **k: calls.append("initgroups"), raising=True)
    monkeypatch.setattr(os, "setgid", lambda gid: calls.append(f"setgid:{gid}"), raising=True)
    monkeypatch.setattr(os, "setuid", lambda uid: calls.append(f"setuid:{uid}"), raising=True)

    ep.drop_privileges({})

    # Expected exact sequence.
    assert calls == ["initgroups", "setgid:3000", "setuid:2000"]

    # $HOME must now reflect the odoo account.
    assert os.environ.get("HOME") == "/home/odoo"

