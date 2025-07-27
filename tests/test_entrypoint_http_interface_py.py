"""Tests covering *compute_http_interface* helper.

The function must:

1. Respect the hard-coded rules for versions < 17 and ≥ 17.
2. Fall back to automatic detection when the *version* argument is *None*
   or cannot be parsed, using the output of ``odoo --version``.
3. Return the conservative IPv4 wildcard when auto-detection fails.
"""

from __future__ import annotations

import subprocess

import entrypoint as ep


def test_explicit_versions() -> None:  # noqa: D401 – imperative mood
    """Helper must honour explicit major versions passed by the caller."""

    assert ep.compute_http_interface(16) == "0.0.0.0"
    assert ep.compute_http_interface("16") == "0.0.0.0"
    assert ep.compute_http_interface(17) == "::"
    assert ep.compute_http_interface("18") == "::"


def test_auto_detection_success(monkeypatch):  # noqa: D401
    """When *version* is invalid the helper should call *odoo --version*."""

    # Stub *subprocess.check_output* to simulate a 17.x banner.
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda cmd, **kwargs: "odoo 17.0\n",
        raising=True,
    )

    # Pass *None* so that the function triggers auto-detection.
    assert ep.compute_http_interface(None) == "::"

    # Also works with an un-parsable value.
    assert ep.compute_http_interface("garbage") == "::"


def test_auto_detection_failure(monkeypatch):  # noqa: D401
    """Failure to auto-detect must fall back to the IPv4 wildcard."""

    # Simulate a missing binary which raises *FileNotFoundError*.
    def _raise(*_a, **_kw):  # noqa: D401 – helper stub
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "check_output", _raise, raising=True)

    assert ep.compute_http_interface(None) == "0.0.0.0"

