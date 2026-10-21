"""§E2 — durable escalation transport (best-effort DB copy + boot rehydrate).

The in-process FIFO stays the live authority inside ONE process (the
single-process API invariant); this module adds what a restart must not
lose:

``enqueued`` / ``claimed`` / ``resolved`` transitions are mirrored into the
``agent_escalations`` table by the dispatcher (awaitable, deterministic,
best-effort — a DB problem logs an honest ``agent_escalation_persist_failed``
ledger event and never breaks the live call), and boot rehydrates
unresolved rows so escalated calls survive a process restart.

This is NOT a distributed claim implementation: claim/complete ordering
stays the queue's own discipline. A Redis-backed live transport would
replace the RECEIVING side behind the same shared dispatcher seams.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import AgentEscalation, CallSession
from app.db.session import db_session
from app.telephony.escalation import EscalationRestoreRow, shared_dispatcher

log = logging.getLogger("app.telephony.escalation_store")


class DBEscalationStore:
    """Best-effort durable copy of the shared escalation queue."""

    async def persist(
        self,
        action: str,
        ticket,
        worker: str | None = None,
        resolution: str | None = None,
    ) -> bool:
        try:
            async with db_session() as db:
                if action == "enqueued":
                    org_id = (await db.execute(
                        select(CallSession.org_id)
                        .where(CallSession.call_sid == ticket.call_sid)
                    )).scalar()
                    if org_id is None:
                        log.warning(
                            "escalation persist: no org for call %s — durable "
                            "row skipped (the call event ledger stays truthful)",
                            ticket.call_sid)
                        return False
                    db.add(AgentEscalation(
                        org_id=org_id,
                        ticket_id=ticket.ticket_id,
                        call_sid=ticket.call_sid,
                        reason=(ticket.reason or None),
                        summary=ticket.summary,
                        turns=ticket.turns,
                    ))
                elif action == "claimed":
                    row = await db.scalar(select(AgentEscalation).where(
                        AgentEscalation.ticket_id == ticket.ticket_id))
                    if row is None:
                        return False
                    row.claimed_by = worker
                    row.claimed_at = datetime.now(UTC)
                elif action == "resolved":
                    row = await db.scalar(select(AgentEscalation).where(
                        AgentEscalation.ticket_id == ticket.ticket_id))
                    if row is None:
                        return False
                    row.resolved_by = worker
                    row.resolved_at = datetime.now(UTC)
                    row.resolution = resolution
                else:                                   # unknown action: refuse
                    log.warning("escalation persist: unknown action %r", action)
                    return False
                await db.commit()
            return True
        except Exception:                               # noqa: BLE001 — best-effort by design
            log.exception("escalation persist failed (action=%s call=%s) — "
                          "the live queue stays the truthful working view",
                          action, ticket.call_sid)
            return False

    async def load_unresolved(self) -> list[EscalationRestoreRow]:
        """Unresolved durable rows (oldest first), boot-rehydrate feed."""
        try:
            async with db_session() as db:
                rows = (await db.execute(
                    select(AgentEscalation)
                    .where(AgentEscalation.resolved_at.is_(None))
                    .order_by(AgentEscalation.created_at.asc())
                )).scalars().all()
            return [
                EscalationRestoreRow(
                    ticket_id=row.ticket_id,
                    call_sid=row.call_sid,
                    reason=row.reason,
                    summary=row.summary,
                    turns=row.turns,
                    claimed_by=row.claimed_by,
                )
                for row in rows
            ]
        except Exception:                               # noqa: BLE001 — missing table / DB hiccup
            log.exception("escalation rehydrate load failed — starting empty")
            return []


async def rehydrate_shared_dispatcher() -> int:
    """Boot seam: restore unresolved durable tickets into the live queue.

    Returns the restored count so the lifespan can log it. Resolved rows are
    intentionally left in the durable table (audit history — a later slice
    can add retention sweeping).
    """
    dispatcher = shared_dispatcher()
    rows = await DBEscalationStore().load_unresolved()
    restored = dispatcher.queue.rehydrate(rows)
    if len(rows) != restored:
        log.warning("escalation rehydrate: %d durable row(s) did not fit into "
                    "the bounded live queue (pending backlog over maxsize)",
                    len(rows) - restored)
    return restored
