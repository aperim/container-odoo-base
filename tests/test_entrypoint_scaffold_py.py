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
        # v0.2 additions
        "is_custom_command",
        "apply_runtime_user",
        "fix_permissions",
        "update_needed",
        "compute_workers",
        "compute_http_interface",
        "get_addons_paths",
    ],
)
def test_symbol_present(name: str) -> None:
    assert hasattr(ep, name), f"{name} should be exported in __all__"


# ---------------------------------------------------------------------------
#  Newly added helpers in v0.2 – presence & basic behaviour
# ---------------------------------------------------------------------------


def test_is_custom_command_detection() -> None:
    assert ep.is_custom_command(["bash"]) is True
    assert ep.is_custom_command(["odoo"]) is False
    assert ep.is_custom_command(["--log-level", "debug"]) is False


def test_compute_workers_formula() -> None:
    assert ep.compute_workers(1) == 1  # 2*1-1 = 1
    assert ep.compute_workers(4) == 7  # 2*4-1 = 7


def test_compute_http_interface() -> None:
    assert ep.compute_http_interface(16) == "0.0.0.0"
    assert ep.compute_http_interface(17) == "::"
    # Garbage input defaults to legacy IPv4
    assert ep.compute_http_interface("not-a-number") == "0.0.0.0"


def test_get_addons_paths_returns_list() -> None:
    paths = ep.get_addons_paths({})  # type: ignore[arg-type]
    assert isinstance(paths, list)


# ---------------------------------------------------------------------------
#  gather_env – just smoke-test defaults
# ---------------------------------------------------------------------------


def test_gather_env_defaults() -> None:
    env = ep.gather_env({})
    assert env["POSTGRES_HOST"] == "postgres"
    assert env["POSTGRES_PORT"] == "5432"
    assert env["ODOO_LANGUAGES"].startswith("en_")  # basic sanity


# ---------------------------------------------------------------------------
#  Placeholder helpers removed – no longer applicable
# ---------------------------------------------------------------------------
