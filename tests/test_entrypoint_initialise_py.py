"""Tests for *initialise_instance* helper in the Python entrypoint."""

from __future__ import annotations

from pathlib import Path

import entrypoint as ep


def test_initialise_instance_creates_semaphores(monkeypatch, tmp_path, capsys):
    """Helper must create scaffold semaphore and write addon timestamp."""

    # ------------------------------------------------------------------
    # 1. Redirect *semaphore* files to our temporary sandbox so that the
    #    helper can run without elevated permissions on the CI worker.
    # ------------------------------------------------------------------

    import sys

    scaffold_file: Path = tmp_path / ".scaffolded"
    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "SCAFFOLDED_SEMAPHORE", scaffold_file, raising=False)

    timestamp_file: Path = tmp_path / ".timestamp"
    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "ADDON_TIMESTAMP_FILE", timestamp_file, raising=False)

    # Provide a minimal fake environment containing only the bits required
    # by the helper.
    env = {
        "ODOO_ADDONS_TIMESTAMP": "555",
    }

    # Stub *get_addons_paths* so that the helper does not attempt to scan the
    # real filesystem – this keeps the test fast and deterministic.
    monkeypatch.setattr(sys.modules["entrypoint.entrypoint"], "get_addons_paths", lambda _env=None: [])

    # Execute the code under test.
    ep.initialise_instance(env)

    # ------------------------------------------------------------------
    # 2. Assertions – both semaphore files shall exist with the expected
    #    contents and the stderr diagnostic should contain the simulated
    #    Odoo command.
    # ------------------------------------------------------------------

    assert scaffold_file.exists(), "scaffold semaphore must be touched"

    assert timestamp_file.read_text("utf-8") == "555"

    stderr = capsys.readouterr().err
    # The helper prints the command that *would* be executed – we verify the
    # presence of the core pieces instead of matching the whole string to
    # avoid flakiness when the implementation evolves (e.g. additional
    # flags).
    assert "--init base,web" in stderr
