"""Validate that the newly scaffolded high-level helpers exist.

Those tests **do not** check any real behaviour – only that the public
symbols are present and, for the time being, raise
:class:`NotImplementedError`.  This protects the API surface from accidental
removal while future pull-requests progressively implement each function.
"""

from __future__ import annotations

import inspect

import pytest


import entrypoint as ep


@pytest.mark.parametrize(
    "name",
    [
        "gather_env",
        "wait_for_dependencies",
        "destroy_instance",
        "initialise_instance",
        "upgrade_modules",
        "build_odoo_command",
    ],
)
def test_symbol_present(name: str) -> None:
    assert hasattr(ep, name), f"{name} should be exported in __all__"


# ---------------------------------------------------------------------------
#  gather_env – just smoke-test defaults
# ---------------------------------------------------------------------------


def test_gather_env_defaults() -> None:
    env = ep.gather_env({})
    assert env["POSTGRES_HOST"] == "postgres"
    assert env["POSTGRES_PORT"] == "5432"
    assert env["ODOO_LANGUAGES"].startswith("en_")  # basic sanity


# ---------------------------------------------------------------------------
#  Placeholder helpers must raise NotImplemented
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func",
    [
        ep.wait_for_dependencies,
        ep.destroy_instance,
        ep.initialise_instance,
        ep.upgrade_modules,
        ep.build_odoo_command,
    ],
)
def test_placeholder_raises_not_implemented(func) -> None:  # type: ignore[no-any-unbound]
    with pytest.raises(NotImplementedError):
        # Call with no arguments – this keeps the test minimal and avoids the
        # need to construct an EntrypointEnv for now.  The signature accepts
        # *None* so this is perfectly valid.
        if inspect.signature(func).parameters:
            func()  # type: ignore[arg-type, call-arg]
        else:  # pragma: no cover – safeguard for future sig changes
            func()  # noqa: B018 – duplicate call intentional

