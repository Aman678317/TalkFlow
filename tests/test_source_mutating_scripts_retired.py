"""The stale one-shot codemods (day-2 map finding O-12) must stay retired.

Evidence behind the retirement (re-checked on ecf4dc5, 2026-10-22, in a clean
detached worktree — both scripts ran, produced their verdicts, and left zero
byte of diff):

``scripts/apply_phase4_hardening.py`` was a one-shot "Phase 4 realtime
security hardening" codemod. Every guarded pattern on today's canonical
tree matches nothing ("already patched or pattern mismatch"), and the two
blocks that rewrite unconditionally — ``app/realtime/ws.py`` and
``app/services/meeting_service.py`` — read the file, run ``str.replace``
on patterns that match nothing, write the file back and print "Patched"
**regardless** (zero-byte rewrite, success banner). ``str.replace`` has no
"only the first occurrence after line 135" (its comment's claim): the
moment a pattern drifts into matching somewhere unintended, the next run
silently stale-patches canonical code and still reports success.

``scripts/update_cross_tests.py`` appends a test block to
``tests/test_cross_tenant_security.py`` guarded by ``if
"<one sentinel name>" not in orig``. On the current tree it prints
"Tests already present", but the appended block still carries pre-#124
v2/v3 assumptions — if that sentinel test is ever renamed, the next run
injects ~50 lines of stale tests straight into the suite CI runs.

Neither is referenced by anything — the ownership map's own matrix is the
only mention. Pinned here: the files stay deleted.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_the_source_mutating_codemods_stay_retired():
    for name in ("apply_phase4_hardening.py", "update_cross_tests.py"):
        assert not (REPO / "scripts" / name).exists(), (
            f"{name} was retired (O-12): a one-shot codemod whose report of "
            "success is unconditional and whose patching becomes stale the "
            "moment the canonical tree moves again. Its history lives in "
            "git; do not resurrect it")
