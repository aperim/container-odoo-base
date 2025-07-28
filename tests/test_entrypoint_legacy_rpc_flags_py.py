"""Test coverage for legacy RPC flags (netrpc and xmlrpcs).

This suite validates the newly added CLI options that complete the TODO #2
matrix for legacy RPC interfaces (netrpc and xmlrpcs with their interface
and port options).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch
import os

from entrypoint import build_odoo_command


class TestLegacyRPCFlags(unittest.TestCase):
    """Test class for legacy RPC flags (TODO #2 final completion)."""
    
    def _extract_flags(self, cmd: list[str]) -> set[str]:
        """Return the set of *flags* present in *cmd* (omit their values)."""
        out: set[str] = set()
        it = iter(cmd)
        # Skip executable and sub-command ("/usr/bin/odoo server")
        next(it)
        next(it)
        for token in it:
            if token.startswith("--"):
                out.add(token)
        return out

    @patch.dict(os.environ, {"ODOO_NETRPC": "true"})
    def test_netrpc_flag_enabled(self):
        """Test --netrpc flag is added when ODOO_NETRPC is set to true."""
        cmd = build_odoo_command([])
        self.assertIn("--netrpc", cmd)

    @patch.dict(os.environ, {"ODOO_NETRPC": "1"})
    def test_netrpc_flag_enabled_with_1(self):
        """Test --netrpc flag is added when ODOO_NETRPC is set to 1."""
        cmd = build_odoo_command([])
        self.assertIn("--netrpc", cmd)

    @patch.dict(os.environ, {"ODOO_NETRPC": "yes"})
    def test_netrpc_flag_enabled_with_yes(self):
        """Test --netrpc flag is added when ODOO_NETRPC is set to yes."""
        cmd = build_odoo_command([])
        self.assertIn("--netrpc", cmd)

    @patch.dict(os.environ, {"ODOO_NETRPC": "on"})
    def test_netrpc_flag_enabled_with_on(self):
        """Test --netrpc flag is added when ODOO_NETRPC is set to on."""
        cmd = build_odoo_command([])
        self.assertIn("--netrpc", cmd)

    @patch.dict(os.environ, {"ODOO_NETRPC": "false"})
    def test_netrpc_flag_not_added_when_false(self):
        """Test --netrpc flag is NOT added when ODOO_NETRPC is false."""
        cmd = build_odoo_command([])
        self.assertNotIn("--netrpc", cmd)

    @patch.dict(os.environ, {"ODOO_NETRPC": ""})
    def test_netrpc_flag_not_added_when_empty(self):
        """Test --netrpc flag is NOT added when ODOO_NETRPC is empty."""
        cmd = build_odoo_command([])
        self.assertNotIn("--netrpc", cmd)

    @patch.dict(os.environ, {
        "ODOO_NETRPC": "true",
        "ODOO_NETRPC_INTERFACE": "127.0.0.1"
    })
    def test_netrpc_interface_flag(self):
        """Test --netrpc-interface flag is added when ODOO_NETRPC_INTERFACE is set."""
        cmd = build_odoo_command([])
        self.assertIn("--netrpc", cmd)
        self.assertIn("--netrpc-interface", cmd)
        idx = cmd.index("--netrpc-interface")
        self.assertEqual(cmd[idx + 1], "127.0.0.1")

    @patch.dict(os.environ, {
        "ODOO_NETRPC": "true",
        "ODOO_NETRPC_PORT": "8070"
    })
    def test_netrpc_port_flag(self):
        """Test --netrpc-port flag is added when ODOO_NETRPC_PORT is set."""
        cmd = build_odoo_command([])
        self.assertIn("--netrpc", cmd)
        self.assertIn("--netrpc-port", cmd)
        idx = cmd.index("--netrpc-port")
        self.assertEqual(cmd[idx + 1], "8070")

    @patch.dict(os.environ, {
        "ODOO_NETRPC": "true",
        "ODOO_NETRPC_INTERFACE": "0.0.0.0",
        "ODOO_NETRPC_PORT": "8070"
    })
    def test_netrpc_all_flags(self):
        """Test all netrpc flags work together."""
        cmd = build_odoo_command([])
        self.assertIn("--netrpc", cmd)
        self.assertIn("--netrpc-interface", cmd)
        self.assertIn("--netrpc-port", cmd)
        
        idx_interface = cmd.index("--netrpc-interface")
        self.assertEqual(cmd[idx_interface + 1], "0.0.0.0")
        
        idx_port = cmd.index("--netrpc-port")
        self.assertEqual(cmd[idx_port + 1], "8070")

    @patch.dict(os.environ, {
        "ODOO_NETRPC": "false",
        "ODOO_NETRPC_INTERFACE": "127.0.0.1",
        "ODOO_NETRPC_PORT": "8070"
    })
    def test_netrpc_interface_port_not_added_when_disabled(self):
        """Test interface/port flags are NOT added when netrpc is disabled."""
        cmd = build_odoo_command([])
        self.assertNotIn("--netrpc", cmd)
        self.assertNotIn("--netrpc-interface", cmd)
        self.assertNotIn("--netrpc-port", cmd)

    # XML-RPC Secure tests
    @patch.dict(os.environ, {"ODOO_XMLRPCS": "true"})
    def test_xmlrpcs_flag_enabled(self):
        """Test --xmlrpcs flag is added when ODOO_XMLRPCS is set to true."""
        cmd = build_odoo_command([])
        self.assertIn("--xmlrpcs", cmd)

    @patch.dict(os.environ, {"ODOO_XMLRPCS": "1"})
    def test_xmlrpcs_flag_enabled_with_1(self):
        """Test --xmlrpcs flag is added when ODOO_XMLRPCS is set to 1."""
        cmd = build_odoo_command([])
        self.assertIn("--xmlrpcs", cmd)

    @patch.dict(os.environ, {"ODOO_XMLRPCS": "false"})
    def test_xmlrpcs_flag_not_added_when_false(self):
        """Test --xmlrpcs flag is NOT added when ODOO_XMLRPCS is false."""
        cmd = build_odoo_command([])
        self.assertNotIn("--xmlrpcs", cmd)

    @patch.dict(os.environ, {
        "ODOO_XMLRPCS": "true",
        "ODOO_XMLRPCS_INTERFACE": "0.0.0.0"
    })
    def test_xmlrpcs_interface_flag(self):
        """Test --xmlrpcs-interface flag is added when ODOO_XMLRPCS_INTERFACE is set."""
        cmd = build_odoo_command([])
        self.assertIn("--xmlrpcs", cmd)
        self.assertIn("--xmlrpcs-interface", cmd)
        idx = cmd.index("--xmlrpcs-interface")
        self.assertEqual(cmd[idx + 1], "0.0.0.0")

    @patch.dict(os.environ, {
        "ODOO_XMLRPCS": "true",
        "ODOO_XMLRPCS_PORT": "8071"
    })
    def test_xmlrpcs_port_flag(self):
        """Test --xmlrpcs-port flag is added when ODOO_XMLRPCS_PORT is set."""
        cmd = build_odoo_command([])
        self.assertIn("--xmlrpcs", cmd)
        self.assertIn("--xmlrpcs-port", cmd)
        idx = cmd.index("--xmlrpcs-port")
        self.assertEqual(cmd[idx + 1], "8071")

    @patch.dict(os.environ, {
        "ODOO_XMLRPCS": "yes",
        "ODOO_XMLRPCS_INTERFACE": "::",
        "ODOO_XMLRPCS_PORT": "8443"
    })
    def test_xmlrpcs_all_flags(self):
        """Test all xmlrpcs flags work together."""
        cmd = build_odoo_command([])
        self.assertIn("--xmlrpcs", cmd)
        self.assertIn("--xmlrpcs-interface", cmd)
        self.assertIn("--xmlrpcs-port", cmd)
        
        idx_interface = cmd.index("--xmlrpcs-interface")
        self.assertEqual(cmd[idx_interface + 1], "::")
        
        idx_port = cmd.index("--xmlrpcs-port")
        self.assertEqual(cmd[idx_port + 1], "8443")

    @patch.dict(os.environ, {
        "ODOO_NETRPC": "true",
        "ODOO_NETRPC_PORT": "8070",
        "ODOO_XMLRPCS": "true",
        "ODOO_XMLRPCS_PORT": "8443"
    })
    def test_both_rpc_protocols_together(self):
        """Test netrpc and xmlrpcs can be enabled together."""
        cmd = build_odoo_command([])
        flags = self._extract_flags(cmd)
        
        # Check both main flags are present
        self.assertIn("--netrpc", flags)
        self.assertIn("--xmlrpcs", flags)
        
        # Check ports are set correctly
        self.assertIn("--netrpc-port", flags)
        self.assertIn("--xmlrpcs-port", flags)
        
        idx_netrpc = cmd.index("--netrpc-port")
        self.assertEqual(cmd[idx_netrpc + 1], "8070")
        
        idx_xmlrpcs = cmd.index("--xmlrpcs-port")
        self.assertEqual(cmd[idx_xmlrpcs + 1], "8443")

    def test_user_override_legacy_rpc(self):
        """Test that user-provided flags override environment variables."""
        with patch.dict(os.environ, {"ODOO_NETRPC": "true"}):
            # User explicitly disables netrpc
            cmd = build_odoo_command(["--netrpc-port", "9999"])
            # The --netrpc flag should still be added due to env var
            self.assertIn("--netrpc", cmd)
            # But user's port should be preserved (not overridden)
            self.assertEqual(cmd.count("--netrpc-port"), 1)
            idx = cmd.index("--netrpc-port")
            self.assertEqual(cmd[idx + 1], "9999")


if __name__ == "__main__":
    unittest.main()