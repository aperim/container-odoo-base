"""Miscellaneous helper tests for the new Python entrypoint implementation."""

from __future__ import annotations

import entrypoint as ep


# ---------------------------------------------------------------------------
#  parse_blocklist
# ---------------------------------------------------------------------------


def test_parse_blocklist_basic() -> None:
    items = ep.parse_blocklist("a,b c,d")
    assert items == ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
#  option_in_args
# ---------------------------------------------------------------------------


def test_option_in_args_detects_exact_match() -> None:
    assert ep.option_in_args("--test", "--test", "--other", "arg") is True


def test_option_in_args_detects_prefix_form() -> None:
    assert ep.option_in_args("--workers", "--workers", "--workers=5", "--foo=bar") is True


def test_option_in_args_negative() -> None:
    assert ep.option_in_args("--missing", "arg1", "arg2") is False

