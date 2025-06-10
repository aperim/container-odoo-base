"""Additional tests for smaller helper functions in entrypoint.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT_DIR / "entrypoint" / "entrypoint.sh"


def _run_bash(snippet: str) -> str:
    awk_cmd = (
        r"awk '/^parse_blocklist\(/,/^}/;/^option_in_args\(/,/^}/' "
        f"{ENTRYPOINT}"
    )

    script = f"""
        set -euo pipefail
        log() {{ :; }}
        eval "$({awk_cmd})"
        {snippet}
    """

    res = subprocess.run(
        ["bash", "-c", script],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return res.stdout.strip()


# ---------------------------------------------------------------------------
# parse_blocklist
# ---------------------------------------------------------------------------


def test_parse_blocklist_basic() -> None:
    snippet = """
        parse_blocklist 'a,b c,d' | tr ' ' '\n'
    """
    items = _run_bash(snippet).splitlines()
    assert items == ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
# option_in_args
# ---------------------------------------------------------------------------


def test_option_in_args_detects_exact_match() -> None:
    snippet = """
        if option_in_args --test --test --other arg; then echo yes; else echo no; fi
    """
    assert _run_bash(snippet) == "yes"


def test_option_in_args_detects_prefix_form() -> None:
    snippet = """
        if option_in_args --workers --workers=5 --foo=bar; then echo yes; else echo no; fi
    """
    assert _run_bash(snippet) == "yes"


def test_option_in_args_negative() -> None:
    snippet = """
        if option_in_args --missing arg1 arg2; then echo yes; else echo no; fi
    """
    assert _run_bash(snippet) == "no"
