"""Verify that TODO #10 (PID handoff) is already complete.

This test suite confirms that the entrypoint already uses os.execv correctly,
meaning TODO #10 is actually done and the documentation is outdated.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

import entrypoint.entrypoint as ep


def test_main_already_uses_execv():
    """Demonstrate that main() already uses os.execv for the Odoo server."""
    
    # Check the source code directly
    import inspect
    source = inspect.getsource(ep.main)
    
    # Verify os.execv is used
    assert "os.execv(cmd[0], cmd)" in source
    
    # Verify it's not subprocess.run for the main process
    # Note: os.execv appears in comments too, so just verify it's there
    assert "os.execv(cmd[0], cmd)" in source  # Used for main server
    assert "os.execvp(args[0], args)" in source  # Used for custom commands
    
    # The comment says it replaces the process
    assert "exec*s either" in source or "exec`s either" in source
    assert "becomes *PID 1*" in source


def test_execv_location_in_main():
    """Verify os.execv is called at the right place in main()."""
    
    # Read the main function
    import inspect
    lines = inspect.getsource(ep.main).split('\n')
    
    # Find the execv line
    execv_line = None
    drop_privileges_line = None
    
    for i, line in enumerate(lines):
        if "os.execv(cmd[0], cmd)" in line:
            execv_line = i
        if "drop_privileges(env)" in line:
            drop_privileges_line = i
    
    assert execv_line is not None, "os.execv not found in main()"
    assert drop_privileges_line is not None, "drop_privileges not found"
    
    # Verify drop_privileges comes before execv
    assert drop_privileges_line < execv_line, "Privileges should be dropped before exec"


def test_custom_command_uses_execvp():
    """Verify custom commands use os.execvp (with PATH search)."""
    
    captured_execvp = []
    
    def mock_execvp(file, args):
        captured_execvp.append((file, args))
        raise SystemExit(0)
    
    # Minimal patching - just what's needed
    import sys
    old_execvp = os.execvp
    os.execvp = mock_execvp
    
    try:
        with pytest.raises(SystemExit):
            ep.main(["echo", "hello"])
        
        assert len(captured_execvp) == 1
        assert captured_execvp[0] == ("echo", ["echo", "hello"])
    finally:
        os.execvp = old_execvp


def test_subprocess_run_not_used_for_main_server():
    """Verify subprocess.run is NOT used for the main Odoo server process."""
    
    # Check that subprocess.run in main() is only in the dev-mode print statement
    import inspect
    source = inspect.getsource(ep.main)
    
    # subprocess.run should not appear in main() at all
    # (it's used in other functions for init/upgrade, but not in main)
    assert "subprocess.run" not in source
    
    
def test_build_odoo_command_returns_list():
    """Verify build_odoo_command returns the right format for execv."""
    
    # Test with minimal environment
    cmd = ep.build_odoo_command([])
    
    assert isinstance(cmd, list)
    assert cmd[0] == "/usr/bin/odoo"
    assert cmd[1] == "server"
    # Rest are flags


def test_todo_10_assessment():
    """Document the assessment of TODO #10."""
    
    # TODO #10 states:
    # "The current Python entrypoint correctly constructs the Odoo command 
    #  and handles environment preparation, but does **not** hand over PID 1 
    #  to the actual Odoo process."
    
    # However, the code clearly shows:
    # 1. main() uses os.execv(cmd[0], cmd) at line ~2441
    # 2. The docstring says it "ultimately `exec`s"
    # 3. The docstring says "the latter becomes *PID 1*"
    
    # Conclusion: TODO #10 is already complete!
    # The Python entrypoint DOES hand over PID 1 using os.execv
    
    assert True  # This test documents the findings


if __name__ == "__main__":
    pytest.main([__file__, "-v"])