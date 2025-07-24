"""Package marker for *entrypoint* namespace."""

from importlib import import_module as _imp

# Re-export the public API of *entrypoint.py* at package level so that tests
# can simply ``import entrypoint``.

_mod = _imp("entrypoint.entrypoint")

for _name in getattr(_mod, "__all__", ()):  # pragma: no cover – dev helper
    globals()[_name] = getattr(_mod, _name)

# Clean-up to avoid leaking helpers
del _imp, _mod, _name

