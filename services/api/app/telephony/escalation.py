"""P4 escalation hooks — route agent-graph escalations to live-agent queues.

The agent graph (``ai_agent_graph``) escalates on its OWN deterministic rules
(opt-out / human / payment / budget / stop / low STT confidence). The turn
loop already exits with ``TurnLoopOutcome(terminal="escalated",
escalation_reason=...)`` and records it on ``call_events`` — but until now
the escalation ENDED THERE: nothing downstream woke up.

This module (plan §C1) is the honest bridge to a live-agent queue:

    AgentTurnLoop --(escalated outcome)--> AgentMediaSession
        -> EscalationDispatcher.dispatch(call_sid, outcome, sink)
            -> records ``agent_escalation_requested``      (audit)
            -> EscalationQueue.push(EscalationTicket)
                 - idempotent per call (a re-escalation never duplicates)
                 - bounded: on overflow the agent records
                   ``agent_escalation_dropped`` — never a silent lie
            -> records ``agent_escalation_enqueued``
        (later, by an operator/worker:)
            queue.claim(worker) -> ``agent_escalation_claimed``
            queue.complete(id, resolution) -> ``agent_escalation_resolved``

Fail-open, never fail-hard: a dispatcher or queue failure is swallowed by
``safe_record``-style guards — a live call is NEVER held hostage by the
escalation plumbing (plan §7). Everything here is in-process and pure; the
production transport (queue backend / laptop claim UI) is a later slice, so
claims are deterministic API calls, not a claim of agent-hiring readiness.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.telephony.media.agent_turn_loop import (
    TERMINAL_ESCALATED,
    TurnLoopOutcome,
    safe_record,
)

log = logging.getLogger("app.telephony.escalation")

#: call_events event names emitted by the hook (audit vocabulary)
EVENT_ESCALATION_REQUESTED = "agent_escalation_requested"
EVENT_ESCALATION_ENQUEUED = "agent_escalation_enqueued"
EVENT_ESCALATION_DUPLICATE = "agent_escalation_duplicate"
EVENT_ESCALATION_DROPPED = "agent_escalation_dropped"
EVENT_ESCALATION_CLAIMED = "agent_escalation_claimed"
EVENT_ESCALATION_RESOLVED = "agent_escalation_resolved"


@dataclass(frozen=True)
class EscalationTicket:
    """One escalated call waiting for a human."""

    ticket_id: str
    call_sid: str
    reason: str | None
    summary: str | None
    turns: int
    created_at: float


@dataclass
class EscalationQueue:
    """In-process FIFO with idempotent push + single-worker claim semantics.

    Pure plumbing (no asyncio primitives needed, no backend): the production
    transport replaces this class behind ``dispatch``/claim seams.
    """

    maxsize: int = 100
    _pending: list[EscalationTicket] = field(default_factory=list)
    _by_call: dict[str, EscalationTicket] = field(default_factory=dict)
    _tickets: dict[str, EscalationTicket] = field(default_factory=dict)  # id → ticket (board view)
    _claimed: dict[str, tuple[str, float]] = field(default_factory=dict)  # ticket -> (worker, at)
    _resolved: dict[str, tuple[str, float]] = field(default_factory=dict)  # ticket -> (resolution, at)

    def __post_init__(self) -> None:
        if self.maxsize <= 0:
            raise ValueError("maxsize must be positive")

    # -- scan perspective --------------------------------------------------- #

    def pending_tickets(self) -> list[EscalationTicket]:
        """Oldest-first snapshot of pending (unclaimed, unresolved) tickets."""
        return list(self._pending)

    def pending_count(self) -> int:
        return len(self._pending)

    def claimed_by(self, ticket_id: str) -> str | None:
        entry = self._claimed.get(ticket_id)
        return entry[0] if entry else None

    def resolution_of(self, ticket_id: str) -> str | None:
        entry = self._resolved.get(ticket_id)
        return entry[0] if entry else None

    def has_ticket_for(self, call_sid: str) -> bool:
        return call_sid in self._by_call

    def ticket_for(self, call_sid: str) -> EscalationTicket | None:
        return self._by_call.get(call_sid)

    # -- mutations ------------------------------------------------------------ #

    def push(self, ticket: EscalationTicket) -> bool:
        """Idempotent enqueue: ``False`` iff a ticket for this call exists."""
        if ticket.call_sid in self._by_call:
            return False
        if self.pending_count() >= self.maxsize:
            raise EscalationQueueFull()
        self._by_call[ticket.call_sid] = ticket
        self._tickets[ticket.ticket_id] = ticket
        self._pending.append(ticket)
        return True

    def claim(self, worker: str, ticket_id: str | None = None) -> EscalationTicket | None:
        """Move a PENDING ticket to ``worker`` (single claim, bounded bookkeeping).

        ``ticket_id=None`` = FIFO (oldest pending); a specific id claims THAT
        ticket (used by the operator console); claiming an already-claimed or
        unknown ticket returns ``None`` — callers translate that to 404/409.
        """
        if ticket_id is None:
            if not self._pending:
                return None
            ticket = self._pending.pop(0)
            self._claimed[ticket.ticket_id] = (worker, time.monotonic())
            return ticket
        existing = self._claimed.get(ticket_id)
        if existing is not None:
            return None                      # claimed once; no work-stealing
        if ticket_id in self._resolved:
            return None
        for index, pending in enumerate(self._pending):
            if pending.ticket_id == ticket_id:
                self._pending.pop(index)
                self._claimed[ticket_id] = (worker, time.monotonic())
                return pending
        return None

    def complete(self, ticket_id: str, resolution: str) -> bool:
        """Mark a CLAIMED ticket resolved. Bookkeeping rows persist for the
        audit; tickets nobody claimed are not resolvable (cannot fake work)."""
        if ticket_id not in self._claimed or ticket_id in self._resolved:
            return False
        self._resolved[ticket_id] = (resolution, time.monotonic())
        return True

    # -- board view (operator console read model) ----------------------------- #

    def ticket_by_id(self, ticket_id: str) -> EscalationTicket | None:
        return self._tickets.get(ticket_id)

    def claimed_ticket_ids(self) -> list[str]:
        return list(self._claimed)

    def resolved_ticket_ids(self) -> list[str]:
        return list(self._resolved)


class EscalationQueueFull(Exception):
    """Raised when the queue is at its bounded capacity (dropped, not lied)."""


class EscalationDispatcher:
    """Turn-loop ⇒ queue ⇒ claim seam, driven by the escalated outcome."""

    def __init__(self, queue: EscalationQueue | None = None) -> None:
        self.queue = queue if queue is not None else EscalationQueue()

    async def dispatch(
        self, call_sid: str, outcome: TurnLoopOutcome, sink: Any,
    ) -> EscalationTicket | None:
        """Move an escalated outcome into the live-agent queue (best-effort).

        Records every decision on the call's own event ledger via the sink —
        the row lives where operators already look; a sink failure NEVER
        breaks the live call (plan §7).
        """
        if outcome.terminal != TERMINAL_ESCALATED:
            return None
        payload = {
            "call_sid": call_sid,
            "reason": outcome.escalation_reason,
            "summary": outcome.summary,
            "turns": outcome.turns,
        }
        await safe_record(sink, EVENT_ESCALATION_REQUESTED, dict(payload))

        queue_ticket = self.queue.ticket_for(call_sid)
        if queue_ticket is not None:  # idempotent re-escalation
            await safe_record(sink, EVENT_ESCALATION_DUPLICATE, {
                "call_sid": call_sid,
                "ticket_id": queue_ticket.ticket_id,
                "reason": outcome.escalation_reason,
            })
            return queue_ticket

        ticket = EscalationTicket(
            ticket_id=f"esc-{uuid.uuid4().hex[:12]}",
            call_sid=call_sid,
            reason=outcome.escalation_reason,
            summary=outcome.summary,
            turns=outcome.turns,
            created_at=time.monotonic(),
        )
        try:
            self.queue.push(ticket)
        except EscalationQueueFull:
            await safe_record(sink, EVENT_ESCALATION_DROPPED, {
                "call_sid": call_sid,
                "reason": "queue_full",
                "maxsize": self.queue.maxsize,
            })
            return None

        await safe_record(sink, EVENT_ESCALATION_ENQUEUED, {
            "call_sid": call_sid,
            "ticket_id": ticket.ticket_id,
            "reason": ticket.reason,
            "summary": ticket.summary,
            "turns": ticket.turns,
        })
        log.info("escalation enqueued for call %s (ticket %s)",
                 call_sid, ticket.ticket_id)
        return ticket

    async def record_claim(
        self, ticket: EscalationTicket, worker: str, sink: Any,
    ) -> None:
        """``claim`` + audit row for an operator/web-wiring claim."""
        claimed = self.queue._claimed.get(ticket.ticket_id)
        if claimed is None:
            return  # not claimed by this path; the agent never lies about it
        await safe_record(sink, EVENT_ESCALATION_CLAIMED, {
            "call_sid": ticket.call_sid,
            "ticket_id": ticket.ticket_id,
            "worker": worker,
            "reason": ticket.reason,
        })

    async def record_resolution(
        self, ticket: EscalationTicket, resolution: str, sink: Any,
    ) -> bool:
        completed = self.queue.complete(ticket.ticket_id, resolution)
        if not completed:
            return False
        await safe_record(sink, EVENT_ESCALATION_RESOLVED, {
            "call_sid": ticket.call_sid,
            "ticket_id": ticket.ticket_id,
            "resolution": resolution,
        })
        return True


# --------------------------------------------------------------------------- #
# the shared process-level dispatcher (runtime + API router converge here)
# --------------------------------------------------------------------------- #

_shared: EscalationDispatcher | None = None


def shared_dispatcher() -> EscalationDispatcher:
    """The ONE dispatcher this process uses: the media runtime dispatches
    into it and the telephony router reads/claims from it (single process
    lane — the production transport swaps behind the same seams).
    """
    global _shared
    if _shared is None:
        _shared = EscalationDispatcher()
    return _shared


def rewire_shared_dispatcher(dispatcher: EscalationDispatcher | None) -> None:
    """Test/reset seam; ``None`` ⇒ the next build is fresh."""
    global _shared
    _shared = dispatcher
