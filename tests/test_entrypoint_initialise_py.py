"""Extended tests for *initialise_instance* helper.

This new suite validates the *two–pass* install logic introduced in the
Python entry-point as well as the additional side-effects (external helper
invocations and semaphore handling).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import entrypoint as ep


def _make_module(path: Path, name: str, depends: list[str] | None = None) -> None:
    """Create a dummy Odoo module under *path* with the given *name*."""

    mod_dir = path / name
    mod_dir.mkdir(parents=True)
    manifest = {
        "name": name,
        "depends": depends or [],
    }
    (mod_dir / "__manifest__.py").write_text(repr(manifest), encoding="utf-8")


def test_initialise_instance_full_flow(monkeypatch, tmp_path):
    """Helper must run expected subprocesses and touch semaphore files."""

    # ------------------------------------------------------------------
    # 1. Fake filesystem layout: two core paths + one extras path containing
    #    minimal dummy modules so that *collect_addons* yields deterministic
    #    results.
    # ------------------------------------------------------------------

    core_a = tmp_path / "coreA"
    core_b = tmp_path / "coreB"
    extras = tmp_path / "extras"

    for p in (core_a, core_b, extras):
        p.mkdir()

    _make_module(core_a, "base")
    _make_module(core_a, "web", ["base"])
    _make_module(core_b, "crm", ["base", "web"])
    _make_module(extras, "awesome_theme", ["web"])

    # Monkey-patch *get_addons_paths* so the helper uses our sandbox.
    monkeypatch.setattr(
        ep,
        "get_addons_paths",
        lambda _env=None: [str(core_a), str(core_b), str(extras)],
    )

    # ------------------------------------------------------------------
    # 2. Substitute *subprocess.run* to capture the exact calls instead of
    #    executing real binaries – no Odoo installation is required.
    # ------------------------------------------------------------------

    calls: list[tuple[str, ...]] = []

    def _fake_run(cmd: list[str], check: bool = False, **_kwargs):  # noqa: D401,WPS430
        calls.append(tuple(cmd))
        return SimpleNamespace(returncode=0)

    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", _fake_run)

    # Ensure lookup for the absolute path of the Odoo binary returns *False*
    # so that the helper does NOT attempt a real execution (the fake run
    # above is only for helper utilities `odoo-addon-updater` / `odoo-config`).
    # Do **not** break other places relying on Path.is_file – override with a
    # wrapper that only reports *False* for the specific Odoo binary path.
    _orig_is_file = Path.is_file

    def _fake_is_file(self: Path) -> bool:  # noqa: D401
        if str(self) == "/usr/bin/odoo":
            return False
        return _orig_is_file(self)

    monkeypatch.setattr(Path, "is_file", _fake_is_file, raising=False)

    # Redirect semaphore paths inside the temp dir so we can inspect them.
    scaffold_file = tmp_path / ".scaffolded"
    ts_file = tmp_path / ".timestamp"

    import sys

    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "SCAFFOLDED_SEMAPHORE", scaffold_file, raising=False)
    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "ADDON_TIMESTAMP_FILE", ts_file, raising=False)

    # Environment with build-time timestamp.
    env = {"ODOO_ADDONS_TIMESTAMP": "999"}

    # ------------------------------------------------------------------
    # 3. Execute the helper under test.
    # ------------------------------------------------------------------

    ep.initialise_instance(env)

    # ------------------------------------------------------------------
    # 4. Assertions.
    # ------------------------------------------------------------------

    # External helper utilities *must* be invoked.
    assert ("odoo-addon-updater",) in calls
    assert ("odoo-config", "--defaults") in calls

    # Semaphore files shall be written.
    assert scaffold_file.exists(), "scaffold semaphore missing"
    assert ts_file.read_text("utf-8") == "999"
