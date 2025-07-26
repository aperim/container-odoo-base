"""Tests for the :pyfunc:`entrypoint.entrypoint.main` helper.

The *real* implementation never returns because it ultimately replaces the
current process image with either a user-supplied custom command or the final
``/usr/bin/odoo server`` invocation.  For test-purposes we therefore monkey-
patch the various *os.exec* functions so that the control flow can continue
inside the Python interpreter while still asserting that the correct
arguments would have been used.
"""

from __future__ import annotations

from pathlib import Path

import builtins
import types

import pytest

import entrypoint.entrypoint as ep


@pytest.mark.parametrize(
    "argv",
    [
        ["ls"],
        ["bash", "-c", "echo hi"],
    ],
)
def test_main_execs_custom_command(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    """Any *first* argument not recognised as Odoo must be exec'ed verbatim."""

    captured: dict[str, list[str]] = {}

    def fake_execvp(cmd: str, args: list[str]) -> None:  # noqa: D401 – nested helper
        captured["cmd"] = [cmd, *args]
        raise SystemExit(0)  # prevent *real* exec, emulate successful replace

    monkeypatch.setattr(ep.os, "execvp", fake_execvp)

    with pytest.raises(SystemExit):
        ep.main(argv)

    # The helper must forward the exact argument list it received – paying
    # attention to the `execvp` convention where *argv[0]* is repeated as
    # the *file* parameter.
    assert captured["cmd"][0] == argv[0]
    assert captured["cmd"][1:] == argv


def test_main_regular_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no custom command is supplied the classic Odoo boot path runs."""

    calls: list[str] = []

    # Replace heavy-weight helpers with no-ops that simply record their call.
    for name in (
        "apply_runtime_user",
        "fix_permissions",
        "wait_for_dependencies",
        "destroy_instance",
        "initialise_instance",
        "upgrade_modules",
        "drop_privileges",
    ):

        monkeypatch.setattr(ep, name, lambda *_args, __name=name: calls.append(__name))

    # Fake build_odoo_command so we control the command that would be exec'ed.
    cmd_stub = ["/usr/bin/odoo", "server", "--dummy"]
    monkeypatch.setattr(ep, "build_odoo_command", lambda *_a, **_kw: cmd_stub)

    # Ensure the test environment does *not* attempt to exec
    monkeypatch.setattr(Path, "is_file", lambda self: False)  # type: ignore[arg-type]

    monkeypatch.setattr(
        ep.os,
        "execv",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("execv should not be reached")),
    )

    # Also shield os.execvp in case the flow accidentally categorises the
    # command as *custom*.
    monkeypatch.setattr(
        ep.os,
        "execvp",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("execvp should not be reached")),
    )

    # Patch Path.exists so that no semaphore files are considered present.
    monkeypatch.setattr(Path, "exists", lambda self: False)  # type: ignore[arg-type]

    # Execute – should complete normally (no SystemExit) and call every helper.
    ep.main(["--log-level", "debug"])

    # All mandatory helpers must have been invoked exactly once.
    assert calls == [
        "apply_runtime_user",
        "fix_permissions",
        "wait_for_dependencies",
        "initialise_instance",
    ]
