"""Ensure :pyfunc:`entrypoint._file_lock` gracefully degrades on FS without flock().

Some distributed or network file-systems – notably GlusterFS, certain NFS
deployments or rclone mounts – do **not** support the `flock(2)` system call
and will raise ``OSError: [Errno 95] Operation not supported``.  The
entry-point must therefore fall back to a creation-based lock so that
semaphore guarantees remain intact even when advisory locks are unavailable.

This test monkey-patches :pyfunc:`fcntl.flock` so that it deterministically
fails with *ENOTSUP*.  The context-manager **must not** propagate the
exception – the code inside the *with* block has to execute exactly once.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import entrypoint as ep


def test_file_lock_fallback_enotsup(monkeypatch, tmp_path):  # noqa: D401
    """The fallback path must run when `flock` raises *ENOTSUP*."""

    # ------------------------------------------------------------------
    # 1. Arrange – patch *fcntl.flock* so that it always raises ENOTSUP.
    # ------------------------------------------------------------------

    fcntl = importlib.import_module("fcntl")  # noqa: WPS433 – runtime import

    def _raise_enotsup(fd: int, flag: int):  # noqa: D401, ANN001 – test helper
        raise OSError(95, "Operation not supported")

    monkeypatch.setattr(fcntl, "flock", _raise_enotsup, raising=True)

    # ------------------------------------------------------------------
    # 2. Act – enter the context and create a side-effect we can later assert.
    # ------------------------------------------------------------------

    lock_target = tmp_path / "dummy.txt"

    executed = False

    with ep._file_lock(lock_target):  # noqa: SLF001 – intentional private access
        executed = True

    # ------------------------------------------------------------------
    # 3. Assert – the body of the `with` must have run once and the sentinel
    #    file must have been cleaned-up afterwards (unlink in *finally*).
    # ------------------------------------------------------------------

    assert executed, "_file_lock did not execute the inner block on ENOTSUP"
    assert not (lock_target.with_suffix(".lock")).exists(), "lock file not cleaned-up"

