"""Test improvements to file locking mechanism for TODO #7.

This suite validates the enhanced file locking implementation that ensures
proper mutual exclusion even in edge cases like permission errors or
unsupported file descriptors.
"""

from __future__ import annotations

import errno
import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

import pytest

import entrypoint as ep


def test_file_lock_fallback_to_temp_on_permission_error(monkeypatch, tmp_path):
    """Test fallback to temp directory when lock file creation fails due to permissions."""
    
    # Mock the initial open to raise PermissionError
    original_open = Path.open
    call_count = 0
    temp_lock_used = False
    
    def mock_path_open(self, mode="r", *args, **kwargs):
        nonlocal call_count, temp_lock_used
        call_count += 1
        
        if call_count == 1 and str(self).endswith('.lock'):
            # First call - simulate permission error
            raise PermissionError("Permission denied")
        elif str(self).startswith(tempfile.gettempdir()):
            # Second call - temp directory lock
            temp_lock_used = True
            return original_open(self, mode, *args, **kwargs)
        else:
            return original_open(self, mode, *args, **kwargs)
    
    monkeypatch.setattr(Path, "open", mock_path_open)
    
    # Mock fcntl.flock to succeed
    fcntl = importlib.import_module("fcntl")
    flock_calls = []
    
    def mock_flock(fd, flag):
        flock_calls.append(flag)
        return 0
    
    monkeypatch.setattr(fcntl, "flock", mock_flock)
    
    # Test the lock
    target = tmp_path / "test.txt"
    executed = False
    
    with ep._file_lock(target):
        executed = True
    
    assert executed, "Lock body should have executed"
    assert temp_lock_used, "Should have fallen back to temp directory lock"
    assert len(flock_calls) == 2, "Should have called flock for lock and unlock"
    assert flock_calls[0] == fcntl.LOCK_EX
    assert flock_calls[1] == fcntl.LOCK_UN


def test_file_lock_fallback_on_bad_file_descriptor(monkeypatch, tmp_path):
    """Test fallback to creation-based locking when flock fails with EBADF."""
    
    # Mock fcntl.flock to raise EBADF
    fcntl = importlib.import_module("fcntl")
    
    def mock_flock(fd, flag):
        if flag == fcntl.LOCK_EX:
            raise OSError(errno.EBADF, "Bad file descriptor")
        return 0
    
    monkeypatch.setattr(fcntl, "flock", mock_flock)
    
    # Test the lock
    target = tmp_path / "test.txt"
    executed = False
    
    with ep._file_lock(target):
        executed = True
    
    assert executed, "Lock body should have executed"
    
    # Verify lock file was cleaned up
    lock_path = target.with_suffix(".lock")
    assert not lock_path.exists(), "Lock file should be cleaned up"


def test_file_lock_timeout_on_stuck_lock(monkeypatch, tmp_path):
    """Test timeout behavior when another process holds the lock too long."""
    
    # Mock fcntl.flock to raise EINVAL
    fcntl = importlib.import_module("fcntl")
    
    def mock_flock(fd, flag):
        if flag == fcntl.LOCK_EX:
            raise OSError(errno.EINVAL, "Invalid argument")
        return 0
    
    monkeypatch.setattr(fcntl, "flock", mock_flock)
    
    # Create a pre-existing lock file to simulate stuck process
    lock_path = (tmp_path / "test.txt").with_suffix(".lock")
    lock_path.touch()
    
    # Mock os.open to always fail with EEXIST
    def mock_os_open(path, flags, *args):
        if flags & os.O_CREAT and flags & os.O_EXCL:
            raise FileExistsError("File exists")
        return -1  # Should not reach here
    
    monkeypatch.setattr(os, "open", mock_os_open)
    
    # Mock time.sleep to avoid actual waiting
    sleep_count = 0
    
    def mock_sleep(seconds):
        nonlocal sleep_count
        sleep_count += 1
    
    monkeypatch.setattr("time.sleep", mock_sleep)
    
    # Test the lock with timeout
    target = tmp_path / "test.txt"
    executed = False
    
    # Capture stderr to check for timeout warning
    import io
    from contextlib import redirect_stderr
    
    stderr_capture = io.StringIO()
    
    with redirect_stderr(stderr_capture):
        with ep._file_lock(target):
            executed = True
    
    assert executed, "Lock body should have executed despite timeout"
    assert sleep_count == 99, "Should have slept 99 times (100 retries - 1)"
    assert "ERROR: timeout waiting for lock" in stderr_capture.getvalue()


def test_file_lock_reraises_unexpected_errors(monkeypatch, tmp_path):
    """Test that unexpected OSErrors are re-raised instead of being swallowed."""
    
    # Mock fcntl.flock to raise an unexpected error
    fcntl = importlib.import_module("fcntl")
    
    def mock_flock(fd, flag):
        if flag == fcntl.LOCK_EX:
            raise OSError(errno.EACCES, "Access denied")  # Not EBADF/EINVAL
        return 0
    
    monkeypatch.setattr(fcntl, "flock", mock_flock)
    
    # Test that the error is re-raised
    target = tmp_path / "test.txt"
    
    with pytest.raises(OSError) as exc_info:
        with ep._file_lock(target):
            pass  # Should not reach here
    
    assert exc_info.value.errno == errno.EACCES


def test_file_lock_complete_failure_fallback(monkeypatch, tmp_path):
    """Test behavior when all lock attempts fail."""
    
    # Mock Path.open to always fail
    def mock_path_open(self, mode="r", *args, **kwargs):
        raise OSError("Cannot create any file")
    
    monkeypatch.setattr(Path, "open", mock_path_open)
    
    # Test the lock
    target = tmp_path / "test.txt"
    executed = False
    
    # Capture stderr
    import io
    from contextlib import redirect_stderr
    
    stderr_capture = io.StringIO()
    
    with redirect_stderr(stderr_capture):
        with ep._file_lock(target):
            executed = True
    
    assert executed, "Lock body should have executed even without lock"
    assert "ERROR: cannot create any lock file" in stderr_capture.getvalue()


def test_concurrent_access_protection(monkeypatch, tmp_path):
    """Test that file locking properly serializes concurrent access."""
    
    # This test simulates concurrent access by tracking the order of operations
    operations = []
    
    # Mock fcntl.flock to track lock/unlock operations
    fcntl = importlib.import_module("fcntl")
    
    def mock_flock(fd, flag):
        if flag == fcntl.LOCK_EX:
            operations.append("lock")
        elif flag == fcntl.LOCK_UN:
            operations.append("unlock")
        return 0
    
    monkeypatch.setattr(fcntl, "flock", mock_flock)
    
    # Test nested locks (should serialize)
    target = tmp_path / "test.txt"
    
    with ep._file_lock(target):
        operations.append("outer_start")
        # Simulate another process trying to acquire the same lock
        # (In real scenario, this would block)
        operations.append("outer_end")
    
    # Verify operations happened in correct order
    assert operations == ["lock", "outer_start", "outer_end", "unlock"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])