"""Tests for *automatic destroy on failed init* feature.

The historical Bash entry-point executed a *destroy* routine whenever the
initial database scaffolding failed so that the **next** container start
would begin from a clean slate.  The Python port now mirrors that behaviour
by catching errors from the internal Odoo initialization passes, invoking
``destroy_instance`` and retrying *once*.
"""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import entrypoint.entrypoint as ep


def test_initialise_failure_triggers_destroy_then_retry(monkeypatch):  # noqa: D401 – imperative
    """A first failure must call *destroy_instance* then succeed on retry."""

    # ------------------------------------------------------------------
    # 1. Ensure the helper uses a deterministic add-on list so that the Odoo
    #    subprocess is actually invoked.
    # ------------------------------------------------------------------

    monkeypatch.setattr(ep, "collect_addons", lambda *a, **k: ["base", "web"])
    monkeypatch.setattr(ep, "get_addons_paths", lambda _env=None: ["/dummy"])

    # ------------------------------------------------------------------
    # 2. Fake *Path.is_file* so that the code believes the real Odoo binary
    #    exists – otherwise the helper would short-circuit and skip the
    #    *subprocess.run* call we want to capture.
    # ------------------------------------------------------------------

    real_is_file = Path.is_file

    def fake_is_file(self: Path) -> bool:  # noqa: D401 – matches signature
        if str(self) == "/usr/bin/odoo":
            return True
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", fake_is_file, raising=False)

    # ------------------------------------------------------------------
    # 3. Stub *subprocess.run* so that the *first* Odoo invocation fails and
    #    subsequent ones succeed.  All other commands always succeed.
    # ------------------------------------------------------------------

    import subprocess as _sp

    odoo_calls: list[list[str]] = []
    first_fail = True

    def fake_run(cmd, check=True, **_kwargs):  # noqa: D401 – keep signature
        nonlocal first_fail
        if cmd[0] == "/usr/bin/odoo":
            odoo_calls.append(cmd)
            if first_fail:
                first_fail = False
                raise _sp.CalledProcessError(returncode=1, cmd=cmd)
        # Any non-failing invocation returns a dummy CompletedProcess.
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(_sp, "run", fake_run)

    # ------------------------------------------------------------------
    # 4. Track execution of *destroy_instance*.
    # ------------------------------------------------------------------

    destroyed = False

    def fake_destroy(_env):  # noqa: D401 – minimal stub
        nonlocal destroyed
        destroyed = True

    monkeypatch.setattr(ep, "destroy_instance", fake_destroy)

    # ------------------------------------------------------------------
    # 5. Prevent the helper from writing under /etc/odoo which would fail
    #    in the unprivileged CI environment.
    # ------------------------------------------------------------------

    monkeypatch.setattr(Path, "mkdir", lambda self, *a, **k: None, raising=False)
    monkeypatch.setattr(Path, "touch", lambda self, *a, **k: None, raising=False)
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None, raising=False)

    # ------------------------------------------------------------------
    # 6. Execute – the routine should *not* raise even though the first Odoo
    #    pass fails because it retries after destroying.
    # ------------------------------------------------------------------

    ep.initialise_instance({})

    # ------------------------------------------------------------------
    # 7. Assertions – the destroy stub was called and at least two Odoo
    #    invocations occurred (one failure + one success).
    # ------------------------------------------------------------------

    assert destroyed is True, "destroy_instance must be invoked on failure"
    assert len(odoo_calls) >= 2, "Odoo should be executed again after destroy"

