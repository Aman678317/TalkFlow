"""P4 §C1 escalation hooks — live-agent queue routing, deterministic.

Covers the full seam:

- queue semantics: idempotent push (re-escalation suppressed), bounded
  capacity (overflow ⇒ honest drop, never a silent lie), FIFO claim,
  claim-then-resolve bookkeeping (unclaimed tickets are NOT resolvable);
- dispatcher: only ``escalated`` outcomes route; reason/summary/turns ride
  the ticket unchanged; every decision lands on the call's own ledger via
  the sink (requested / enqueued / duplicate / dropped / claimed / resolved);
- agent-media integration: an escalated turn-loop outcome routes through the
  session hook (the deterministic fail-closed path — a session without a
  recognizer raises ``low_stt_confidence``); a session without a hook stays
  a pure no-op; a dispatcher failure never breaks teardown.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from app.telephony.escalation import (
    EVENT_ESCALATION_CLAIMED,
    EVENT_ESCALATION_DUPLICATE,
    EVENT_ESCALATION_DROPPED,
    EVENT_ESCALATION_ENQUEUED,
    EVENT_ESCALATION_REQUESTED,
    EVENT_ESCALATION_RESOLVED,
    EscalationDispatcher,
    EscalationQueue,
    EscalationQueueFull,
    EscalationTicket,
)
from app.telephony.media.agent_media_session import AgentMediaSession, AgentMediaSpec
from app.telephony.media.agent_turn_loop import (
    TERMINAL_CONCLUDED,
    TERMINAL_ESCALATED,
    TurnLoopOutcome,
)


class SpySink:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.records.append((event_type, dict(payload)))

    def events(self, kind: str) -> list[dict[str, Any]]:
        return [payload for event, payload in self.records if event == kind]


def escalated_outcome(reason: str = "opt_out", turns: int = 3,
                      summary: str | None = "wants to be left alone") -> TurnLoopOutcome:
    return TurnLoopOutcome(terminal=TERMINAL_ESCALATED,
                           escalation_reason=reason,
                           summary=summary, turns=turns)


# --------------------------------------------------------------------------- #
# queue semantics
# --------------------------------------------------------------------------- #


def test_queue_rejects_nonpositive_maxsize():
    with pytest.raises(ValueError):
        EscalationQueue(maxsize=0)


def test_push_is_idempotent_per_call():
    q = EscalationQueue()
    t1 = EscalationTicket("t-1", "call-1", "opt_out", "s", 3, 0.0)
    t2 = EscalationTicket("t-2", "call-1", "stop", "s2", 5, 0.1)
    assert q.push(t1) is True
    assert q.push(t2) is False                      # same call: suppressed
    assert q.has_ticket_for("call-1")
    assert q.ticket_for("call-1") is t1             # FIRST ticket wins
    assert q.pending_count() == 1


def test_push_over_capacity_raises_for_the_caller_to_decide():
    q = EscalationQueue(maxsize=1)
    assert q.push(EscalationTicket("t-1", "call-1", None, None, 0, 0.0)) is True
    with pytest.raises(EscalationQueueFull):
        q.push(EscalationTicket("t-2", "call-2", None, None, 0, 0.1))


def test_claim_is_fifo_and_single():
    q = EscalationQueue()
    q.push(EscalationTicket("t-1", "call-a", "human", "first", 1, 0.0))
    q.push(EscalationTicket("t-2", "call-b", "payment", "second", 2, 0.1))

    first = q.claim("worker-7")
    assert first is not None and first.ticket_id == "t-1"
    assert q.claimed_by("t-1") == "worker-7"

    second = q.claim("worker-7")
    assert second is not None and second.ticket_id == "t-2"

    assert q.claim("worker-8") is None              # empty queue
    assert q.pending_count() == 0


def test_unclaimed_ticket_is_not_resolvable():
    q = EscalationQueue()
    q.push(EscalationTicket("t-1", "call-1", None, None, 0, 0.0))
    assert q.complete("t-1", "handled") is False    # nobody claimed it
    q.claim("w")
    assert q.complete("t-1", "handled") is True
    assert q.complete("t-1", "again") is False      # resolved once
    assert q.resolution_of("t-1") == "handled"


# --------------------------------------------------------------------------- #
# dispatcher
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_only_escalated_outcomes_route():
    sink = SpySink()
    dispatcher = EscalationDispatcher()
    outcome = TurnLoopOutcome(terminal=TERMINAL_CONCLUDED,
                              summary="happy path", turns=2)
    assert await dispatcher.dispatch("call-1", outcome, sink) is None
    assert sink.records == []


@pytest.mark.asyncio
async def test_dispatch_records_requested_and_enqueued():
    sink = SpySink()
    dispatcher = EscalationDispatcher()

    ticket = await dispatcher.dispatch(
        "call-1", escalated_outcome(), sink)

    assert ticket is not None
    assert ticket.ticket_id.startswith("esc-")
    assert ticket.reason == "opt_out"
    assert ticket.summary == "wants to be left alone"
    assert ticket.turns == 3
    assert ticket.call_sid == "call-1"

    requested = sink.events(EVENT_ESCALATION_REQUESTED)
    assert len(requested) == 1
    assert requested[0]["reason"] == "opt_out"

    enqueued = sink.events(EVENT_ESCALATION_ENQUEUED)
    assert len(enqueued) == 1
    assert enqueued[0]["ticket_id"] == ticket.ticket_id
    assert enqueued[0]["turns"] == 3


@pytest.mark.asyncio
async def test_re_escalation_records_duplicate_not_a_second_ticket():
    sink = SpySink()
    dispatcher = EscalationDispatcher()

    first = await dispatcher.dispatch("call-1", escalated_outcome(), sink)
    second = await dispatcher.dispatch("call-1", escalated_outcome("stop"), sink)

    assert first is not None and second is first   # same ticket returned
    dup = sink.events(EVENT_ESCALATION_DUPLICATE)
    assert len(dup) == 1
    assert dup[0]["reason"] == "stop"              # the NEW reason is recorded
    assert sink.events(EVENT_ESCALATION_ENQUEUED)  # enqueued exactly once
    assert len(dispatcher.queue.pending_tickets()) == 1


@pytest.mark.asyncio
async def test_overflow_marks_call_dropped_honestly():
    sink_a, sink_b = SpySink(), SpySink()
    dispatcher = EscalationDispatcher(EscalationQueue(maxsize=1))

    await dispatcher.dispatch("call-a", escalated_outcome(), sink_a)
    ticket = await dispatcher.dispatch("call-b", escalated_outcome(), sink_b)

    assert ticket is None                          # capacity ⇒ dropped
    dropped = sink_b.events(EVENT_ESCALATION_DROPPED)
    assert len(dropped) == 1
    assert dropped[0]["reason"] == "queue_full"
    assert dropped[0]["maxsize"] == 1
    # the queued call was never touched
    assert sink_a.events(EVENT_ESCALATION_DROPPED) == []


@pytest.mark.asyncio
async def test_claim_and_resolution_flow_records_ledger_rows():
    sink = SpySink()
    dispatcher = EscalationDispatcher()
    ticket = await dispatcher.dispatch("call-1", escalated_outcome(), sink)

    claimed = dispatcher.queue.claim("worker-9")
    assert claimed is ticket
    await dispatcher.record_claim(ticket, "worker-9", sink)

    resolved = await dispatcher.record_resolution(ticket, "talked_to_human", sink)
    assert resolved is True

    claimed_rows = sink.events(EVENT_ESCALATION_CLAIMED)
    assert len(claimed_rows) == 1
    assert claimed_rows[0]["worker"] == "worker-9"
    assert claimed_rows[0]["ticket_id"] == ticket.ticket_id

    resolved_rows = sink.events(EVENT_ESCALATION_RESOLVED)
    assert len(resolved_rows) == 1
    assert resolved_rows[0]["resolution"] == "talked_to_human"


# --------------------------------------------------------------------------- #
# agent-media integration (deterministic fail-closed escalation)
# --------------------------------------------------------------------------- #


class FakeARIList:
    async def request_json(self, method: str, path: str, params=None):
        params = dict(params or {})
        if method == "POST" and path == "/ari/channels/externalMedia":
            cid = str(params["channelId"])
            return {"id": cid, "state": "Up", "dialstring": "WebSocket/x/d"}
        if method == "POST" and path == "/ari/bridges":
            return {"id": str(params["bridgeId"])}
        if method == "POST" and path.endswith("/addChannel"):
            return {}
        if method == "DELETE":
            return {}
        raise AssertionError(f"unexpected ARI call {method} {path}")

    async def list_channels(self) -> list[dict]:
        return []


@pytest.mark.asyncio
async def test_fail_closed_session_routes_escalation_through_hook():
    """No recognizer ⇒ graph escalates (low_stt_confidence) ⇒ ticket."""
    sink = SpySink()
    dispatcher = EscalationDispatcher()
    session = AgentMediaSession(
        FakeARIList(),
        call_sid="call-hotline",
        caller_channel_id="caller-1",
        spec=AgentMediaSpec(app_name="talkflow", external_host="media-cfg",
                            segment_wait_seconds=0.05),
        sink=sink,
        registry={},
        escalation=dispatcher,
    )
    await session.run_until_done()

    assert session.outcome is not None
    assert session.outcome.terminal == TERMINAL_ESCALATED
    assert session.outcome.escalation_reason == "low_stt_confidence"

    requested = sink.events(EVENT_ESCALATION_REQUESTED)
    assert len(requested) == 1
    assert requested[0]["reason"] == "low_stt_confidence"
    assert dispatcher.queue.has_ticket_for("call-hotline")

    ended = sink.events("agent_media_session_ended")
    assert len(ended) == 1                        # teardown still completed


@pytest.mark.asyncio
async def test_session_without_hook_stays_pure_noop():
    """Default hook = None: escalated outcome behaves exactly as before #C1."""
    sink = SpySink()
    session = AgentMediaSession(
        FakeARIList(),
        call_sid="call-plain",
        caller_channel_id="caller-1",
        spec=AgentMediaSpec(app_name="talkflow", external_host="media-cfg",
                            segment_wait_seconds=0.05),
        sink=sink,
        registry={},
    )
    await session.run_until_done()

    escalation_events = [e for e, _p in sink.records
                         if e.startswith("agent_escalation")]
    assert escalation_events == []


@pytest.mark.asyncio
async def test_dispatcher_failure_never_breaks_teardown():
    """A hook that raises must not block the call's teardown (plan §7)."""

    class ExplodingDispatcher:
        async def dispatch(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("queue backend on fire")

    sink = SpySink()
    session = AgentMediaSession(
        FakeARIList(),
        call_sid="call-boom",
        caller_channel_id="caller-1",
        spec=AgentMediaSpec(app_name="talkflow", external_host="media-cfg",
                            segment_wait_seconds=0.05),
        sink=sink,
        registry={},
        escalation=ExplodingDispatcher(),
    )
    await session.run_until_done()

    assert session.outcome.terminal == TERMINAL_ESCALATED
    ended = sink.events("agent_media_session_ended")
    assert len(ended) == 1                        # teardown completed anyway
