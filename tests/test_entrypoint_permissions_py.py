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

    # Pretend we are running as *root* so the helper proceeds with the
    # permission fix routine.
    import os

    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=True)

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

    # Pretend we are running as *root* so the helper proceeds with chown.
    import os

    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=True)

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

    # We expect **at least one** invocation per target directory – either the
    # differential `--from=0:0` call or the plain recursive one depending on
    # platform support.  The exact flags are therefore not significant for
    # functional correctness.

    seen = {cmd[-1] for cmd in recorded if cmd and cmd[0] == "chown"}

    assert seen == targets


def test_fix_permissions_skipped_when_unprivileged(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """When executed as a non-root user the helper must *not* attempt chown."""

    # Pretend we are not running as root.
    import os

    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=True)

    called = False

    import subprocess

    def _fake_run(cmd, **kwargs):  # noqa: D401 – tiny stub
        nonlocal called
        called = True

    monkeypatch.setattr(subprocess, "run", _fake_run, raising=True)

    ep.fix_permissions({})

    assert called is False


# ---------------------------------------------------------------------------
#  New behaviours – home directory ownership + skip toggle
# ---------------------------------------------------------------------------


def _patch_pwd(monkeypatch: pytest.MonkeyPatch, home: str = "/opt/odoo") -> None:  # noqa: D401 – helper
    """Make *pwd.getpwnam* return a dummy record with *home* set."""

    import types

    record = types.SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir=home)

    import pwd

    monkeypatch.setattr(pwd, "getpwnam", lambda _: record, raising=True)


def test_fix_permissions_includes_home_dir(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """The helper must also adjust ownership of the *odoo* home directory."""

    # Run as *root* so chown triggers.
    import os

    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=True)

    # Stub passwd entry so the helper can resolve home directory.
    _patch_pwd(monkeypatch, home="/opt/odoo")

    # Make /opt/odoo exist and be a regular directory.
    import pathlib

    orig_exists = pathlib.Path.exists
    orig_is_symlink = pathlib.Path.is_symlink

    targets = {"/opt/odoo"}

    def fake_exists(self: pathlib.Path) -> bool:  # noqa: D401
        if str(self) in targets:
            return True
        return orig_exists(self)

    def fake_is_symlink(self: pathlib.Path) -> bool:  # noqa: D401
        if str(self) in targets:
            return False
        return orig_is_symlink(self)

    monkeypatch.setattr(pathlib.Path, "exists", fake_exists, raising=False)
    monkeypatch.setattr(pathlib.Path, "is_symlink", fake_is_symlink, raising=False)

    recorded = []

    import subprocess

    def _fake_run(cmd, **kwargs):  # noqa: D401
        recorded.append(cmd)

    monkeypatch.setattr(subprocess, "run", _fake_run, raising=True)

    ep.fix_permissions({})

    # Verify /opt/odoo was included in invocations.
    assert any(cmd[-1] == "/opt/odoo" for cmd in recorded)


def test_fix_permissions_skipped_via_env(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """Setting *ODOO_SKIP_CHOWN* disables the recursive chown."""

    import os

    # We would otherwise be root.
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=True)

    called = False

    import subprocess

    def _fake_run(cmd, **kwargs):  # noqa: D401
        nonlocal called
        called = True

    monkeypatch.setattr(subprocess, "run", _fake_run, raising=True)

    env = {"ODOO_SKIP_CHOWN": "true"}

    ep.fix_permissions(env)

    assert called is False
