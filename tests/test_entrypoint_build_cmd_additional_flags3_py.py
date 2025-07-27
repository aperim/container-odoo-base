"""Additional flag coverage tests for entrypoint.build_odoo_command.

This suite validates the newly added CLI options that complete the TODO #2
matrix (SMTP support, auto-reload, advanced PostgreSQL limits, list-db, syslog
opt-in …).  Every test isolates **one** environment variable so that failures
remain easy to pin-point if regression occurs.
"""

from __future__ import annotations

from entrypoint import build_odoo_command


def _extract_flags(cmd: list[str]) -> set[str]:
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


def test_smtp_flags(monkeypatch):
    env = {
        "SMTP_SERVER": "mail.local",
        "SMTP_PORT": "2525",
        "SMTP_USER": "mailer",
        "SMTP_PASSWORD": "secret",
        "SMTP_SSL": "true",
    }

    monkeypatch.setenv("SMTP_SERVER", env["SMTP_SERVER"])
    monkeypatch.setenv("SMTP_PORT", env["SMTP_PORT"])
    monkeypatch.setenv("SMTP_USER", env["SMTP_USER"])
    monkeypatch.setenv("SMTP_PASSWORD", env["SMTP_PASSWORD"])
    monkeypatch.setenv("SMTP_SSL", env["SMTP_SSL"])

    cmd = build_odoo_command([])
    flags = _extract_flags(cmd)

    assert "--smtp-server" in flags
    assert "--smtp-port" in flags
    assert "--smtp-user" in flags
    assert "--smtp-password" in flags
    assert "--smtp-ssl" in flags


def test_auto_reload_flag(monkeypatch):
    monkeypatch.setenv("ODOO_AUTO_RELOAD", "1")
    cmd = build_odoo_command([])
    assert "--auto-reload" in cmd


def test_postgres_extra(monkeypatch):
    monkeypatch.setenv("POSTGRES_TEMPLATE", "template_postgis")
    monkeypatch.setenv("POSTGRES_MAXCONN", "256")
    cmd = build_odoo_command([])
    flags = _extract_flags(cmd)
    assert "--db_template" in flags
    assert "--db_maxconn" in flags


def test_list_db(monkeypatch):
    monkeypatch.setenv("ODOO_LIST_DB", "false")
    cmd = build_odoo_command([])
    # the option takes a value just after the flag, so we look for the pair
    assert "--list-db" in cmd
    idx = cmd.index("--list-db")
    assert cmd[idx + 1] == "false"


def test_syslog(monkeypatch):
    monkeypatch.setenv("ODOO_SYSLOG", "yes")
    cmd = build_odoo_command([])
    assert "--syslog" in cmd

