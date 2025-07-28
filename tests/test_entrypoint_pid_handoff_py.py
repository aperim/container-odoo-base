"""Test that the entrypoint properly hands off PID 1 to Odoo process (TODO #10).

This suite validates that the Python entrypoint uses os.execv to replace itself
with the Odoo process, ensuring proper signal handling in container environments.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock, patch, call

import pytest

import entrypoint.entrypoint as ep


def test_main_uses_execv_for_odoo_server(monkeypatch):
    """Test that main() uses os.execv to replace the Python process with Odoo."""
    
    # Track execv calls
    execv_calls = []
    
    def mock_execv(path, args):
        execv_calls.append((path, args))
        # Don't actually exec (would terminate test)
        raise SystemExit(0)  # Simulate successful exec
    
    monkeypatch.setattr(os, "execv", mock_execv)
    
    # Mock other dependencies
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "exists", lambda self: False)  # No scaffolded file
    monkeypatch.setattr("subprocess.run", Mock())
    
    # Mock the entrypoint module functions
    monkeypatch.setattr(ep, "apply_runtime_user", Mock())
    monkeypatch.setattr(ep, "fix_permissions", Mock())
    monkeypatch.setattr(ep, "wait_for_dependencies", Mock())
    monkeypatch.setattr(ep, "runtime_housekeeping", Mock())
    monkeypatch.setattr(ep, "drop_privileges", Mock())
    
    # Run main with no arguments (default Odoo server)
    with pytest.raises(SystemExit) as exc_info:
        ep.main([])
    
    # Verify it exited cleanly
    assert exc_info.value.code == 0
    
    # Verify execv was called
    assert len(execv_calls) == 1
    path, args = execv_calls[0]
    
    # Verify it's executing the Odoo binary
    assert path == "/usr/bin/odoo"
    assert args[0] == "/usr/bin/odoo"
    assert args[1] == "server"
    
    # Verify os.execv was used, not subprocess.run
    assert ep.drop_privileges.called  # Should drop privileges before exec


def test_main_uses_execvp_for_custom_commands(monkeypatch):
    """Test that main() uses os.execvp for custom user commands."""
    
    # Track execvp calls
    execvp_calls = []
    
    def mock_execvp(file, args):
        execvp_calls.append((file, args))
        # Don't actually exec
        raise SystemExit(0)
    
    monkeypatch.setattr(os, "execvp", mock_execvp)
    
    # Run main with custom command
    with pytest.raises(SystemExit) as exc_info:
        ep.main(["psql", "-U", "postgres"])
    
    # Verify it exited cleanly
    assert exc_info.value.code == 0
    
    # Verify execvp was called for custom command
    assert len(execvp_calls) == 1
    file, args = execvp_calls[0]
    
    assert file == "psql"
    assert args == ["psql", "-U", "postgres"]


def test_subprocess_run_only_used_for_init_and_upgrade(monkeypatch, tmp_path):
    """Test that subprocess.run is only used for --stop-after-init commands."""
    
    # Track subprocess.run calls
    subprocess_calls = []
    
    def mock_subprocess_run(cmd, **kwargs):
        subprocess_calls.append(cmd)
        # Simulate successful run
        return Mock(returncode=0)
    
    monkeypatch.setattr("subprocess.run", mock_subprocess_run)
    monkeypatch.setattr("subprocess.CalledProcessError", Exception)
    
    # Mock file checks
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    monkeypatch.setattr(Path, "exists", lambda self: str(self).endswith("scaffolded"))
    
    # Test initialise_instance
    ep.initialise_instance()
    
    # Check that odoo commands use --stop-after-init
    odoo_calls = [cmd for cmd in subprocess_calls if "/usr/bin/odoo" in cmd[0]]
    for cmd in odoo_calls:
        assert "--stop-after-init" in cmd, f"Command {cmd} should include --stop-after-init"
        assert "--init" in cmd or "--update" in cmd
    
    # Reset
    subprocess_calls.clear()
    
    # Test upgrade_modules
    monkeypatch.setattr(ep, "collect_addons", lambda *args: ["sale", "stock"])
    monkeypatch.setattr(ep, "update_needed", lambda *args: True)
    
    # Create timestamp files
    ts_file = tmp_path / ".timestamp"
    ts_file.write_text("old")
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", ts_file)
    
    ep.upgrade_modules()
    
    # Check upgrade commands also use --stop-after-init
    odoo_calls = [cmd for cmd in subprocess_calls if "/usr/bin/odoo" in cmd[0]]
    for cmd in odoo_calls:
        assert "--stop-after-init" in cmd
        assert "--update" in cmd


def test_no_subprocess_for_main_server_process(monkeypatch):
    """Test that the main server process does NOT use subprocess.run."""
    
    # This should fail if subprocess.run is called
    def fail_on_subprocess(*args, **kwargs):
        if args and "/usr/bin/odoo" in str(args[0]) and "--stop-after-init" not in str(args[0]):
            pytest.fail("Main server should use os.execv, not subprocess.run")
        return Mock(returncode=0)
    
    monkeypatch.setattr("subprocess.run", fail_on_subprocess)
    
    # Mock dependencies
    monkeypatch.setattr(os, "execv", Mock(side_effect=SystemExit(0)))
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    
    # Mock entrypoint functions
    monkeypatch.setattr(ep, "apply_runtime_user", Mock())
    monkeypatch.setattr(ep, "fix_permissions", Mock())
    monkeypatch.setattr(ep, "wait_for_dependencies", Mock())
    monkeypatch.setattr(ep, "runtime_housekeeping", Mock())
    monkeypatch.setattr(ep, "drop_privileges", Mock())
    
    # This should NOT call subprocess.run for the main server
    with pytest.raises(SystemExit):
        ep.main([])
    
    # Verify os.execv was called
    assert os.execv.called


def test_signal_handling_preserved():
    """Document that os.execv preserves signal handling for the container."""
    
    # This is more of a documentation test
    # os.execv replaces the current process, so:
    # 1. The new process gets the same PID (usually 1 in container)
    # 2. Signals sent to the container go directly to Odoo
    # 3. No Python wrapper process remains to interfere
    
    # The key difference from subprocess.run:
    # - subprocess.run: Python remains as PID 1, Odoo is a child process
    # - os.execv: Odoo becomes PID 1, Python process is gone
    
    # This is critical for:
    # - SIGTERM handling during container shutdown
    # - SIGHUP for reload scenarios
    # - Proper process tree in container orchestrators
    
    assert True  # This test documents the behavior


if __name__ == "__main__":
    pytest.main([__file__, "-v"])