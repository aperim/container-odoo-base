"""Tests covering *apply_runtime_user* and *fix_permissions* helpers.

The two helpers interact with system-level primitives (``pwd.getpwnam``,
``subprocess.run`` …).  We therefore rely on *monkeypatch* to intercept
those calls and assert the **intent** without requiring root privileges or
modifying the host where the tests execute.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import List

import pytest

import entrypoint as ep


# ---------------------------------------------------------------------------
#  apply_runtime_user
# ---------------------------------------------------------------------------


class _PwdRecord:  # minimal stub mimicking pwd struct
    def __init__(self, uid: int, gid: int):
        self.pw_uid = uid
        self.pw_gid = gid


def test_apply_runtime_user_noop(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401 – imperative name
    """When neither *PUID* nor *PGID* is set the helper must be a *no-op*."""

    called: List[List[str]] = []

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: called.append(cmd), raising=True)

    # Patch pwd.getpwnam so the helper does not hit the real system database.
    import pwd

    monkeypatch.setattr(pwd, "getpwnam", lambda _: _PwdRecord(1000, 1000), raising=True)

    ep.apply_runtime_user({})

    # No command should have been scheduled.
    assert called == []


def test_apply_runtime_user_modifies_uid_gid(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """Correct *usermod* / *groupmod* invocations are emitted when needed."""

    recorded: List[List[str]] = []

    import subprocess

    def _fake_run(cmd: List[str], **kwargs):  # noqa: D401 – small helper
        recorded.append(cmd)

    monkeypatch.setattr(subprocess, "run", _fake_run, raising=True)

    import pwd

    monkeypatch.setattr(pwd, "getpwnam", lambda _: _PwdRecord(1000, 1000), raising=True)

    env = {"PUID": "2000", "PGID": "3000"}

    ep.apply_runtime_user(env)

    # Group must be changed **first**.
    assert recorded == [
        ["groupmod", "-g", "3000", "odoo"],
        ["usermod", "-u", "2000", "odoo"],
    ]


# ---------------------------------------------------------------------------
#  fix_permissions
# ---------------------------------------------------------------------------


def test_fix_permissions_chown_invocations(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """The helper must call *chown -R* for every target that exists."""

    # Keep original *Path* methods so we can delegate when needed.
    import pathlib

    original_exists = pathlib.Path.exists
    original_is_symlink = pathlib.Path.is_symlink

    # The three default target directories.
    targets = {"/var/lib/odoo", "/etc/odoo", "/mnt/addons"}

    def fake_exists(self: Path) -> bool:  # noqa: D401 – small helper
        if str(self) in targets:
            return True
        return original_exists(self)

    def fake_is_symlink(self: Path) -> bool:  # noqa: D401 – small helper
        if str(self) in targets:
            return False  # pretend regular directory
        return original_is_symlink(self)

    monkeypatch.setattr(pathlib.Path, "exists", fake_exists, raising=False)
    monkeypatch.setattr(pathlib.Path, "is_symlink", fake_is_symlink, raising=False)

    recorded: List[List[str]] = []

    import subprocess

    def _fake_run(cmd: List[str], **kwargs):  # noqa: D401 – helper
        recorded.append(cmd)

    monkeypatch.setattr(subprocess, "run", _fake_run, raising=True)

    ep.fix_permissions({})

    expected = [["chown", "-R", "odoo:odoo", p] for p in sorted(targets)]

    # Order is not mandated, so we compare as *sets*.
    assert {tuple(cmd) for cmd in recorded} == {tuple(cmd) for cmd in expected}
