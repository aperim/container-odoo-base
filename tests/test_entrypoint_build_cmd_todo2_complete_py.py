"""Test coverage for the remaining TODO #2 flags completion.

This suite validates the newly added CLI options that complete the TODO #2
matrix for missing flags (import-partial, log-db, osv-memory-*, pidfile,
pg-path, reportgz, test-enable, timezone, translate-modules, without-demo).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch
import os

from entrypoint import build_odoo_command


class TestTodo2FlagsCompletion(unittest.TestCase):
    """Test class for TODO #2 flags completion."""
    
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

    @patch.dict(os.environ, {"ODOO_IMPORT_PARTIAL": "/tmp/import_state.csv"})
    def test_import_partial_flag(self):
        """Test --import-partial flag is added when ODOO_IMPORT_PARTIAL is set."""
        cmd = build_odoo_command([])
        self.assertIn("--import-partial", cmd)
        idx = cmd.index("--import-partial")
        self.assertEqual(cmd[idx + 1], "/tmp/import_state.csv")

    @patch.dict(os.environ, {"ODOO_LOG_DB": "log_database"})
    def test_log_db_flag(self):
        """Test --log-db flag is added when ODOO_LOG_DB is set."""
        cmd = build_odoo_command([])
        self.assertIn("--log-db", cmd)
        idx = cmd.index("--log-db")
        self.assertEqual(cmd[idx + 1], "log_database")

    @patch.dict(os.environ, {
        "ODOO_OSV_MEMORY_AGE_LIMIT": "1.5",
        "ODOO_OSV_MEMORY_COUNT_LIMIT": "5000"
    })
    def test_osv_memory_flags(self):
        """Test --osv-memory-age-limit and --osv-memory-count-limit flags."""
        cmd = build_odoo_command([])
        
        self.assertIn("--osv-memory-age-limit", cmd)
        idx = cmd.index("--osv-memory-age-limit")
        self.assertEqual(cmd[idx + 1], "1.5")
        
        self.assertIn("--osv-memory-count-limit", cmd)
        idx = cmd.index("--osv-memory-count-limit")
        self.assertEqual(cmd[idx + 1], "5000")

    @patch.dict(os.environ, {"ODOO_PIDFILE": "/var/run/odoo.pid"})
    def test_pidfile_flag(self):
        """Test --pidfile flag is added when ODOO_PIDFILE is set."""
        cmd = build_odoo_command([])
        self.assertIn("--pidfile", cmd)
        idx = cmd.index("--pidfile")
        self.assertEqual(cmd[idx + 1], "/var/run/odoo.pid")

    @patch.dict(os.environ, {"ODOO_PG_PATH": "/opt/postgresql/bin"})
    def test_pg_path_flag(self):
        """Test --pg_path flag is added when ODOO_PG_PATH is set."""
        cmd = build_odoo_command([])
        self.assertIn("--pg_path", cmd)
        idx = cmd.index("--pg_path")
        self.assertEqual(cmd[idx + 1], "/opt/postgresql/bin")

    @patch.dict(os.environ, {"ODOO_REPORTGZ": "true"})
    def test_reportgz_flag(self):
        """Test --reportgz flag is added when ODOO_REPORTGZ is set."""
        cmd = build_odoo_command([])
        self.assertIn("--reportgz", cmd)

    @patch.dict(os.environ, {"ODOO_TEST_ENABLE": "1"})
    def test_test_enable_flag(self):
        """Test --test-enable flag is added when ODOO_TEST_ENABLE is set."""
        cmd = build_odoo_command([])
        self.assertIn("--test-enable", cmd)

    @patch.dict(os.environ, {"ODOO_TIMEZONE": "Europe/Paris"})
    def test_timezone_flag(self):
        """Test --timezone flag is added when ODOO_TIMEZONE is set."""
        cmd = build_odoo_command([])
        self.assertIn("--timezone", cmd)
        idx = cmd.index("--timezone")
        self.assertEqual(cmd[idx + 1], "Europe/Paris")

    @patch.dict(os.environ, {"ODOO_TRANSLATE_MODULES": "sale,purchase,stock"})
    def test_translate_modules_flag(self):
        """Test --translate-modules flag is added when ODOO_TRANSLATE_MODULES is set."""
        cmd = build_odoo_command([])
        self.assertIn("--translate-modules", cmd)
        idx = cmd.index("--translate-modules")
        self.assertEqual(cmd[idx + 1], "sale,purchase,stock")

    @patch.dict(os.environ, {"ODOO_WITHOUT_DEMO": "all"})
    def test_without_demo_flag(self):
        """Test --without-demo flag is added when ODOO_WITHOUT_DEMO is set."""
        cmd = build_odoo_command([])
        self.assertIn("--without-demo", cmd)
        idx = cmd.index("--without-demo")
        self.assertEqual(cmd[idx + 1], "all")

    @patch.dict(os.environ, {
        "ODOO_IMPORT_PARTIAL": "/tmp/import.csv",
        "ODOO_LOG_DB": "log_db",
        "ODOO_OSV_MEMORY_AGE_LIMIT": "2.0",
        "ODOO_OSV_MEMORY_COUNT_LIMIT": "10000",
        "ODOO_PIDFILE": "/var/run/odoo.pid",
        "ODOO_PG_PATH": "/usr/bin",
        "ODOO_REPORTGZ": "yes",
        "ODOO_TEST_ENABLE": "true",
        "ODOO_TIMEZONE": "UTC",
        "ODOO_TRANSLATE_MODULES": "website",
        "ODOO_WITHOUT_DEMO": "sale,purchase"
    })
    def test_all_new_flags_together(self):
        """Test all new flags work together without conflicts."""
        cmd = build_odoo_command([])
        flags = self._extract_flags(cmd)
        
        # Check all flags are present
        expected_flags = {
            "--import-partial",
            "--log-db",
            "--osv-memory-age-limit",
            "--osv-memory-count-limit",
            "--pidfile",
            "--pg_path",
            "--reportgz",
            "--test-enable",
            "--timezone",
            "--translate-modules",
            "--without-demo",
        }
        
        for flag in expected_flags:
            self.assertIn(flag, flags, f"Missing flag: {flag}")

    @patch.dict(os.environ, {
        "ODOO_IMPORT_PARTIAL": "",
        "ODOO_LOG_DB": "",
        "ODOO_OSV_MEMORY_AGE_LIMIT": "",
        "ODOO_OSV_MEMORY_COUNT_LIMIT": "",
        "ODOO_PIDFILE": "",
        "ODOO_PG_PATH": "",
        "ODOO_REPORTGZ": "",
        "ODOO_TEST_ENABLE": "",
        "ODOO_TIMEZONE": "",
        "ODOO_TRANSLATE_MODULES": "",
        "ODOO_WITHOUT_DEMO": ""
    })
    def test_flags_not_added_when_env_empty(self):
        """Test flags are not added when environment variables are empty."""
        cmd = build_odoo_command([])
        flags = self._extract_flags(cmd)
        
        # Check none of the new flags are present
        unexpected_flags = {
            "--import-partial",
            "--log-db",
            "--osv-memory-age-limit",
            "--osv-memory-count-limit",
            "--pidfile",
            "--pg_path",
            "--reportgz",
            "--test-enable",
            "--timezone",
            "--translate-modules",
            "--without-demo",
        }
        
        for flag in unexpected_flags:
            self.assertNotIn(flag, flags, f"Unexpected flag found: {flag}")


if __name__ == "__main__":
    unittest.main()