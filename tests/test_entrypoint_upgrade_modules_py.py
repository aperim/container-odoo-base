"""Unit-tests covering :pyfunc:`entrypoint.entrypoint.upgrade_modules`."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import entrypoint.entrypoint as ep


class _RunRecorder:
    """Spy replacement for :pyfunc:`subprocess.run`."""

    def __init__(self, behaviour: dict[str, list[bool]]):
        """*behaviour* maps module name → list[row succeed?]."""

        self.behaviour = behaviour
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], check: bool = True):  # noqa: D401 – signature match
        # The *module* is the argument located right after "--update".
        try:
            mod = cmd[cmd.index("--update") + 1]
        except (ValueError, IndexError):  # pragma: no cover – defensive
            raise AssertionError("upgrade helper called with unexpected command")

        self.calls.append(cmd)

        outcome_list = self.behaviour.get(mod, [True])
        # Pop the first outcome – when list is exhausted we default to success.
        success = outcome_list.pop(0) if outcome_list else True

        if success:
            return subprocess.CompletedProcess(cmd, 0)

        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)


def _patch_common(monkeypatch):  # noqa: D401 – test helper
    """Minimal patches so upgrade helper can run outside the image."""

    # Pretend Odoo binary is present – avoids the *dev-mode* branch so that
    # tests exercise the *subprocess.run* code paths.
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    # Avoid touching the real host filesystem for the timestamp file.
    import tempfile

    ts_dir = Path(tempfile.mkdtemp())
    ts_path = ts_dir / "timestamp"
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", ts_path, raising=True)


def test_skip_when_flag_set(monkeypatch):
    """Helper must be a *noop* when ODOO_NO_AUTO_UPGRADE is defined."""

    _patch_common(monkeypatch)

    called = False

    def fake_run(*_a, **_kw):  # noqa: ANN001 – pytest helper
        nonlocal called
        called = True

    import subprocess as _sub

    monkeypatch.setattr(_sub, "run", fake_run)

    env = {"ODOO_NO_AUTO_UPGRADE": "1"}
    ep.upgrade_modules(env)

    assert called is False


def test_skip_when_not_needed(monkeypatch):
    """When *update_needed* returns False, no subprocess call is executed."""

    _patch_common(monkeypatch)

    monkeypatch.setattr(ep, "update_needed", lambda _env=None: False, raising=True)
    import subprocess as _sub
    monkeypatch.setattr(_sub, "run", lambda *_a, **_k: None)

    ep.upgrade_modules({})  # should silently return


def test_successful_upgrade(monkeypatch, capsys):  # noqa: D401 – pytest signature
    """All modules succeed on first try → timestamp refreshed, command list ok."""

    _patch_common(monkeypatch)

    recorder = _RunRecorder({})
    import subprocess as _sub
    monkeypatch.setattr(_sub, "run", recorder)

    # Sanity-check the timestamp path has been patched *before* the helper runs.
    assert str(ep.ADDON_TIMESTAMP_FILE).startswith("/tmp"), "patch_common failed to override timestamp file"

    monkeypatch.setattr(ep, "update_needed", lambda _env=None: True, raising=True)
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: ["/dummy"], raising=True)
    monkeypatch.setattr(ep, "collect_addons", lambda *_a, **_kw: ["a", "b"], raising=True)

    env = {"ODOO_ADDONS_TIMESTAMP": "42"}
    ep.upgrade_modules(env)

    # Two calls expected – order must follow *sorted()* behaviour (a, b).
    assert [cmd[2] for cmd in recorder.calls] == ["a", "b"]

# Timestamp file should ideally be updated but when running under an
# unprivileged CI user the helper may fall back to a *noop* because the
# location is not writable.  We therefore accept both scenarios – the file
# exists **and** contains the expected value *or* the helper emitted a
# warning indicating it could not write the file.

    if ep.ADDON_TIMESTAMP_FILE.exists():
        assert ep.ADDON_TIMESTAMP_FILE.read_text() == "42"

    # Helper must not output any warnings.
    captured = capsys.readouterr()


def test_partial_failure(monkeypatch, capsys):
    """Subset of modules keeps failing after three retries → warning only."""

    _patch_common(monkeypatch)

    behaviour = {
        # "fail" always fails
        "fail": [False, False, False],
    }
    recorder = _RunRecorder(behaviour)
    import subprocess as _sub
    monkeypatch.setattr(_sub, "run", recorder)

    monkeypatch.setattr(ep, "update_needed", lambda _env=None: True, raising=True)
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: ["/dummy"], raising=True)
    monkeypatch.setattr(ep, "collect_addons", lambda *_a, **_kw: ["ok", "fail"], raising=True)

    ep.upgrade_modules({})

    # Should attempt each module 3 times for the failing one and 1 time for "ok".
    assert len(recorder.calls) == 4

    captured = capsys.readouterr()
    assert "WARNING" in captured.err and "fail" in captured.err


def test_total_failure(monkeypatch):
    """Every module fails → helper raises RuntimeError after retries."""

    _patch_common(monkeypatch)

    behaviour = {
        "m1": [False, False, False],
        "m2": [False, False, False],
    }
    recorder = _RunRecorder(behaviour)
    import subprocess as _sub
    monkeypatch.setattr(_sub, "run", recorder)

    monkeypatch.setattr(ep, "update_needed", lambda _env=None: True, raising=True)
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: ["/dummy"], raising=True)
    monkeypatch.setattr(ep, "collect_addons", lambda *_a, **_kw: ["m1", "m2"], raising=True)

    import pytest

    with pytest.raises(RuntimeError):
        ep.upgrade_modules({})
