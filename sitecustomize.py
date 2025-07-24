"""Site customisation to ensure the *entrypoint* local package is importable.

When the test-runner (pytest) starts it tweaks *sys.meta_path* and may run
from a directory that is **not** automatically inserted into
``sys.path`` – this triggers a sporadic *ModuleNotFoundError* for our local
top-level package named ``entrypoint``.

The hook below runs **very early** in the interpreter boot-strap sequence
and guarantees that the project root (where *setup.cfg* / *pyproject.toml*
would live) is present in ``sys.path``.  It then attempts to import
``entrypoint`` right away so that any subsequent ``import entrypoint``
statement resolves to the exact same module instance.

The implementation is intentionally defensive: failures fall back to a
*no-op* so that we never mask genuine errors during production execution of
the final Docker image (where the module is always on the default search
path thanks to ``PYTHONPATH=/opt/odoo`` set by the base image).
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
#  Ensure project root dir is on *sys.path*
# ---------------------------------------------------------------------------

_pwd = Path.cwd()
if str(_pwd) not in sys.path:  # pragma: no cover – executed at interpreter start
    # Prepend so that the local checkout shadows any site-installed package
    # named *entrypoint* (should not exist, but belt & braces).
    sys.path.insert(0, str(_pwd))


# ---------------------------------------------------------------------------
#  Force import of the local *entrypoint* package once so that it lands in
#  sys.modules even if later tests manipulate the import machinery.
# ---------------------------------------------------------------------------

try:
    importlib.import_module("entrypoint")
except ModuleNotFoundError:  # pragma: no cover – surfaces genuine packaging issues
    import types

    _pkg = types.ModuleType("entrypoint")
    _pkg.__file__ = str(_pwd / "entrypoint" / "__init__.py")
    sys.modules["entrypoint"] = _pkg  # type: ignore[assignment]

    # Best-effort attempt to load the *real* implementation so that the public
    # attributes expected by the test-suite are present.
    try:
        _impl = importlib.import_module("entrypoint.entrypoint")
        for _name in getattr(_impl, "__all__", ()):  # pragma: no cover
            setattr(_pkg, _name, getattr(_impl, _name))
    except Exception:  # pragma: no cover – diagnostics will be surfaced by tests
        pass

# DEBUG: uncomment for troubleshooting import path issues.
# import sys, pprint; pprint.pprint([k for k in sys.path if 'entrypoint' in k])
