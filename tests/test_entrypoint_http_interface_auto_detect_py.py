"""Test for compute_http_interface auto-detection fix (TODO #6).

This test verifies that when ODOO_MAJOR_VERSION is not set, the
compute_http_interface function is called with None to trigger
auto-detection via the odoo binary.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import subprocess

from entrypoint import build_odoo_command, compute_http_interface


class TestHttpInterfaceAutoDetect(unittest.TestCase):
    """Test class for HTTP interface auto-detection."""
    
    def test_compute_http_interface_with_version_17(self):
        """Test that version 17 returns IPv6 interface."""
        result = compute_http_interface(17)
        self.assertEqual(result, "::")
        
        result = compute_http_interface("17")
        self.assertEqual(result, "::")

    def test_compute_http_interface_with_version_16(self):
        """Test that version 16 returns IPv4 interface."""
        result = compute_http_interface(16)
        self.assertEqual(result, "0.0.0.0")
        
        result = compute_http_interface("16")
        self.assertEqual(result, "0.0.0.0")

    @patch('subprocess.check_output')
    def test_compute_http_interface_auto_detect_v17(self, mock_check_output):
        """Test auto-detection when version is None and odoo returns v17."""
        mock_check_output.return_value = "Odoo Server 17.0"
        
        result = compute_http_interface(None)
        
        self.assertEqual(result, "::")
        mock_check_output.assert_called_once_with(
            ["odoo", "--version"], 
            stderr=subprocess.STDOUT, 
            text=True
        )

    @patch('subprocess.check_output')
    def test_compute_http_interface_auto_detect_v16(self, mock_check_output):
        """Test auto-detection when version is None and odoo returns v16."""
        mock_check_output.return_value = "Odoo Server 16.0+e"
        
        result = compute_http_interface(None)
        
        self.assertEqual(result, "0.0.0.0")
        mock_check_output.assert_called_once_with(
            ["odoo", "--version"], 
            stderr=subprocess.STDOUT, 
            text=True
        )

    @patch('subprocess.check_output')
    def test_compute_http_interface_auto_detect_failure(self, mock_check_output):
        """Test fallback when auto-detection fails."""
        mock_check_output.side_effect = FileNotFoundError("odoo not found")
        
        result = compute_http_interface(None)
        
        # Should fall back to IPv4
        self.assertEqual(result, "0.0.0.0")

    @patch('subprocess.check_output')
    def test_build_odoo_command_without_major_version_env(self, mock_check_output):
        """Test that build_odoo_command triggers auto-detection when ODOO_MAJOR_VERSION is not set."""
        # Mock successful auto-detection of version 17
        mock_check_output.return_value = "Odoo Server 17.0"
        
        # Build command without ODOO_MAJOR_VERSION environment variable
        cmd = build_odoo_command([])
        
        # Verify that auto-detection was triggered
        mock_check_output.assert_called_with(
            ["odoo", "--version"], 
            stderr=subprocess.STDOUT, 
            text=True
        )
        
        # Verify IPv6 interface was selected
        self.assertIn("--http-interface", cmd)
        idx = cmd.index("--http-interface")
        self.assertEqual(cmd[idx + 1], "::")

    @patch.dict('os.environ', {'ODOO_MAJOR_VERSION': '18'})
    def test_build_odoo_command_with_major_version_env(self):
        """Test that build_odoo_command uses ODOO_MAJOR_VERSION when set."""
        # Build command with ODOO_MAJOR_VERSION set
        cmd = build_odoo_command([])
        
        # Verify IPv6 interface was selected (version 18 >= 17)
        self.assertIn("--http-interface", cmd)
        idx = cmd.index("--http-interface")
        self.assertEqual(cmd[idx + 1], "::")

    @patch.dict('os.environ', {'ODOO_MAJOR_VERSION': '15'})
    def test_build_odoo_command_with_old_major_version_env(self):
        """Test that build_odoo_command uses IPv4 for old versions."""
        # Build command with ODOO_MAJOR_VERSION set to old version
        cmd = build_odoo_command([])
        
        # Verify IPv4 interface was selected (version 15 < 17)
        self.assertIn("--http-interface", cmd)
        idx = cmd.index("--http-interface")
        self.assertEqual(cmd[idx + 1], "0.0.0.0")


if __name__ == "__main__":
    unittest.main()