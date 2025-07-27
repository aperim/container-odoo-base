"""Validate `--admin-passwd` default injection by *build_odoo_command*."""

from __future__ import annotations

import entrypoint as ep


def test_build_odoo_command_admin_passwd_injection(monkeypatch):
    """The master password must be forwarded when `$ODOO_ADMIN_PASSWORD` is set."""

    env = {
        "POSTGRES_DB": "db",
        "POSTGRES_HOST": "pg",
        "POSTGRES_PORT": "5432",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "pw",
        "POSTGRES_SSL_MODE": "disable",
        "ODOO_ADMIN_PASSWORD": "secret!",
    }

    # Minimal patch to speed-up test – avoid scanning actual filesystem.
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: [])

    cmd = ep.build_odoo_command([], env=env)

    # Ensure flag *and* value are present and in the expected order.
    assert "--admin-passwd" in cmd
    flag_index = cmd.index("--admin-passwd")
    assert cmd[flag_index + 1] == "secret!"

