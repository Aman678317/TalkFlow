"""P4 §E5 — durable escalation retention: the §E2 audit rows get a sweep.

The durable escalation transport (§E2) keeps RESOLVED ticket rows as audit
history forever. This suite locks the sweep contract added to the retention
service:

- only RESOLVED rows whose RESOLUTION aged past ``retention_escalation_days``
  are deleted (anchored on resolution time, not creation time);
- an UNRESOLVED row is never swept — unresolved rows are the restart
  rehydrate working set (§E2) and their ages mean nothing while the ticket
  waits;
- ``retention_escalation_days = 0`` keeps everything (the config's own
  "0 = forever" contract);
- the counts dict always carries the ``escalations`` bucket (observability).

Settings are forced on every module-owned binding (the post-reload bleed
convention) so lane ordering cannot flip the window.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture()
def _force_window(monkeypatch):
    """`retention_escalation_days = 30` on every module-owned settings
    binding (app.config + retention_service)."""
    import app.config as cfg_mod
    import app.services.retention_service as ret_svc

    for holder in (ret_svc.settings, cfg_mod.settings):
        monkeypatch.setattr(holder, "retention_escalation_days", 30,
                            raising=True)


async def _seed_rows(org_id: str) -> str:
    """One old resolved ticket, one recent resolved ticket, one old-but-
    unresolved ticket (claimed, waiting). Returns the call_sid stem used."""
    from app.db import models as M
    from app.db.session import db_session

    now = datetime.now(UTC)
    stem = uuid.uuid4().hex[:12]
    async with db_session() as db:
        db.add(M.AgentEscalation(
            org_id=uuid.UUID(org_id),
            ticket_id=f"t-old-{stem}",
            call_sid=f"talkflow-{stem}-a",
            reason="opt_out", summary=None, turns=1,
            resolved_by="agent-1",
            resolved_at=now - timedelta(days=40),          # past the window
        ))
        db.add(M.AgentEscalation(
            org_id=uuid.UUID(org_id),
            ticket_id=f"t-recent-{stem}",
            call_sid=f"talkflow-{stem}-b",
            reason="human_request", summary=None, turns=2,
            resolved_by="agent-1",
            resolved_at=now - timedelta(days=1),           # inside the window
        ))
        db.add(M.AgentEscalation(
            org_id=uuid.UUID(org_id),
            ticket_id=f"t-waiting-{stem}",
            call_sid=f"talkflow-{stem}-c",
            reason="low_stt_confidence", summary=None, turns=1,
            claimed_by="agent-2",
            claimed_at=now - timedelta(days=5),
            resolved_at=None,                               # FOREVER untouchable
        ))
        await db.commit()
    return stem


async def _escalation_rows() -> dict[str, bool]:
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        rows = (await db.execute(select(M.AgentEscalation))).scalars().all()
    return {r.ticket_id: (r.resolved_at is not None) for r in rows}


async def test_sweep_deletes_only_past_window_resolved_rows(
        services_app_client, user, _force_window):
    from app.db.session import db_session
    from app.services import retention_service

    stem = await _seed_rows(user["org_id"])

    async with db_session() as db:
        counts = await retention_service.sweep(db)

    assert counts["escalations"] == 1                  # exactly the old one
    survivors = await _escalation_rows()
    assert f"t-old-{stem}" not in survivors            # past window: swept
    assert survivors[f"t-recent-{stem}"] is True       # in-window: kept
    assert survivors[f"t-waiting-{stem}"] is False     # unresolved: kept


async def test_zero_window_keeps_everything_forever(
        services_app_client, user, monkeypatch):
    import app.config as cfg_mod
    import app.services.retention_service as ret_svc

    for holder in (ret_svc.settings, cfg_mod.settings):
        monkeypatch.setattr(holder, "retention_escalation_days", 0,
                            raising=True)

    from app.db.session import db_session
    from app.services import retention_service

    stem = await _seed_rows(user["org_id"])

    async with db_session() as db:
        counts = await retention_service.sweep(db)

    assert counts["escalations"] == 0
    mine = {t: ok for (t, ok) in (await _escalation_rows()).items()
            if t.endswith(stem)}
    assert len(mine) == 3                              # my rows: none swept
    assert mine[f"t-old-{stem}"] is True    # old RESOLVED row kept, still resolved


async def test_counts_bucket_shape_is_stable(services_app_client, user,
                                             _force_window):
    from app.db.session import db_session
    from app.services import retention_service

    async with db_session() as db:
        counts = await retention_service.sweep(db)

    assert set(counts) == {"audio_objects", "documents", "usage",
                           "expired_tokens", "escalations"}
