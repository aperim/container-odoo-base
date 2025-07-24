"""Tests for the *is_custom_command* helper.

The predicate is responsible for deciding whether the first CLI argument
should be treated as a **user command** (and therefore executed directly)
or whether the regular *Odoo* start-up sequence must run.  The logic is
simple yet critical as a false positive would skip the whole entry-point
initialisation while a false negative would prevent legitimate custom
commands from working.

The tests below exercise every branch so that the helper contributes to the
overall *100 %* line coverage target set for *entrypoint/entrypoint.py*.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

import pytest

import entrypoint as ep


# ---------------------------------------------------------------------------
#  Helper that temporarily overrides *sys.argv* when needed.
# ---------------------------------------------------------------------------


class _ArgvCtx:
    """Context-manager that swaps *sys.argv* for the duration of the *with*."""

    def __init__(self, argv: List[str]):
        self._new = argv
        self._orig = None

    def __enter__(self):  # noqa: D401 – imperative mood
        import sys

        self._orig = sys.argv[:]
        sys.argv[:] = self._new

    def __exit__(self, exc_type, exc, tb):  # noqa: D401 – imperative mood
        import sys

        sys.argv[:] = self._orig  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
#  Main assertions – every decision branch must be checked.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv, expected",
    [
        ([], False),  # docker run image  → default Odoo start-up
        (["--log-level=info"], False),  # first token is a long option
        (["odoo"], False),  # recognised binary name
        (["odoo.py"], False),  # historical alias
        (["bash", "-c", "echo hi"], True),  # arbitrary command
    ],
)
def test_is_custom_command(argv: List[str], expected: bool) -> None:  # noqa: D401 – imperative name
    """The helper must correctly classify *argv* sequences.

    Two invocation styles are exercised:

    1. Passing *argv* explicitly so the helper **does not** touch
       ``sys.argv`` at all.
    2. Relying on the implicit path (``argv=None``) where the helper reads
       from the process global.  This guarantees the fallback code path is
       also covered in the statement coverage report.
    """

    # 1. Explicit list – straightforward assertion.
    assert ep.is_custom_command(argv) is expected

    # 2. Implicit path via *sys.argv* – use context-manager so that we do not
    #    leak the modified global state to the rest of the test-suite.
    with _ArgvCtx(["dummy.py", *argv]):
        assert ep.is_custom_command() is expected

