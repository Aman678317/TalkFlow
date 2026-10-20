"""P4 §C2 — transcript + citation API (`GET /api/v1/telephony/calls/{ref}/transcript`).

Two layers, both deterministic:

- pure assembler (`app.telephony.call_transcript.assemble_transcript`): turn
  slicing, caller-side fingerprint-only privacy invariant, verbatim agent
  lines, sha256 node citations, escalation/media surfaces, honest accounting
  of everything else;
- the real app: ref resolution (UUID id vs call_sid), org isolation (a
  foreign tenant gets the SAME 404 as a nonexistent call), and a seeded
  ai_agent-shaped ledger surfacing completely.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _ts(base: datetime, offset_ms: int) -> datetime:
    return base + timedelta(milliseconds=offset_ms)


def _ev(call_id: uuid.UUID, etype: str, payload: dict,
        at: datetime) -> SimpleNamespace:
    """A stand-in ledger row: the assembler touches (id, event_type,
    payload_json, created_at) only — duck-typed, no ORM round-trip needed."""
    return SimpleNamespace(id=uuid.uuid4(), call_id=call_id,
                           event_type=etype, payload_json=payload, created_at=at)


def _call() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        call_sid="CA-test-sid",
        direction="outbound",
        mode="ai_agent",
        status="ended",
        provider="simulated",
        caller_language="en",
        receiver_language="hi",
        from_number="+1001",
        to_number="+1002",
        started_at=datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc),
        connected_at=None,
        ended_at=None,
        duration_seconds=42,
    )


T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# pure assembler
# --------------------------------------------------------------------------- #


def test_full_agent_turn_is_sliced_with_fingerprint_and_citation():
    from app.telephony.call_transcript import assemble_transcript

    call = _call()
    events = [
        # greeting: graph speaks before any caller turn
        _ev(call.id, "ai_agent.node",
            {"node": "disclose", "from": "disclose", "to": "disclose",
             "inputs_sha256": "in-0", "output_sha256": "out-0"}, _ts(T0, 0)),
        _ev(call.id, "agent_turn_said",
            {"node": "disclose", "action": "speak",
             "text": "This is an AI agent.", "frames_rendered": 90,
             "tts": "absent"}, _ts(T0, 10)),
        # caller turn 1
        _ev(call.id, "agent_turn_utterance",
            {"turn": 1, "text_len": 9, "text_sha256": "fp-1",
             "confidence": 0.7, "frames": 42}, _ts(T0, 100)),
        _ev(call.id, "ai_agent.node",
            {"node": "respond", "from": "disclose", "to": "respond",
             "inputs_sha256": "in-1", "output_sha256": "out-1"}, _ts(T0, 110)),
        _ev(call.id, "agent_turn_said",
            {"node": "respond", "action": "speak", "text": "Happy to help.",
             "frames_rendered": 40, "tts": "wired"}, _ts(T0, 120)),
        # caller turn 2 escalates
        _ev(call.id, "agent_turn_utterance",
            {"turn": 2, "text_len": 11, "text_sha256": "fp-2",
             "confidence": 0.2, "frames": 8}, _ts(T0, 200)),
        _ev(call.id, "ai_agent.node",
            {"node": "escalate", "from": "respond", "to": "escalate",
             "inputs_sha256": "in-2", "output_sha256": "out-2",
             "escalation_reason": "human_request"}, _ts(T0, 210)),
        _ev(call.id, "agent_turn_outcome",
            {"terminal": "escalated", "escalation_reason": "human_request",
             "summary": "wants a human", "turns": 2}, _ts(T0, 300)),
    ]

    body = assemble_transcript(call, events)

    assert body["call"]["call_sid"] == "CA-test-sid"
    assert body["meta"]["turns"] == 3
    # greeting turn: turn 0, caller {} (fingerprint absent), verbatim agent
    greet = body["turns"][0]
    assert greet["turn"] == 0 and greet["caller"] == {}
    assert greet["agent_lines"][0]["text"] == "This is an AI agent."
    assert greet["agent_lines"][0]["tts"] == "absent"
    assert greet["citations"][0]["inputs_sha256"] == "in-0"
    # caller turn 1: fingerprint ONLY — no raw text anywhere
    t1 = body["turns"][1]
    assert t1["turn"] == 1
    assert t1["caller"] == {"text_len": 9, "text_sha256": "fp-1",
                            "confidence": 0.7, "frames": 42}
    assert "text" not in t1["caller"]
    assert t1["agent_lines"][0]["text"] == "Happy to help."
    assert t1["agent_lines"][0]["tts"] == "wired"
    assert t1["citations"][0]["to"] == "respond"
    # caller turn 2: escalation citation carries the reason
    t2 = body["turns"][2]
    assert t2["citations"][0]["escalation_reason"] == "human_request"
    assert t2["citations"][0]["output_sha256"] == "out-2"
    # outcome
    assert body["outcome"]["terminal"] == "escalated"
    assert body["outcome"]["turns"] == 2
    assert body["outcome"]["escalation_reason"] == "human_request"
    # nothing was lost
    assert body["unsurfaced_events"] == {}


def test_arrival_order_is_irrelevant_deterministic_sort():
    from app.telephony.call_transcript import assemble_transcript

    call = _call()
    events = [
        _ev(call.id, "agent_turn_said",
            {"text": "second", "frames_rendered": 0, "tts": "wired"},
            _ts(T0, 100)),
        _ev(call.id, "agent_turn_utterance",
            {"turn": 1, "text_len": 3, "text_sha256": "fp", "confidence": 0.9,
             "frames": 10}, _ts(T0, 50)),
    ]
    body = assemble_transcript(call, events)
    assert body["turns"][0]["turn"] == 1          # utterance first by time
    assert body["turns"][0]["agent_lines"][0]["text"] == "second"


def test_events_at_the_same_instant_keep_a_stable_order():
    from app.telephony.call_transcript import assemble_transcript

    call = _call()
    same_at = _ts(T0, 50)
    events = [
        _ev(call.id, "agent_turn_utterance",
            {"turn": 1, "text_len": 3, "text_sha256": "fp", "confidence": 0.9,
             "frames": 10}, same_at),
        _ev(call.id, "agent_turn_said",
            {"text": "line", "frames_rendered": 0, "tts": "absent"}, same_at),
    ]
    body = assemble_transcript(call, events)
    # turn row was opened by whichever row sorted first; both rows surface
    total_said = sum(len(t["agent_lines"]) for t in body["turns"])
    assert total_said == 1
    assert body["meta"]["events_total"] == 2


def test_escalation_and_media_surfaces_move_to_their_sections():
    from app.telephony.call_transcript import assemble_transcript

    call = _call()
    events = [
        _ev(call.id, "media_bridge_joined",
            {"bridge_id": "b-1", "members": ["c", "r"]}, _ts(T0, 1)),
        _ev(call.id, "agent_media_session_started", {"frames_in": 0}, _ts(T0, 2)),
        _ev(call.id, "call.caption_delivered",
            {"leg": "receiver", "text": "hi translated", "audio": False},
            _ts(T0, 3)),
        _ev(call.id, "agent_escalation_requested",
            {"call_sid": "CA-test-sid", "reason": "human_request"}, _ts(T0, 4)),
        _ev(call.id, "agent_escalation_enqueued",
            {"ticket_id": "esc-1", "reason": "human_request"}, _ts(T0, 5)),
        _ev(call.id, "status_change", {"status": "connected"}, _ts(T0, 6)),
    ]
    body = assemble_transcript(call, events)

    kinds = [m["event"] for m in body["media_timeline"]]
    assert kinds == ["media_bridge_joined", "agent_media_session_started",
                     "call.caption_delivered"]
    assert body["media_timeline"][2]["payload"]["audio"] is False

    esc = [e["event"] for e in body["escalations"]]
    assert esc == ["agent_escalation_requested", "agent_escalation_enqueued"]
    assert body["escalations"][1]["payload"]["ticket_id"] == "esc-1"

    # lifecycle/provider rows are accounted for, not silently dropped
    assert body["unsurfaced_events"] == {"status_change": 1}
    assert body["outcome"] is None                      # no outcome row yet


def test_empty_ledger_is_an_honest_empty_transcript():
    from app.telephony.call_transcript import assemble_transcript

    body = assemble_transcript(_call(), [])
    assert body["turns"] == []
    assert body["outcome"] is None
    assert body["escalations"] == [] and body["media_timeline"] == []
    assert body["unsurfaced_events"] == {}
    assert body["meta"]["events_total"] == 0


# --------------------------------------------------------------------------- #
# the real app (SQLite, real auth, real router)
# --------------------------------------------------------------------------- #


async def _seed_agent_call(org_id: str, user_id: str, sid: str) -> None:
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        row = M.CallSession(
            org_id=uuid.UUID(org_id), created_by=uuid.UUID(user_id),
            call_sid=sid, from_number="1001", to_number="1002",
            mode="ai_agent", provider="asterisk", status="connected",
        )
        db.add(row)
        await db.flush()
        base = datetime.now(timezone.utc)
        rows = [
            M.CallEvent(call_id=row.id, event_type="agent_turn_said",
                        payload_json={"node": "disclose", "action": "speak",
                                      "text": "AI disclosure line.",
                                      "frames_rendered": 0, "tts": "absent"},
                        created_at=_ts(base, 0)),
            M.CallEvent(call_id=row.id, event_type="agent_turn_utterance",
                        payload_json={"turn": 1, "text_len": 21,
                                      "text_sha256": "fp-seed",
                                      "confidence": 0.5, "frames": 30},
                        created_at=_ts(base, 50)),
            M.CallEvent(call_id=row.id, event_type="ai_agent.node",
                        payload_json={"node": "escalate", "from": "disclose",
                                      "to": "escalate",
                                      "inputs_sha256": "in-seed",
                                      "output_sha256": "out-seed",
                                      "escalation_reason": "low_stt_confidence"},
                        created_at=_ts(base, 60)),
            M.CallEvent(call_id=row.id, event_type="agent_turn_outcome",
                        payload_json={"terminal": "escalated",
                                      "escalation_reason": "low_stt_confidence",
                                      "summary": "seedy", "turns": 1},
                        created_at=_ts(base, 100)),
            M.CallEvent(call_id=row.id, event_type="media_bridge_joined",
                        payload_json={"bridge_id": "b-seed"}, created_at=_ts(base, 20)),
        ]
        for r in rows:
            db.add(r)
        await db.commit()


def test_transcript_api_404_for_unknown_id_and_sid(services_app_client, user):
    r = services_app_client.get(
        f"/api/v1/telephony/calls/{uuid.uuid4()}/transcript",
        headers=user["headers"])
    assert r.status_code == 404, r.text

    r = services_app_client.get(
        f"/api/v1/telephony/calls/talkflow-{uuid.uuid4()}/transcript",
        headers=user["headers"])
    assert r.status_code == 404, r.text


async def test_transcript_api_org_isolated(services_app_client, user, second_user):
    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_agent_call(user["org_id"], user["user_id"], sid)

    r = services_app_client.get(
        f"/api/v1/telephony/calls/{sid}/transcript",
        headers=second_user["headers"])
    assert r.status_code == 404, r.text     # indistinguishable from unknown


async def test_transcript_api_surfaces_the_full_seeded_ledger(services_app_client,
                                                              user):
    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_agent_call(user["org_id"], user["user_id"], sid)

    r = services_app_client.get(f"/api/v1/telephony/calls/{sid}/transcript",
                                headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["call"]["call_sid"] == sid
    assert body["call"]["mode"] == "ai_agent"

    turns = body["turns"]
    assert len(turns) == 2
    assert turns[0]["turn"] == 0
    assert turns[0]["agent_lines"][0]["text"] == "AI disclosure line."
    assert turns[1]["turn"] == 1
    assert turns[1]["caller"]["text_sha256"] == "fp-seed"
    assert "text" not in turns[1]["caller"]

    citation = turns[1]["citations"][0]
    assert citation["inputs_sha256"] == "in-seed"
    assert citation["output_sha256"] == "out-seed"
    assert citation["escalation_reason"] == "low_stt_confidence"

    assert body["outcome"]["terminal"] == "escalated"
    assert body["escalations"] == []                      # queue C1 rows seeded separately below
    assert body["media_timeline"][0]["event"] == "media_bridge_joined"
    assert body["unsurfaced_events"] == {}


async def test_transcript_api_resolves_by_id_and_records_escalation_rows(
        services_app_client, user):
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session

    sid = f"talkflow-{uuid.uuid4()}"
    await _seed_agent_call(user["org_id"], user["user_id"], sid)

    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession.id).where(M.CallSession.call_sid == sid))
        call_id = str(res.scalars().one())
        row = M.CallEvent(call_id=uuid.UUID(call_id),
                          event_type="agent_escalation_enqueued",
                          payload_json={"call_sid": sid, "ticket_id": "esc-x",
                                        "reason": "low_stt_confidence"},
                          created_at=datetime.now(timezone.utc))
        db.add(row)
        await db.commit()

    # same call reached twice: by UUID id and by call_sid
    r = services_app_client.get(f"/api/v1/telephony/calls/{call_id}/transcript",
                                headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["call"]["call_sid"] == sid

    tickets = [e for e in body["escalations"]
               if e["event"] == "agent_escalation_enqueued"]
    assert tickets and tickets[0]["payload"]["ticket_id"] == "esc-x"


# --------------------------------------------------------------------------- #
# queue C4 — citation re-derivation (verify_citations)
# --------------------------------------------------------------------------- #
# The transcript exposes input/output sha256 digests per graph transition.
# This section makes those digests EARN their keep: what can be re-derived
# from stored ledger content MUST re-derive; what cannot (caller speech,
# fingerprint-only) is counted and never faked. The canonical serialization
# contract with ai_agent_graph._sha256 is guarded by the real-graph drive.


def _said(ev, node: str, text: str):
    return _ev(ev, "agent_turn_said",
               {"node": node, "action": "speak", "text": text,
                "frames_rendered": 12, "tts": "wired"}, _ts(T0, 100))


def _node_row(ev, to_node: str, *, say: str | None = None,
              reason: str | None = None, inputs: str = "in-digest"):
    from app.telephony.call_transcript import _citation_sha256

    out = (_citation_sha256({"escalation_reason": reason}) if reason is not None
           else _citation_sha256({"say": say}))
    payload = {"node": to_node, "from": "disclose", "to": to_node,
               "inputs_sha256": inputs, "output_sha256": out}
    if reason is not None:
        payload["escalation_reason"] = reason
    return _ev(ev, "ai_agent.node", payload, _ts(T0, 90))


def test_say_bound_citation_rederives_from_the_verbatim_line():
    from app.telephony.call_transcript import _citation_sha256, verify_citations

    call = _call()
    line = "Happy to help with your balance."
    events = [_node_row(call.id, "respond", say=line),
              _said(call.id, "respond", line)]

    report = verify_citations(events)
    assert report["checked"] == 1 and report["verified"] == 1
    assert report["mismatches"] == []
    assert report["inputs_not_rederivable"] == 1        # counted, not faked

    # TAMPER: the verbatim line is altered after the fact — the citation no
    # longer re-derives against the ledger's verbatim evidence set: the
    # mismatch carries the on-ledger digest and names no invented line
    tampered = [_node_row(call.id, "respond", say=line),
                _said(call.id, "respond", "totally different words")]
    bad = verify_citations(tampered)
    assert bad["verified"] == 0 and bad["checked"] == 1
    assert len(bad["mismatches"]) == 1
    m = bad["mismatches"][0]
    assert m["node"] == "respond" and m["kind"] == "say_line"
    assert m["expected"] is None
    assert m["found"] == _citation_sha256({"say": line})


def test_escalation_citation_rederives_from_its_own_reason():
    from app.telephony.call_transcript import verify_citations

    call = _call()
    events = [_node_row(call.id, "escalate", reason="human_request")]
    report = verify_citations(events)
    assert report["checked"] == 1 and report["verified"] == 1
    assert report["mismatches"] == []

    # a rewritten reason breaks the binding exactly like edited speech:
    # the reason is edited AFTER the digest was minted, not re-minted
    tampered_row = _node_row(call.id, "escalate", reason="human_request")
    tampered_row.payload_json["escalation_reason"] = "opt_out"
    bad = verify_citations([tampered_row])
    assert bad["verified"] == 0
    assert bad["mismatches"][0]["kind"] == "escalation_reason"


def test_scaffolding_transitions_bind_empty_say_and_still_rederive():
    """Pre-speech hand-offs (ask_purpose et al.) bind ``{"say": ""}`` and the
    loop records no empty speech — the digest must re-derive from that
    binding, WITHOUT being mascaraed as a lost line."""
    from app.telephony.call_transcript import _citation_sha256, verify_citations

    call = _call()
    events = [_ev(call.id, "ai_agent.node",
                  {"node": "ask_purpose", "from": "verify_identity",
                   "to": "ask_purpose", "inputs_sha256": "in-z",
                   "output_sha256": _citation_sha256({"say": ""})},
                  _ts(T0, 90))]
    report = verify_citations(events)
    assert report["checked"] == 1 and report["verified"] == 1
    assert report["mismatches"] == []
    assert report["rederived"]["scaffolding_empty_say"] == 1
    assert report["rederived"]["verbatim_say"] == 0


def test_line_bound_digest_without_stored_speech_is_reported_not_fabricated():
    from app.telephony.call_transcript import verify_citations

    call = _call()
    events = [_node_row(call.id, "respond", say="words that never got written")]
    report = verify_citations(events)
    assert report["checked"] == 1 and report["verified"] == 0
    assert report["mismatches"][0]["kind"] == "say_line"


def test_verifier_is_honest_on_empty_and_citation_free_streams():
    from app.telephony.call_transcript import verify_citations

    report = verify_citations([])
    assert report["checked"] == 0 and report["verified"] == 0
    assert report["mismatches"] == [] and report["inputs_not_rederivable"] == 0

    call = _call()
    said_only = [_said(call.id, "respond", "a line with no transition")]
    report = verify_citations(said_only)
    assert report["checked"] == 0                      # nothing to verify


async def _drive_real_agent_session(services_app_client, user) -> str:
    """Full production write path (frames → segmenter → transcribe → loop →
    MediaCallEventSink → call_events), then the sid whose ledger to verify."""
    import asyncio

    from test_agent_media_session import (
        FakeARI,
        _create_call_session,
        dial_asterisk_like_client,
        make_runtime,
        media_start_text,
    )

    sid = f"talkflow-{uuid.uuid4()}"
    await _create_call_session(user["org_id"], user["user_id"], sid, "ai_agent")

    from app.telephony.media.agent_media_session import MediaCallEventSink

    sink = MediaCallEventSink(sid)

    async def known_transcribe(segment: list[bytes]) -> str:
        return "what is my remaining balance today"

    from app.telephony.ai_agent_graph import GraphConfig

    runtime = make_runtime(FakeARI(), sink, spec_overrides={
        "transcribe": known_transcribe,
        "segment_wait_seconds": 0.15,
        "graph_config": GraphConfig(verify_identity=False),
    })
    port = await runtime.start()
    try:
        session = runtime.start_for_call(sid, "caller-cite")
        client = await dial_asterisk_like_client(port)
        await client.send(media_start_text(session.media_channel_id))
        for _ in range(100):
            if session.conn is not None:
                break
            await asyncio.sleep(0.01)
        assert session.conn is not None, "MEDIA_START never attached"

        await client.send("MEDIA_XON")
        for _ in range(8):
            await client.send(b"\xff\x7f" * 320)      # real speech
        for _ in range(30):                            # 25+ finalize the segment
            await client.send(b"\x00" * 640)
        await asyncio.sleep(0.6)
        for _ in range(60):                            # bounded fail-closed tail
            if session.finished.is_set():
                break
            await client.send(b"\x00" * 640)
            await asyncio.sleep(0.05)
        await asyncio.wait_for(session.finished.wait(), timeout=10.0)
        await client.close()
    finally:
        await runtime.stop()
    return sid


async def test_real_production_stream_rederives_every_citation(
        services_app_client, user):
    """THE contract test: the actual graph's digests re-derive from the
    actual stored ledger — coupling between the two serializers guarded."""
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session
    from app.telephony.call_transcript import verify_citations

    sid = await _drive_real_agent_session(services_app_client, user)

    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession.id).where(M.CallSession.call_sid == sid))
        call_id = res.scalars().one()
        res = await db.execute(
            select(M.CallEvent).where(M.CallEvent.call_id == call_id))
        rows = list(res.scalars().all())

    transitions = [r for r in rows if r.event_type == "ai_agent.node"]
    assert any(r.payload_json.get("output_sha256") for r in transitions), \
        "vacuous drive: no hash-bearing transitions recorded"

    report = verify_citations(rows)
    assert report["mismatches"] == [], report["mismatches"]
    assert report["verified"] == report["checked"]
    assert report["checked"] >= 2                      # disclose + (respond|escalate)
    assert report["inputs_not_rederivable"] == report["checked"]
    # arithmetic holds and the re-derivation paths that the REAL graph emits
    # all fire: reason-bound escalation digests, and say-bound transitions —
    # which in the current graph bind the EMPTY say (the loop's payload
    # policy stages the spoken line on AgentStep.say AFTER the transition and
    # stores it verbatim in the said rows), so the verbatim bucket stays 0
    # here while the pure tests exercise it directly
    rederived = report["rederived"]
    assert (rederived["verbatim_say"] + rederived["escalation_reason"]
            + rederived["scaffolding_empty_say"]) == report["verified"]
    assert rederived["scaffolding_empty_say"] >= 1
    assert rederived["escalation_reason"] >= 1

    # the escalation leg re-derives from its own reason, end to end
    escalate = [r for r in transitions
                if r.payload_json.get("escalation_reason")]
    if escalate:
        assert all(m["node"] != "escalate" for m in report["mismatches"])


async def test_transcript_api_publishes_citation_integrity(
        services_app_client, user):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session
    from app.telephony.call_transcript import _citation_sha256

    sid = f"talkflow-{uuid.uuid4()}"
    disclosed = "This is an automated AI assistant."
    async with db_session() as db:
        res = await db.execute(select(M.CallSession).where(
            M.CallSession.call_sid == sid))
        row = res.scalars().first()
        if row is None:
            row = M.CallSession(
                org_id=uuid.UUID(user["org_id"]),
                created_by=uuid.UUID(user["user_id"]),
                call_sid=sid, from_number="1001", to_number="1002",
                mode="ai_agent", provider="asterisk", status="connected")
            db.add(row)
        await db.flush()
        base = datetime.now(timezone.utc)
        db.add(M.CallEvent(
            call_id=row.id, event_type="ai_agent.node",
            payload_json={"node": "disclose", "from": "disclose",
                          "to": "disclose", "inputs_sha256": "in-x",
                          "output_sha256": _citation_sha256({"say": disclosed})},
            created_at=base))
        db.add(M.CallEvent(
            call_id=row.id, event_type="agent_turn_said",
            payload_json={"node": "disclose", "action": "speak",
                          "text": disclosed, "frames_rendered": 0,
                          "tts": "absent"},
            created_at=base + timedelta(milliseconds=10)))
        db.add(M.CallEvent(
            call_id=row.id, event_type="ai_agent.node",
            payload_json={"node": "escalate", "from": "disclose",
                          "to": "escalate", "inputs_sha256": "in-y",
                          "output_sha256": _citation_sha256(
                              {"escalation_reason": "low_stt_confidence"}),
                          "escalation_reason": "low_stt_confidence"},
            created_at=base + timedelta(milliseconds=20)))
        await db.commit()

    r = services_app_client.get(f"/api/v1/telephony/calls/{sid}/transcript",
                                headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()

    integrity = body["citation_integrity"]
    assert integrity["checked"] == 2
    assert integrity["verified"] == 2
    assert integrity["mismatches"] == []
    assert integrity["inputs_not_rederivable"] == 2
    assert "counted, not re-computed" in integrity["note"]
    assert "re-derive" in body["meta"]["privacy"]["citations"]

