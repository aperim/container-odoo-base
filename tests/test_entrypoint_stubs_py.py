"""Tests covering the *stub* helpers in entrypoint.entrypoint.

The goal is **full line coverage** of *entrypoint/entrypoint.py* without
actually implementing routines that would require elevated privileges or
external services (UID/GID mutation, recursive *chown*, database wiping …).

The API contract for those helpers – as documented in *ENTRYPOINT.md* – is
clear: they currently raise :class:`NotImplementedError`.  Exercising the
exception path is enough for coverage while still locking the public
signature so that future refactors cannot silently change it.
"""

from __future__ import annotations

import inspect
from typing import Callable, List

import pytest

import entrypoint as ep


# ---------------------------------------------------------------------------
#  Helpers that must raise *NotImplementedError*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func",
    [
        # apply_runtime_user, fix_permissions and initialise_instance are now implemented
        ep.upgrade_modules,
    ],
)
def test_unimplemented_helpers_raise(func: Callable[..., object]) -> None:  # noqa: D401 – straightforward test
    """Verify that stub helpers currently raise *NotImplementedError*."""

    with pytest.raises(NotImplementedError):
        # Call with *no* parameters; the signature of all those helpers
        # accepts an optional *env* mapping so omitting it is valid.
        func()  # type: ignore[misc]


# ---------------------------------------------------------------------------
#  gather_env – default value integrity
# ---------------------------------------------------------------------------


def test_gather_env_defaults_are_consistent() -> None:  # noqa: D401 – imperative name
    """The helper must populate expected keys with documented defaults."""

    # We import the *real* implementation module to access the TypedDict
    # definition – the *shim* inserted by *entrypoint.__init__* intentionally
    # exposes **only** the public helpers listed in ``__all__``.

    import entrypoint.entrypoint as impl

    env = impl.gather_env({})

    expected_keys: List[str] = [
        name for name in impl.EntrypointEnv.__annotations__.keys()  # type: ignore[attr-defined]
    ]

    # 1. Every expected key is present.
    assert set(env.keys()) == set(expected_keys)

    # 2. A selection of well-known defaults – we do not hard-code the whole
    #    mapping so that the test remains maintainable.
    assert env["POSTGRES_HOST"] == "postgres"
    assert env["POSTGRES_PORT"] == "5432"
    assert env["ODOO_LANGUAGES"].startswith("en_")


# ---------------------------------------------------------------------------
#  option_in_args – validation path
# ---------------------------------------------------------------------------


def test_option_in_args_validates_input() -> None:  # noqa: D401 – imperative name
    """A short option *not* starting with '--' must raise *ValueError*."""

    with pytest.raises(ValueError):
        ep.option_in_args("-w", "-w", "--other")
