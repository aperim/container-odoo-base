"""Unit tests for the *ODOO_EXTRA_FLAGS* escape hatch (open-issue #2)."""

from __future__ import annotations

import shlex

import entrypoint as ep


def test_extra_flags_appended_at_end() -> None:  # noqa: D401
    """Flags from *ODOO_EXTRA_FLAGS* must appear **after** automatic ones."""

    env = {
        "ODOO_EXTRA_FLAGS": "--my-flag=value --another",
    }

    cmd = ep.build_odoo_command([], env=env)

    # The command always starts with the binary and "server" keyword.
    assert cmd[:2] == ["/usr/bin/odoo", "server"]

    # Extract the tail of the command and compare with the expected split.
    extras = shlex.split(env["ODOO_EXTRA_FLAGS"])
    assert cmd[-len(extras) :] == extras  # noqa: WPS221 – slice readability
