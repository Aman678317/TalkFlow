"""P4 §D1 — the live-agent escalation board: operator claim/resolve API.

Extends the C1 queue with claim-by-id and an id→ticket registry, exposes the
board through the telephony router (org-scoping derived from
``call_sid → CallSession.org_id``, foreign tickets simply invisible), proves
single-claim semantics (no stealing, noFabricated resolution), and shows the
board's actions land on the call ledger.
"""
from __future__ import annotations

import uuid

import pytest


# --------------------------------------------------------------------------- #
# queue primitives (pure)
# --------------------------------------------------------------------------- #


def _ticket(call_sid: str, ticket_id: str, reason: str = "opt_out") -> object:
    from app.telephony.escalation import EscalationTicket

    return EscalationTicket(ticket_id=ticket_id, call_sid=call_sid,
                            reason=reason, summary=None, turns=1,
                            created_at=0.0)


def test_claim_by_id_targets_the_requested_ticket_only():
    from app.telephony.escalation import EscalationQueue

    q = EscalationQueue()
    q.push(_ticket("call-a", "t-a"))
    q.push(_ticket("call-b", "t-b"))

    claimed = q.claim("agent-1", ticket_id="t-b")     # NOT the FIFO head
    assert claimed is not None and claimed.ticket_id == "t-b"
    assert q.claimed_by("t-b") == "agent-1"
    assert q.ticket_by_id("t-a") is not None          # registry keeps all
    assert q.pending_tickets()[0].ticket_id == "t-a"  # FIFO unaffected


def test_claim_by_id_never_steals_work():
    from app.telephony.escalation import EscalationQueue

    q = EscalationQueue()
    q.push(_ticket("call-a", "t-a"))
    q.claim("agent-1", ticket_id="t-a")
    assert q.claim("agent-2", ticket_id="t-a") is None     # claimed
    q.complete("t-a", "done")
    assert q.claim("agent-2", ticket_id="t-a") is None     # resolved


def test_claim_by_id_unknown_ticket_is_none():
    from app.telephony.escalation import EscalationQueue

    q = EscalationQueue()
    assert q.claim("agent-1", ticket_id="missing") is None


def test_ticket_by_id_survives_claim_and_resolution():
    from app.telephony.escalation import EscalationQueue

    q = EscalationQueue()
    q.push(_ticket("call-a", "t-a"))
    q.claim("w", ticket_id="t-a")
    q.complete("t-a", "handled")
    assert q.ticket_by_id("t-a").ticket_id == "t-a"
    assert q.resolution_of("t-a") == "handled"


# --------------------------------------------------------------------------- #
# the real app (SQLite, real auth, real router)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def fresh_board():
    from app.telephony.escalation import (
        EscalationDispatcher,
        rewire_shared_dispatcher,
    )

    dispatcher = EscalationDispatcher()
    rewire_shared_dispatcher(dispatcher)
    yield dispatcher
    rewire_shared_dispatcher(None)


async def _seed_board_call(org_id: str, user_id: str, sid: str) -> None:
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        db.add(M.CallSession(
            org_id=uuid.UUID(org_id), created_by=uuid.UUID(user_id),
            call_sid=sid, from_number="1001", to_number="1002",
            mode="ai_agent", provider="asterisk", status="connected",
        ))
        await db.commit()


async def _push_ticket(dispatcher, sid: str, ticket_id: str) -> None:
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session
    from app.telephony.escalation import EscalationTicket

    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession.id).where(M.CallSession.call_sid == sid))
        assert res.scalars().first() is not None, "seed the call first"
    dispatcher.queue.push(EscalationTicket(
        ticket_id=ticket_id, call_sid=sid, reason="human_request",
        summary="wants a human", turns=2, created_at=0.0))


async def test_board_lists_only_this_orgs_tickets(services_app_client, user,
                                                  second_user, fresh_board):
    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_board_call(user["org_id"], user["user_id"], sid)
    await _push_ticket(fresh_board, sid, "esc-mine")

    r = services_app_client.get("/api/v1/telephony/escalations",
                                headers=user["headers"])
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["ticket_id"] == "esc-mine"
    assert rows[0]["state"] == "pending"
    assert rows[0]["reason"] == "human_request"
    assert rows[0]["claimed_by"] is None

    other = services_app_client.get("/api/v1/telephony/escalations",
                                    headers=second_user["headers"])
    assert other.status_code == 200
    assert other.json() == []                        # invisible, not 403


async def test_board_claim_and_resolve_close_the_loop(services_app_client,
                                                      user, fresh_board):
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session

    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_board_call(user["org_id"], user["user_id"], sid)
    await _push_ticket(fresh_board, sid, "esc-loop")

    r = services_app_client.post("/api/v1/telephony/escalations/esc-loop/claim",
                                 json={"worker": "Amara"},
                                 headers=user["headers"])
    assert r.status_code == 200, r.text
    claimed = r.json()
    assert claimed["state"] == "claimed"
    assert claimed["claimed_by"] == "Amara"

    r = services_app_client.post("/api/v1/telephony/escalations/esc-loop/claim",
                                 json={"worker": "Rival"},
                                 headers=user["headers"])
    assert r.status_code == 409, r.text              # no stealing

    r = services_app_client.post(
        "/api/v1/telephony/escalations/esc-loop/resolve",
        json={"resolution": "talked_customer_down"}, headers=user["headers"])
    assert r.status_code == 200, r.text
    resolved = r.json()
    assert resolved["state"] == "resolved"
    assert resolved["resolution"] == "talked_customer_down"

    # the board's actions are audited on the call ledger
    async with db_session() as db:
        res = await db.execute(
            select(M.CallEvent.event_type).where(
                M.CallEvent.call_id.in_(select(M.CallSession.id)
                                        .where(M.CallSession.call_sid == sid))))
        kinds = {row[0] for row in res.all()}
    assert "agent_escalation_claimed" in kinds
    assert "agent_escalation_resolved" in kinds

    # final board view
    r = services_app_client.get("/api/v1/telephony/escalations",
                                headers=user["headers"])
    states = {row["ticket_id"]: row["state"] for row in r.json()}
    assert states == {"esc-loop": "resolved"}


async def test_board_claim_404_is_indistinguishable_foreign_or_missing(
        services_app_client, user, second_user, fresh_board):
    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_board_call(user["org_id"], user["user_id"], sid)
    await _push_ticket(fresh_board, sid, "esc-hidden")

    r = services_app_client.post("/api/v1/telephony/escalations/esc-hidden/claim",
                                 json=None, headers=second_user["headers"])
    assert r.status_code == 404, r.text              # no existence leak

    r = services_app_client.post("/api/v1/telephony/escalations/missing/claim",
                                 json=None, headers=user["headers"])
    assert r.status_code == 404, r.text


async def test_board_cannot_resolve_unclaimed_work(services_app_client, user,
                                                   fresh_board):
    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_board_call(user["org_id"], user["user_id"], sid)
    await _push_ticket(fresh_board, sid, "esc-free")

    r = services_app_client.post(
        "/api/v1/telephony/escalations/esc-free/resolve", json=None,
        headers=user["headers"])
    assert r.status_code == 409, r.text

    # nothing fake reached the ledger
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session
    async with db_session() as db:
        res = await db.execute(
            select(M.CallEvent).where(
                M.CallEvent.call_id.in_(select(M.CallSession.id)
                                        .where(M.CallSession.call_sid == sid))))
        assert list(res.scalars().all()) == []
