"""Unit-tests for *destroy_instance* helper.

The routine is now fully implemented: it invokes *psql* twice, waits ten
seconds, removes the filestore directory and deletes semaphore files.  The
tests monkey-patch the heavy operations so that no real database nor root
privileges are required.
"""

from __future__ import annotations

import builtins
import types
from pathlib import Path
from typing import List

import entrypoint as ep


def test_destroy_instance_happy_path(monkeypatch, tmp_path):  # noqa: D401 – imperative test name
    """All side-effects must be carried out in the documented order."""

    executed: List[list[str]] = []

    # ------------------------------------------------------------------
    # 1. Capture *subprocess.run* invocations so we can assert the SQL.
    # ------------------------------------------------------------------

    import subprocess  # local import for monkeypatch target

    def fake_run(cmd, *a, **kw):  # noqa: D401, ANN001 – signature matches *subprocess.run*
        executed.append(cmd)
        if kw.get("check"):
            return types.SimpleNamespace(returncode=0)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run, raising=False)

    # ------------------------------------------------------------------
    # 2. Patch *time.sleep* to avoid waiting.
    # ------------------------------------------------------------------

    import time

    monkeypatch.setattr(time, "sleep", lambda s: None)

    # ------------------------------------------------------------------
    # 3. Capture *shutil.rmtree* – we just store the path argument.
    # ------------------------------------------------------------------

    removed_dirs: List[Path] = []

    import shutil

    monkeypatch.setattr(shutil, "rmtree", lambda p, ignore_errors=True: removed_dirs.append(p))

    # ------------------------------------------------------------------
    # 4. Intercept *Path.unlink* for the two semaphore files.
    # ------------------------------------------------------------------

    unlinked: List[Path] = []

    real_unlink = Path.unlink

    def fake_unlink(self: Path, *_, **__):  # noqa: D401 – mimic Path.unlink
        # Only record calls for our two semaphore files – fall back to the
        # real implementation for any other path so that *tmp_path* keeps
        # working as expected should the helper be extended in the future.
        if str(self) in {"/etc/odoo/.destroy", "/etc/odoo/.scaffolded"}:
            unlinked.append(self)
            return None
        return real_unlink(self)

    monkeypatch.setattr(Path, "unlink", fake_unlink, raising=False)

    # ------------------------------------------------------------------
    # 5. Provide a minimal env so we hit all branches.  We deliberately use
    #    a short database name to keep generated SQL easy to eyeball.
    # ------------------------------------------------------------------

    env = {
        "POSTGRES_DB": "mydb",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
    }

    ep.destroy_instance(env)

    # ------------------------------------------------------------------
    # 6. Assertions
    # ------------------------------------------------------------------

    # a) Two *psql* invocations executed in order.
    assert len(executed) == 2

    first, second = executed

    assert first[0] == "psql" and "pg_terminate_backend" in first[-1]
    assert second[0] == "psql" and "DROP DATABASE" in second[-1]

    # b) Filestore directory path matches expectation.
    expected_filestore = Path("/var/lib/odoo/filestore/mydb")
    assert removed_dirs == [expected_filestore]

    # c) Semaphore files were unlinked.
    assert {str(p) for p in unlinked} == {"/etc/odoo/.destroy", "/etc/odoo/.scaffolded"}
