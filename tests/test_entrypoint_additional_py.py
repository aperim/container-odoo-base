"""Additional coverage tests for entrypoint.entrypoint.

These unit-tests focus on helper functions that were not exercised by the
previous test-suite.  They stay **pure Python** so that the CI pipeline does
not need any external service (PostgreSQL, Redis, root privileges, …).
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Dict

import importlib

import pytest


# We import the module *lazily* inside each test so that monkey-patches applied
# to module-level globals (e.g. ``ADDON_TIMESTAMP_FILE``) are taken into
# account.  Helpers that do not rely on such globals are nevertheless tested
# through the *public* API to guarantee a realistic call-path.


def test_compute_workers_formula() -> None:  # noqa: D401 – imperative test name
    import entrypoint.entrypoint as ep

    # single CPU must yield **1** worker (bound guard)
    assert ep.compute_workers(1) == 1

    # generic formula check: 4 CPUs → 2 × 4 − 1 = 7 workers
    assert ep.compute_workers(4) == 7


@pytest.mark.parametrize(
    "version, expected",
    [
        (18, "::"),
        (17, "::"),
        (16, "0.0.0.0"),
        ("not-a-number", "0.0.0.0"),
        (None, "0.0.0.0"),
    ],
)
def test_compute_http_interface(version: object, expected: str) -> None:  # noqa: D401
    import entrypoint.entrypoint as ep

    assert ep.compute_http_interface(version) == expected


def _reload_entrypoint() -> ModuleType:  # noqa: D401 – helper
    """Import *entrypoint.entrypoint* freshly.

    Used in tests where we monkey-patch module-level constants.
    """

    # ensure a clean import – remove cached module then import again
    import sys

    sys.modules.pop("entrypoint.entrypoint", None)
    return importlib.import_module("entrypoint.entrypoint")


def test_update_needed_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    """When *build-time* timestamp is empty the helper must short-circuit."""

    ep = _reload_entrypoint()

    env: Dict[str, str] = {"ODOO_ADDONS_TIMESTAMP": "   "}

    # Point the semaphore file somewhere under *tmp_path* even though it will
    # never get read for this test case.
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", tmp_path / ".timestamp")

    assert ep.update_needed(env) is False


def test_update_needed_first_boot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    """Missing semaphore triggers an upgrade on first container start."""

    ep = _reload_entrypoint()

    env = {"ODOO_ADDONS_TIMESTAMP": "1700000000"}

    # ensure the target path does **not** exist
    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", tmp_path / ".missing-file")

    assert ep.update_needed(env) is True


def test_update_needed_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    """Different build vs stored timestamp → upgrade required."""

    ep = _reload_entrypoint()

    stored = tmp_path / ".timestamp"
    stored.write_text("123", encoding="utf-8")

    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", stored)

    env = {"ODOO_ADDONS_TIMESTAMP": "456"}

    assert ep.update_needed(env) is True


def test_update_needed_match(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # noqa: D401
    """Identical timestamps → no upgrade needed."""

    ep = _reload_entrypoint()

    stored = tmp_path / ".timestamp"
    stored.write_text("999", encoding="utf-8")

    monkeypatch.setattr(ep, "ADDON_TIMESTAMP_FILE", stored)

    env = {"ODOO_ADDONS_TIMESTAMP": " 999  "}  # intentional whitespace

    assert ep.update_needed(env) is False


@pytest.mark.parametrize(
    "argv, expected",
    [
        ([], False),
        (["--db_host"], False),
        (["odoo"], False),
        (["odoo.py", "--some-flag"], False),
        (["bash", "-c", "echo hi"], True),
        (["/bin/sh"], True),
    ],
)
def test_is_custom_command(argv: list[str], expected: bool) -> None:  # noqa: D401
    import entrypoint.entrypoint as ep

    assert ep.is_custom_command(argv) is expected


def test_get_addons_paths_order_and_filter(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: D401
    """Directories are returned in deterministic order when they exist."""

    import entrypoint.entrypoint as ep

    existing: set[str] = {
        "/opt/odoo/community",
        "/opt/odoo/extras",
        # intentionally skip enterprise and /mnt/addons to test filtering
    }

    def fake_is_dir(self: Path) -> bool:  # noqa: D401 – helper signature follows Path API
        return str(self) in existing

    monkeypatch.setattr(Path, "is_dir", fake_is_dir, raising=True)

    paths = ep.get_addons_paths()

    assert paths == [
        "/opt/odoo/community",  # enterprise non-existing → skipped
        "/opt/odoo/extras",      # present
        # /mnt/addons absent in *existing* set → skipped
    ]

