"""Tests for collect_addons and related helpers in entrypoint.sh.

The entrypoint is a Bash script.  We interact with its functions by spawning
`bash -c` subprocesses that source the script and execute the desired shell
code.  Each helper below builds a tiny shell snippet, executes it and captures
stdout so that we can perform assertions from Python.

Only functions that are side-effect-free and do not need external services are
covered here (e.g. *collect_addons*, *is_blocked_addon*).  Heavyweight
functions that manipulate databases or invoke Odoo itself remain outside the
scope of unit tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT_DIR / "entrypoint" / "entrypoint.sh"


def _run_bash(snippet: str, env: dict[str, str] | None = None) -> str:
    """Run *snippet* in a Bash shell that has sourced *entrypoint.sh*.

    Returns captured **stdout**; raises ``CalledProcessError`` on non-zero
    exit.
    """

    # Pull in only the definitions we need so the full entrypoint logic (which
    # starts services, acquires locks, etc.) is **not** executed during unit
    # tests.  We rely on awk to extract the bodies of the helper functions we
    # are interested in.

    awk_cmd = (
        r"awk '/^is_blocked_addon\(/,/^}/;/^collect_addons\(/,/^}/' "
        f"{ENTRYPOINT}"
    )

    full_script = f"""
        set -euo pipefail
        # minimal stubs expected by helper functions
        log() {{ :; }}
        readonly DEFAULT_ODOO_LANGUAGES="en_AU,en_US"

        eval "$({awk_cmd})"

        {snippet}
    """

    result = subprocess.run(
        ["bash", "-c", full_script],
        env={**os.environ, **(env or {})},
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
#  is_blocked_addon
# ---------------------------------------------------------------------------


def test_is_blocked_addon_positive() -> None:
    """Module name that matches regex in blocklist must return success."""

    snippet = """
        if is_blocked_addon "sale_extra" "^sale_.*"; then
            echo "yes"
        else
            echo "no"
        fi
    """
    out = _run_bash(snippet)
    assert out == "yes"


def test_is_blocked_addon_negative() -> None:
    """Module name not matching any pattern is *not* blocked."""

    snippet = """
        if is_blocked_addon "crm" "^sale_.*"; then
            echo "yes"
        else
            echo "no"
        fi
    """
    out = _run_bash(snippet)
    assert out == "no"


# ---------------------------------------------------------------------------
#  collect_addons – basic inclusion / exclusion and deduplication
# ---------------------------------------------------------------------------


def _make_addon(path: Path, name: str, manifest: dict | None = None) -> Path:
    """Create a minimal Odoo addon directory with *__manifest__.py*."""

    mod_path = path / name
    mod_path.mkdir(parents=True)
    # The dependency resolver simply performs ``ast.literal_eval`` on the file
    # content.  Therefore we write a **raw dict literal** – no variables, no
    # Python code.  Keep it minimal.
    (mod_path / "__manifest__.py").write_text(
        json.dumps(manifest or {}),
        encoding="utf-8",
    )
    return mod_path


def test_collect_addons_blocklist_and_dedup(tmp_path: Path) -> None:
    """Modules in the blocklist are skipped and duplicates removed."""

    src1 = tmp_path / "src1"
    src2 = tmp_path / "src2"
    src1.mkdir()
    src2.mkdir()

    _make_addon(src1, "sale_management")
    _make_addon(src2, "sale_management")  # duplicate in another path
    _make_addon(src1, "crm")

    snippet = rf"""
        declare -a result
        collect_addons result "{src1}" "{src2}"
        printf '%s\n' "${{result[@]}}"
    """

    env = {"ODOO_ADDON_INIT_BLOCKLIST": "^sale_.*"}
    modules = _run_bash(snippet, env=env).splitlines()

    # Expect only 'crm' once (sale_* blocked, duplicate removed)
    assert modules == ["crm"]


# ---------------------------------------------------------------------------
#  collect_addons – localisation filtering
# ---------------------------------------------------------------------------


def test_collect_addons_localisation_filter(tmp_path: Path) -> None:
    """Only localisation modules matching language codes are kept."""

    src = tmp_path / "src"
    src.mkdir()

    _make_addon(src, "l10n_au")
    _make_addon(src, "l10n_de")
    _make_addon(src, "base")

    snippet = rf"""
        declare -a res
        collect_addons res "{src}"
        printf '%s\n' "${{res[@]}}"
    """

    env = {"ODOO_LANGUAGES": "en_AU,en_US"}
    modules = _run_bash(snippet, env=env).splitlines()

    # l10n_au should be included, l10n_de excluded; base always present.
    assert modules == ["l10n_au", "base"] or modules == ["base", "l10n_au"]


# ---------------------------------------------------------------------------
#  collect_addons – dependency ordering
# ---------------------------------------------------------------------------


def test_collect_addons_dependency_order(tmp_path: Path) -> None:
    """Module list must respect manifest 'depends' relationships."""

    src = tmp_path / "src"
    src.mkdir()

    # B has no depends; A depends on B; C depends on A (B <- A <- C)
    _make_addon(src, "module_b", {"depends": []})
    _make_addon(src, "module_a", {"depends": ["module_b"]})
    _make_addon(src, "module_c", {"depends": ["module_a"]})

    snippet = rf"""
        declare -a res
        collect_addons res "{src}"
        printf '%s\n' "${{res[@]}}"
    """

    ordered = _run_bash(snippet).splitlines()

    # Ensure topological order (b before a before c)
    assert ordered.index("module_b") < ordered.index("module_a") < ordered.index(
        "module_c"
    )
