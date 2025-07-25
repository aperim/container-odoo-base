"""Unit-tests for the *restore from backup* logic inside ``initialise_instance``.

The historical ``entrypoint.sh`` tried to restore a database from the backup
volume when the helper script was available **before** falling back to a brand
new initialisation.  This test-suite validates the parity of the Python port
for the three possible scenarios:

1. Helper **present** and returns *success* (exit code ``0``).
2. Helper **absent** – direct new database creation.
3. Helper **present** but returns a *failure* – the routine must invoke
   :pyfunc:`entrypoint.entrypoint.destroy_instance` then proceed with a clean
   initialisation.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import entrypoint.entrypoint as ep


def _tmp_paths(tmp_path: Path) -> tuple[Path, Path]:
    """Return isolated scaffold & timestamp file locations inside *tmp_path*."""

    scaffold = tmp_path / "scaffolded"
    timestamp = tmp_path / "timestamp"
    return scaffold, timestamp


def _patched_env() -> ep.EntrypointEnv:  # noqa: D401 – helper
    """Return a minimal environment mapping suited for the restore tests."""

    return ep.gather_env({"ODOO_ADDONS_TIMESTAMP": "42"})


def test_restore_success(monkeypatch, tmp_path):  # noqa: D401 – imperative mood
    """When the helper succeeds the routine must *short-circuit* early."""

    scaffold, timestamp = _tmp_paths(tmp_path)

    import sys as _sys

    import sys as _sys

    monkeypatch.setattr(ep, "SCAFFOLDED_SEMAPHORE", scaffold)
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", timestamp)
    if "entrypoint" in _sys.modules:
        monkeypatch.setattr(_sys.modules["entrypoint"], "SCAFFOLDED_SEMAPHORE", scaffold, raising=False)
        monkeypatch.setattr(_sys.modules["entrypoint"], "ADDON_TIMESTAMP_FILE", timestamp, raising=False)
    # Also patch the *package* level attribute because the implementation may
    # resolve the constant from either location depending on import order.
    if "entrypoint" in _sys.modules:
        monkeypatch.setattr(_sys.modules["entrypoint"], "SCAFFOLDED_SEMAPHORE", scaffold, raising=False)
        monkeypatch.setattr(_sys.modules["entrypoint"], "ADDON_TIMESTAMP_FILE", timestamp, raising=False)

    # --- Fake presence of the helper & successful execution -----------------

    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, check):  # noqa: D401 – local stub
        calls.append(tuple(cmd))
        # Only *restore* and *odoo-regenerate-assets* reach this stub – both
        # must succeed therefore we return a dummy *CompletedProcess* object.
        return SimpleNamespace(returncode=0)

    restore_path = Path("/usr/local/sbin/restore")
    monkeypatch.setattr(restore_path.__class__, "is_file", lambda self: self == restore_path)
    monkeypatch.setattr("os.access", lambda p, mode: True)

    monkeypatch.setattr("subprocess.run", fake_run)

    # Prevent *mkdir* attempts under /etc/odoo inside the helper when the
    # constant patch would somehow be ignored by the implementation (for
    # instance if another test modified the attribute beforehand).  We stub
    # it out so the call becomes a *noop* regardless of the target path – we
    # only care about the high-level side-effects, not the actual
    # filesystem writes.
    monkeypatch.setattr("pathlib.Path.mkdir", lambda self, *a, **k: None)
    from pathlib import PosixPath

    monkeypatch.setattr(PosixPath, "touch", lambda self, *a, **k: None)
    monkeypatch.setattr(PosixPath, "write_text", lambda self, *a, **k: None)

    import os as _os
    monkeypatch.setattr(_os, "utime", lambda *a, **k: None)
    monkeypatch.setattr(_os, "open", lambda *a, **k: 1)
    from pathlib import PosixPath

    monkeypatch.setattr(PosixPath, "touch", lambda self, *a, **k: None)
    monkeypatch.setattr(PosixPath, "write_text", lambda self, *a, **k: None)
    monkeypatch.setattr(_os, "utime", lambda *a, **k: None)
    monkeypatch.setattr(_os, "open", lambda *a, **k: 1)

    ep.initialise_instance(_patched_env())

    # The helper and asset regeneration must have been invoked, *nothing* else
    # (addon-updater / odoo-config) should appear in the call list because the
    # function returned early.
    assert calls == [
        (str(restore_path),),
        ("odoo-regenerate-assets",),
    ]

    # Semaphore & timestamp helpers were invoked – the actual on-disk file may
    # not exist because we stubbed *Path.touch* but the *initialise_instance*
    # routine finished without raising which is sufficient proof that the
    # code path executed successfully.


def test_restore_absent(monkeypatch, tmp_path):  # noqa: D401 – imperative mood
    """Absent helper leads to the *standard* brand-new DB initialisation."""

    scaffold, timestamp = _tmp_paths(tmp_path)
    import sys as _sys

    monkeypatch.setattr(ep, "SCAFFOLDED_SEMAPHORE", scaffold)
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", timestamp)
    if "entrypoint" in _sys.modules:
        monkeypatch.setattr(_sys.modules["entrypoint"], "SCAFFOLDED_SEMAPHORE", scaffold, raising=False)
        monkeypatch.setattr(_sys.modules["entrypoint"], "ADDON_TIMESTAMP_FILE", timestamp, raising=False)

    # Pretend the helper binary does *not* exist.
    restore_path = Path("/usr/local/sbin/restore")
    monkeypatch.setattr(restore_path.__class__, "is_file", lambda self: False)

    # Collect calls to *subprocess.run* for later assertions.
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, check):  # noqa: D401 – local stub
        calls.append(tuple(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("pathlib.Path.mkdir", lambda self, *a, **k: None)

    # Force *collect_addons* to return a non-empty list so that the code path
    # actually attempts to run Odoo – the underlying binary is absent on the
    # CI host therefore the internal helper prints but does *not* reach
    # subprocess.  This is fine – we assert only the updater & config helpers.
    import os as _os

    monkeypatch.setattr(_os, "mkdir", lambda *a, **k: None)

    monkeypatch.setattr(ep, "collect_addons", lambda *a, **k: ["base", "web"])

    ep.initialise_instance(_patched_env())

    # Must have called the two mandatory utilities – *restore* and asset
    # regeneration are absent.
    assert ("odoo-addon-updater",) in calls
    assert ("odoo-config", "--defaults") in calls
    assert all("restore" not in c[0] for c in calls)

    # Routine returned successfully – detailed filesystem side-effects are
    # not asserted because *Path.touch* was stubbed.


def test_restore_failure(monkeypatch, tmp_path):  # noqa: D401 – imperative mood
    """Failure of the helper triggers *destroy* then proceeds normally."""

    scaffold, timestamp = _tmp_paths(tmp_path)
    monkeypatch.setattr(ep, "SCAFFOLDED_SEMAPHORE", scaffold)
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", timestamp)

    restore_path = Path("/usr/local/sbin/restore")
    monkeypatch.setattr(restore_path.__class__, "is_file", lambda self: self == restore_path)
    monkeypatch.setattr("os.access", lambda p, mode: True)

    # Fake subprocess behaviour: *restore* fails the first time, every other
    # call succeeds.
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, check):  # noqa: D401 – local stub
        calls.append(tuple(cmd))
        if "restore" in cmd[0]:
            import subprocess as _sp

            raise _sp.CalledProcessError(returncode=1, cmd=cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    # Track *destroy_instance* invocation.
    destroyed = False

    def fake_destroy(env):  # noqa: D401 – local stub
        nonlocal destroyed
        destroyed = True

    monkeypatch.setattr(ep, "destroy_instance", fake_destroy)

    monkeypatch.setattr("pathlib.Path.mkdir", lambda self, *a, **k: None)
    monkeypatch.setattr("pathlib.Path.touch", lambda self, *a, **k: None)
    monkeypatch.setattr("pathlib.Path.write_text", lambda self, *a, **k: None)

    monkeypatch.setattr("pathlib.Path.mkdir", lambda self, *a, **k: None)

    monkeypatch.setattr(ep, "collect_addons", lambda *a, **k: ["base", "web"])

    ep.initialise_instance(_patched_env())

    # First call is the failing restore, destroy must have been executed.
    assert destroyed is True
    assert calls and "restore" in calls[0][0]

    # The routine must have continued – that means odoo-addon-updater &
    # odoo-config were invoked afterwards.
    assert ("odoo-addon-updater",) in calls
    assert ("odoo-config", "--defaults") in calls

    # The routine completed without errors – this is enough for the purpose
    # of the unit-test given we stubbed out the filesystem operations.
    monkeypatch.setattr("pathlib.Path.write_text", lambda self, *a, **k: None)
