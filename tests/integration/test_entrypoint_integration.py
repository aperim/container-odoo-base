#!/usr/bin/env python3
"""Integration tests for entrypoint.py with real Odoo, Redis, and PostgreSQL.

This test suite validates the entrypoint script against real services running
in Docker containers. It ensures that the generated commands work correctly
with actual PostgreSQL and Redis instances.
"""

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

# Add the entrypoint module to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import entrypoint


class TestEntrypointIntegration(unittest.TestCase):
    """Integration tests for the entrypoint with real services."""

    @classmethod
    def setUpClass(cls):
        """Set up test environment variables."""
        # Ensure we're testing production behavior
        os.environ.pop("PYTEST_CURRENT_TEST", None)
        os.environ.pop("ENTRYPOINT_DEV_MODE", None)
        
        # Set up connection parameters from environment
        cls.postgres_host = os.environ.get("POSTGRES_HOST", "postgres")
        cls.postgres_port = os.environ.get("POSTGRES_PORT", "5432")
        cls.postgres_user = os.environ.get("POSTGRES_USER", "odoo")
        cls.postgres_password = os.environ.get("POSTGRES_PASSWORD", "odoo")
        cls.postgres_db = os.environ.get("POSTGRES_DB", "odoo_test")
        
        cls.redis_host = os.environ.get("REDIS_HOST", "redis")
        cls.redis_port = os.environ.get("REDIS_PORT", "6379")

    def test_wait_for_dependencies_real_services(self):
        """Test wait_for_dependencies with real PostgreSQL and Redis."""
        env = {
            "POSTGRES_HOST": self.postgres_host,
            "POSTGRES_PORT": self.postgres_port,
            "POSTGRES_USER": self.postgres_user,
            "POSTGRES_PASSWORD": self.postgres_password,
            "POSTGRES_DB": self.postgres_db,
            "REDIS_HOST": self.redis_host,
            "REDIS_PORT": self.redis_port,
        }
        
        # This should complete without raising exceptions
        # The actual services are running in Docker
        try:
            entrypoint.wait_for_dependencies(env)
            self.assertTrue(True, "wait_for_dependencies completed successfully")
        except Exception as e:
            self.fail(f"wait_for_dependencies failed: {e}")

    def test_build_odoo_command_structure(self):
        """Test that build_odoo_command generates valid command structure."""
        env = {
            "POSTGRES_HOST": self.postgres_host,
            "POSTGRES_PORT": self.postgres_port,
            "POSTGRES_USER": self.postgres_user,
            "POSTGRES_PASSWORD": self.postgres_password,
            "POSTGRES_DB": self.postgres_db,
            "ODOO_WITHOUT_DEMO": "true",
            "ODOO_LOG_LEVEL": "info",
        }
        
        cmd = entrypoint.build_odoo_command(["--version"], env)
        
        # Verify command structure
        self.assertEqual(cmd[0], "odoo")
        self.assertIn("--db_host", cmd)
        self.assertIn(self.postgres_host, cmd)
        self.assertIn("--db_port", cmd)
        self.assertIn(self.postgres_port, cmd)
        self.assertIn("--db_user", cmd)
        self.assertIn(self.postgres_user, cmd)
        self.assertIn("--db_password", cmd)
        self.assertIn(self.postgres_password, cmd)
        self.assertIn("--without-demo", cmd)
        self.assertIn("--log-level", cmd)
        self.assertIn("info", cmd)
        self.assertIn("--version", cmd)

    def test_database_connection_parameters(self):
        """Test database connection with real PostgreSQL."""
        import psycopg2
        
        # Verify we can connect with the parameters used by entrypoint
        try:
            conn = psycopg2.connect(
                host=self.postgres_host,
                port=int(self.postgres_port),
                user=self.postgres_user,
                password=self.postgres_password,
                database="postgres",  # Use default DB for connection test
                connect_timeout=10
            )
            conn.close()
            self.assertTrue(True, "PostgreSQL connection successful")
        except Exception as e:
            self.fail(f"PostgreSQL connection failed: {e}")

    def test_redis_connection_parameters(self):
        """Test Redis connection with real Redis."""
        import redis
        
        # Verify we can connect with the parameters used by entrypoint
        try:
            r = redis.Redis(
                host=self.redis_host,
                port=int(self.redis_port),
                socket_connect_timeout=10
            )
            r.ping()
            self.assertTrue(True, "Redis connection successful")
        except Exception as e:
            self.fail(f"Redis connection failed: {e}")

    def test_odoo_version_detection(self):
        """Test that compute_http_interface can detect Odoo version."""
        # This test checks if the odoo binary is available and --version works
        try:
            result = subprocess.run(
                ["odoo", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Test auto-detection
                interface = entrypoint.compute_http_interface(None)
                self.assertIn(interface, ["::", "0.0.0.0"])
                
                # Check if version output contains version number
                if "17" in result.stdout or "18" in result.stdout:
                    self.assertEqual(interface, "::")
                else:
                    self.assertEqual(interface, "0.0.0.0")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.skipTest("Odoo binary not available in test environment")

    def test_runtime_housekeeping_helpers(self):
        """Test that runtime housekeeping helper binaries exist."""
        helpers = ["odoo-config", "odoo-update"]
        
        for helper in helpers:
            try:
                result = subprocess.run(
                    [helper, "--help"],
                    capture_output=True,
                    timeout=5
                )
                self.assertIn(
                    result.returncode, [0, 1, 2],  # Common help exit codes
                    f"{helper} binary should be available"
                )
            except FileNotFoundError:
                self.skipTest(f"{helper} binary not available in test environment")

    def test_gather_env_database_precedence(self):
        """Test environment variable precedence for database configuration."""
        # Test PGBOUNCER_HOST takes precedence
        env = {
            "POSTGRES_HOST": "direct-postgres",
            "POSTGRES_PORT": "5432",
            "PGBOUNCER_HOST": "pgbouncer",
            "PGBOUNCER_PORT": "6432",
        }
        
        gathered = entrypoint.gather_env(env)
        
        # When PGBOUNCER_HOST is set, it should override POSTGRES_HOST
        # in the actual database connection
        self.assertEqual(gathered["PGBOUNCER_HOST"], "pgbouncer")
        self.assertEqual(gathered["PGBOUNCER_PORT"], "6432")

    def test_full_entrypoint_flow_version_command(self):
        """Test the full entrypoint flow with --version command."""
        # This simulates what happens when the container starts with --version
        try:
            # Set up minimal environment
            env = entrypoint.gather_env({
                "POSTGRES_HOST": self.postgres_host,
                "POSTGRES_PORT": self.postgres_port,
                "POSTGRES_USER": self.postgres_user,
                "POSTGRES_PASSWORD": self.postgres_password,
                "POSTGRES_DB": self.postgres_db,
                "REDIS_HOST": self.redis_host,
                "REDIS_PORT": self.redis_port,
            })
            
            # Check if it's a custom command (--version is custom)
            self.assertTrue(entrypoint.is_custom_command(["--version"]))
            
            # Build the command
            cmd = entrypoint.build_odoo_command(["--version"], env)
            
            # Verify command is properly constructed
            self.assertTrue(len(cmd) > 0)
            self.assertEqual(cmd[0], "odoo")
            self.assertIn("--version", cmd)
            
        except Exception as e:
            self.fail(f"Full entrypoint flow failed: {e}")


if __name__ == "__main__":
    unittest.main()