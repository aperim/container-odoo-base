"""Simple syntax check for the *entrypoint.sh* script.

This test invokes ``bash -n`` (no-exec) which parses the script without
executing it.  It will fail if the file contains syntax errors such as
unterminated HEREDOCs, mismatched braces, etc.
"""

from pathlib import Path
import subprocess


def test_entrypoint_has_valid_syntax() -> None:
    entrypoint = Path(__file__).resolve().parents[1] / "entrypoint" / "entrypoint.sh"

    subprocess.run(["bash", "-n", str(entrypoint)], check=True)
