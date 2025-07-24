"""Ensure that the entrypoint package is importable and exposes the public API."""


def test_can_import_entrypoint() -> None:
    import importlib

    mod = importlib.import_module("entrypoint")

    # A subset of the API should be present.
    for name in [
        "parse_blocklist",
        "option_in_args",
        "is_blocked_addon",
        "collect_addons",
    ]:
        assert hasattr(mod, name)

