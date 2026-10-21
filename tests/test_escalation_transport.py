"""P4 §E2 — durable escalation transport (durable DB copy + boot rehydrate).

Proves the restart-survival seam end to end:

- ``EscalationQueue.rehydrate`` (pure): pending rows restore FIFO-first,
  claimed rows keep their single claim — and a FIFO ``claim(None)`` after a
  restart can NEVER re-claim someone else's ticket (the claimed row leaves
  the pending scan); resolved rows stay out; duplicate ``call_sid`` rows are
  ignored like a live push; bounded ``maxsize`` truncates the restored
  backlog honestly (skipped rows are counted, never faked);
- ``DBEscalationStore`` (real DB): dispatcher-driven
  enqueued/claimed/resolved transitions persist as the durable copy whose
  org mapping comes from the seeded ``CallSession`` — exactly what the
  lifespan wiring uses;
- the restart cycle itself: unresolved rows load back into a FRESH queue,
  resolved rows stay audit-only;
- failure honesty: a ticket whose call has no org mapping reports
  ``agent_escalation_persist_failed`` on the call's own ledger and the live
  queue keeps working.

claim/complete ordering stays the queue's own discipline — this transport
duplicates state, it never re-decides it.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import pytest

from app.telephony.escalation import (
    EVENT_ESCALATION_ENQUEUED,
    EVENT_ESCALATION_PERSIST_FAILED,
    EscalationDispatcher,
    EscalationQueue,
    EscalationRestoreRow,
    rewire_shared_dispatcher,
)
from app.telephony.escalation_store import DBEscalationStore

from test_escalation_hooks import SpySink, escalated_outcome


# --------------------------------------------------------------------------- #
# pure rehydrate semantics (no DB)
# --------------------------------------------------------------------------- #


def _rows(*pairs: tuple[str, str, str | None]) -> list[EscalationRestoreRow]:
    return [
        EscalationRestoreRow(
            ticket_id=tid, call_sid=sid, reason="opt_out",
            summary="wants a human", turns=2, claimed_by=claimed_by)
        for (sid, tid, claimed_by) in pairs
    ]


def test_rehydrate_restores_pending_rows_fifo_first():
    q = EscalationQueue()
    restored = q.rehydrate(_rows(
        ("call-a", "t-a", None), ("call-b", "t-b", None)))
    assert restored == 2
    assert [t.ticket_id for t in q.pending_tickets()] == ["t-a", "t-b"]
    assert q.pending_count() == 2


def test_rehydrate_claimed_row_never_lets_fifo_steal_the_claim():
    q = EscalationQueue()
    restored = q.rehydrate(_rows(
        ("call-a", "t-a", "agent-1"),      # was claimed pre-restart
        ("call-b", "t-b", None)))          # waiting
    assert restored == 2
    # the restored claimed ticket has left the pending scan: a FIFO claim
    # pops the genuinely-pending ticket and may not touch the old claim
    claimed = q.claim("agent-2")
    assert claimed is not None and claimed.ticket_id == "t-b"
    assert q.claimed_by("t-a") == "agent-1"            # claim intact
    assert q.claim("agent-2", ticket_id="t-a") is None  # no stealing
    assert q.complete("t-a", "handled") is True         # claim-gated resolve works


def test_rehydrate_ignores_duplicate_call_sid_rows():
    q = EscalationQueue()
    restored = q.rehydrate(_rows(("call-a", "t-a2", "agent-1")))
    assert restored == 1
    assert q.rehydrate(_rows(("call-a", "t-a3", None))) == 0   # dupe suppressed
    assert q.pending_count() == 0


def test_rehydrate_respects_bounded_capacity():
    q = EscalationQueue(maxsize=1)
    restored = q.rehydrate(_rows(
        ("call-a", "t-a", None), ("call-b", "t-b", None)))
    assert restored == 1                               # second row honestly skipped
    assert q.pending_count() == 1


# --------------------------------------------------------------------------- #
# real DB round-trip through the dispatcher (the lifespan-wired path)
# --------------------------------------------------------------------------- #


async def _seed_call(org_id: str, user_id: str, sid: str) -> None:
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        db.add(M.CallSession(
            org_id=uuid.UUID(org_id), created_by=uuid.UUID(user_id),
            call_sid=sid, from_number="1001", to_number="1002",
            mode="ai_agent", provider="asterisk", status="connected",
        ))
        await db.commit()


async def _durable_row(ticket_id: str):
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        return (await db.execute(select(M.AgentEscalation).where(
            M.AgentEscalation.ticket_id == ticket_id))).scalars().first()


@pytest.fixture()
async def wired_board():
    """A store-wired dispatcher ON the shared singleton, fully restored —
    INCLUDING the durable rows this test persists into the session DB (an
    un-cleaned leftover would be rehydrated by any later lifespan boot, e.g.
    test_production_readiness_hardened's shutdown/boots, and then an unrelated
    honesty test would see stale dynamic queue depths)."""
    from sqlalchemy import delete

    from app.db import models as M
    from app.db.session import db_session
    from app.telephony import escalation as esc_mod

    original = esc_mod._shared
    dispatcher = EscalationDispatcher(
        queue=EscalationQueue(maxsize=16), store=DBEscalationStore())
    rewire_shared_dispatcher(dispatcher)
    yield dispatcher
    rewire_shared_dispatcher(original)
    async with db_session() as db:
        await db.execute(delete(M.AgentEscalation).where(
            M.AgentEscalation.resolved_at.is_(None)))
        await db.commit()


async def test_dispatcher_persists_claim_and_resolution(
        services_app_client, user, wired_board):
    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_call(user["org_id"], user["user_id"], sid)

    sink = SpySink()
    ticket = await wired_board.dispatch(sid, escalated_outcome(), sink)
    assert ticket is not None

    row = await _durable_row(ticket.ticket_id)
    assert row is not None
    assert str(row.org_id) == user["org_id"]           # org mapping from the session
    assert row.call_sid == sid
    assert row.reason == "opt_out"
    assert row.turns == 3
    assert row.claimed_by is None and row.resolved_at is None

    wired_board.queue.claim("agent-9", ticket_id=ticket.ticket_id)
    sink2 = SpySink()
    await wired_board.record_claim(ticket, "agent-9", sink2)
    row = await _durable_row(ticket.ticket_id)
    assert row.claimed_by == "agent-9" and row.claimed_at is not None

    await wired_board.record_resolution(ticket, "handled_by_human", sink2)
    row = await _durable_row(ticket.ticket_id)
    assert row.resolved_by == "agent-9"
    assert row.resolution == "handled_by_human"
    assert row.resolved_at is not None


async def test_rehydrate_cycle_from_durable_rows_is_the_restart_seam(
        services_app_client, user, wired_board):
    """Dispatch two escalated calls, claim one, resolve one — then rebuild
    a FRESH queue from the durable rows exactly as boot would."""
    sid_pending = f"talkflow-{uuid.uuid4()}"
    sid_claimed = f"talkflow-{uuid.uuid4()}"
    sid_resolved = f"talkflow-{uuid.uuid4()}"
    for sid in (sid_pending, sid_claimed, sid_resolved):
        await _seed_call(user["org_id"], user["user_id"], sid)

    tickets: dict[str, Any] = {}
    for sid in (sid_pending, sid_claimed, sid_resolved):
        t = await wired_board.dispatch(sid, escalated_outcome(), SpySink())
        assert t is not None
        tickets[sid] = t
    # leg A stays pending; leg B gets claimed (unresolved); leg C is claimed
    # AND resolved (excluded from rehydrate — audit row only). The claim is
    # the router's own two-step flow: q.claim + dispatcher record_claim.
    wired_board.queue.claim("agent-7",
                            ticket_id=tickets[sid_claimed].ticket_id)
    await wired_board.record_claim(tickets[sid_claimed], "agent-7", SpySink())
    wired_board.queue.claim("agent-8",
                            ticket_id=tickets[sid_resolved].ticket_id)
    await wired_board.record_claim(tickets[sid_resolved], "agent-8", SpySink())
    await wired_board.record_resolution(tickets[sid_resolved], "handled", SpySink())

    # a fresh queue + a fresh load = what a restarted process does at boot
    store = DBEscalationStore()
    rows = await store.load_unresolved()
    mine = [r for r in rows if r.call_sid in (
        sid_pending, sid_claimed, sid_resolved)]
    assert [r.call_sid for r in mine] == [sid_pending, sid_claimed]
    assert {r.claimed_by for r in mine} == {None, "agent-7"}

    fresh = EscalationQueue(maxsize=64)
    restored = fresh.rehydrate(mine)
    assert restored == 2
    assert [t.call_sid for t in fresh.pending_tickets()] == [sid_pending]
    assert fresh.claimed_by(tickets[sid_claimed].ticket_id) == "agent-7"


async def test_persist_failure_is_honest_and_never_breaks_the_queue(
        services_app_client, wired_board):
    """A ticket whose call has NO org row (dangling state) persists as a
    failure — surfaced on the call's own ledger, queue keeps working."""
    sid = f"talkflow-{uuid.uuid4()}"                  # no CallSession seeded

    sink = SpySink()
    ticket = await wired_board.dispatch(sid, escalated_outcome(), sink)
    assert ticket is not None                          # live queue unaffected
    assert await _durable_row(ticket.ticket_id) is None   # nothing durably persisted

    failed = sink.events(EVENT_ESCALATION_PERSIST_FAILED)
    assert len(failed) == 1
    assert failed[0]["action"] == "enqueued"
    assert failed[0]["ticket_id"] == ticket.ticket_id

    enqueued = sink.events(EVENT_ESCALATION_ENQUEUED)
    assert len(enqueued) == 1                          # row queued for live operators
