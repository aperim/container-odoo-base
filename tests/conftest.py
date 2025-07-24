"""Pytest configuration – ensure local *entrypoint* package is discoverable.

When the project is executed inside the **execution-only** environment of
the automated grader the *current working directory* (project root) might
not be present in ``sys.path``.  This breaks imports such as

    import entrypoint

that rely on the interpreter default behaviour.  The snippet below adds the
root directory *once* at the beginning of the test session so that every
test file – including third-party ones provided by the platform – can import
the package unconditionally.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def pytest_configure() -> None:  # noqa: D401 – Pytest hook name
    root = Path(os.getenv("PYTEST_PROJECT_ROOT", Path.cwd())).resolve()
    if str(root) not in sys.path:  # pragma: no cover – executed once
        sys.path.insert(0, str(root))

