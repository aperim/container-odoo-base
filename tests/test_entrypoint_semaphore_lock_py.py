"""Tests for the *flock* guard around semaphore & config writes.

The historical Bash entry-point serialised writes to critical files such as
``/etc/odoo/.timestamp`` and ``/etc/odoo/odoo.conf`` with an *exclusive*
flock.  The Python port re-implements the behaviour through the private
helpers :pyfunc:`entrypoint._guarded_write_text`, :pyfunc:`entrypoint._guarded_touch`
and the context-manager :pyfunc:`entrypoint._file_lock`.

This suite focuses on the correctness of the locking mechanism itself while
remaining **fully isolated** – no actual lock files under */etc* are created
so the tests can run under an un-privileged user inside CI.
"""

from __future__ import annotations

import contextlib
import importlib
from pathlib import Path
from types import ModuleType
from typing import List

import entrypoint as ep


def test_guarded_write_and_touch_use_flock(monkeypatch, tmp_path):  # noqa: D401
    """Both helpers must acquire then release an exclusive lock."""

    # ------------------------------------------------------------------
    # 1. Intercept *fcntl.flock* so we can assert the two expected calls.
    # ------------------------------------------------------------------

    calls: List[int] = []

    # Import the *real* fcntl module so we can access the constant values.
    fcntl: ModuleType = importlib.import_module("fcntl")  # noqa: WPS433 – runtime import

    def _fake_flock(fd: int, flag: int):  # noqa: D401
        # We are only interested in the *flag* argument – fd is OS-assigned.
        calls.append(flag)
        return 0

    monkeypatch.setattr(fcntl, "flock", _fake_flock, raising=True)

    # ------------------------------------------------------------------
    # 2. Exercise both public helpers.
    # ------------------------------------------------------------------

    target_file = tmp_path / "sample.txt"

    ep._guarded_touch(target_file)  # noqa: SLF001 – intentional access to private helper
    ep._guarded_write_text(target_file, "hello")  # noqa: SLF001 – intentional

    # ------------------------------------------------------------------
    # 3. Assertions – we expect the pattern [LOCK_EX, LOCK_UN] *twice*
    #    (once for each helper invocation).
    # ------------------------------------------------------------------

    expected = [fcntl.LOCK_EX, fcntl.LOCK_UN] * 2
    assert calls == expected, "helpers did not acquire & release the expected locks"


def test_runtime_housekeeping_acquires_lock(monkeypatch):  # noqa: D401
    """The high-level helper must also protect *odoo.conf* with a lock."""

    captured: List[Path] = []

    @contextlib.contextmanager  # type: ignore[misc]
    def _fake_lock(path: Path):  # noqa: D401
        captured.append(path)
        yield  # immediately release – we only care that it was called

    # Patch the *package* attribute so the implementation picks it up.
    monkeypatch.setattr(ep, "_file_lock", _fake_lock, raising=True)

    # Patch subprocess.run to a noop so we do not depend on external binaries.
    monkeypatch.setattr("subprocess.run", lambda *a, **k: 0, raising=True)

    # Minimal env accepted by gather_env.
    env = {
        "POSTGRES_HOST": "h",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "u",
        "POSTGRES_PASSWORD": "p",
        "POSTGRES_DB": "d",
        "POSTGRES_SSL_MODE": "disable",
    }

    ep.runtime_housekeeping(env)

    assert captured, "runtime_housekeeping did not invoke _file_lock"
    assert captured[0].name == "odoo.conf", "lock not taken on odoo.conf"
