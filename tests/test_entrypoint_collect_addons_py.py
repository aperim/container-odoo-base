"""Tests for *collect_addons* and related helpers now implemented in Python.

The original unit-tests interacted with the Bash functions through
sub-processes.  In the new Python implementation we can call the helpers
directly which makes the tests faster and easier to reason about.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import entrypoint as ep


# ---------------------------------------------------------------------------
#  is_blocked_addon
# ---------------------------------------------------------------------------


def test_is_blocked_addon_positive() -> None:
    assert ep.is_blocked_addon("sale_extra", r"^sale_.*") is True


def test_is_blocked_addon_negative() -> None:
    assert ep.is_blocked_addon("crm", r"^sale_.*") is False


# ---------------------------------------------------------------------------
#  Helpers for building minimal add-ons on the fly
# ---------------------------------------------------------------------------


def _make_addon(path: Path, name: str, manifest: dict | None = None) -> Path:
    mod = path / name
    mod.mkdir(parents=True)
    (mod / "__manifest__.py").write_text(json.dumps(manifest or {}), "utf-8")
    return mod


# ---------------------------------------------------------------------------
#  collect_addons – block-list & deduplication
# ---------------------------------------------------------------------------


def test_collect_addons_blocklist_and_dedup(tmp_path: Path) -> None:
    src1 = tmp_path / "src1"
    src2 = tmp_path / "src2"
    src1.mkdir()
    src2.mkdir()

    _make_addon(src1, "sale_management")
    _make_addon(src2, "sale_management")  # duplicate in another path
    _make_addon(src1, "crm")

    mods = ep.collect_addons(
        [src1, src2],
        blocklist_patterns=[r"^sale_.*"],
    )

    assert mods == ["crm"]


# ---------------------------------------------------------------------------
#  collect_addons – localisation filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("langs, expected", [
    ("en_AU,en_US", {"l10n_au", "base"}),
    ("en_US", {"base"}),
])
def test_collect_addons_localisation_filter(tmp_path: Path, langs: str, expected: set[str]) -> None:
    src = tmp_path / "src"
    src.mkdir()

    _make_addon(src, "l10n_au")
    _make_addon(src, "l10n_de")
    _make_addon(src, "base")

    result = set(
        ep.collect_addons(
            [src],
            languages=langs.split(","),
        )
    )

    assert expected.issubset(result)
    assert "l10n_de" not in result


# ---------------------------------------------------------------------------
#  collect_addons – dependency ordering
# ---------------------------------------------------------------------------


def test_collect_addons_dependency_order(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()

    # Module chain: B <- A <- C
    _make_addon(src, "module_b", {"depends": []})
    _make_addon(src, "module_a", {"depends": ["module_b"]})
    _make_addon(src, "module_c", {"depends": ["module_a"]})

    ordered = ep.collect_addons([src])

    assert ordered.index("module_b") < ordered.index("module_a") < ordered.index(
        "module_c"
    )

