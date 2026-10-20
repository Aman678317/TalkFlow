"""P4 §C2 — call transcript & citation assembly.

Turns the call's immutable audit ledger (``call_events``) into an
operator-facing transcript, WITHOUT inventing anything:

- per-turn rows keyed by ``agent_turn_utterance`` (the turn number the loop
  stamped); the SPEAKER side is a fingerprint only (``text_len`` +
  ``text_sha256`` — raw caller speech never enters the ledger, so it can
  never leave it);
- the agent's own spoken lines are org-authored content and are surfaced
  verbatim (``agent_turn_said``), together with the TTS status;
- every ``ai_agent.node`` transition becomes a CITATION on the turn it
  happened in: from/to nodes plus the sha256 input/output digests — the
  machine's decisions stay verifiable against the ledger row;
- ``agent_turn_outcome`` (terminal status + escalation reason + summary);
- the escalation trail (``agent_escalation_*``, queue C1), the media/session
  timeline (bridge/codec/caption rows), and an honest count of any remaining
  event types (nothing is dropped silently).

The assembler is PURE: given the call row and its events in any arrival
order, it deterministically sorts by ``(created_at, id)`` and groups. It
belongs in the telephony package so future surfaces (UI transcript pages,
exports) reuse the exact same contract.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from app.db.models import CallEvent, CallSession

TURN_EVENT = "agent_turn_utterance"
SAID_EVENT = "agent_turn_said"
NODE_EVENT = "ai_agent.node"
OUTCOME_EVENT = "agent_turn_outcome"
ESCALATION_PREFIX = "agent_escalation_"
MEDIA_PREFIXES = ("agent_media_", "media_bridge_", "media_codec_", "call.caption_", "bridge_caption_")

#: the exact caller fingerprint vocabulary (privacy invariant: NOTHING raw)
CALLER_FINGERPRINT_KEYS = ("text_len", "text_sha256", "confidence", "frames")


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at is not None else None


def _ordered(events: Iterable[CallEvent]) -> list[CallEvent]:
    """Deterministic ledger order: wall clock, then row id as the tiebreak."""
    return sorted(events, key=lambda e: (e.created_at, str(e.id)))


def _blank_turn(at: datetime | None) -> dict[str, Any]:
    return {"turn": 0, "at": _iso(at), "caller": {}, "agent_lines": [],
            "citations": []}


def _citation_sha256(obj: Any) -> str:
    """Canonical citation digest.

    BYTE-IDENTICAL CONTRACT with ``ai_agent_graph._sha256``:
    ``json.dumps(obj, sort_keys=True, default=str).encode()`` → sha256.
    The real-graph re-derivation test drives the actual graph and re-computes
    its digests with THIS helper, so any drift between the two serializations
    fails the suite instead of silently voiding citations.
    """
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def verify_citations(events: Sequence[CallEvent]) -> dict[str, Any]:
    """§C4 — re-derive the transcript's sha256 citations from stored ledger
    material, and report honestly what cannot be re-derived.

    What a verifier CAN recompute post-hoc, bucket by bucket:

    - **verbatim say digests** bind ``{"say": <line>}`` at transition time;
      the turn loop stores the spoken line verbatim in ``agent_turn_said`` —
      the digest re-derives against the ledger's set of verbatim lines. A
      tampered line (or an edited digest) stops re-deriving and lands in
      ``mismatches``;
    - **escalation digests** bind ``{"escalation_reason": <reason>}``, which
      the citation itself carries — re-derivable directly;
    - **scaffolding say digests** bind the EMPTY say: pre-speech transitions
      (``ask_purpose`` hand-offs) never speak and the loop records no empty
      speech — such a digest equals ``sha256({"say": ""})`` and re-derives
      from the graph's own await-contract, cryptographically distinct from a
      lost line (which would bind non-empty text);
    - **input digests bind caller speech the ledger never stores**
      (fingerprint-only privacy invariant). They are COUNTED, never
      re-computed — pretending to verify them would fabricate trust.

    Pure: same ordering contract as the assembler
    (``(created_at, id)`` deterministic sort). Healthy stream invariant:
    ``verified == checked`` and ``mismatches == []``.
    """
    ordered_ev = _ordered(events)
    empty_say_digest = _citation_sha256({"say": ""})

    # the ledger's verbatim evidence: every distinct spoken line
    line_digests: set[str] = set()
    for event in ordered_ev:
        if event.event_type != SAID_EVENT:
            continue
        text = (dict(event.payload_json or {}).get("text") or "").strip()
        if text:
            line_digests.add(_citation_sha256({"say": text}))

    checked = verified = 0
    verbatim_say = reason_bound = empty_say = 0
    inputs_not_rederivable = 0
    mismatches: list[dict[str, Any]] = []

    for event in ordered_ev:
        if event.event_type != NODE_EVENT:
            continue
        payload = dict(event.payload_json or {})
        if payload.get("inputs_sha256"):
            # caller speech never entered the ledger: presence is all the
            # ledger can honestly attest
            inputs_not_rederivable += 1
        digest = payload.get("output_sha256")
        if not digest:
            continue
        checked += 1
        if payload.get("escalation_reason") is not None:
            expected = _citation_sha256(
                {"escalation_reason": payload["escalation_reason"]})
            if expected == digest:
                verified += 1
                reason_bound += 1
            else:
                mismatches.append({
                    "node": payload.get("to"), "kind": "escalation_reason",
                    "expected": expected, "found": digest,
                })
        elif digest == empty_say_digest:
            # the graph's await-scaffolding binds "" at transition time; a
            # lost line would bind non-empty text instead
            verified += 1
            empty_say += 1
        elif digest in line_digests:
            verified += 1
            verbatim_say += 1
        else:
            mismatches.append({
                "node": payload.get("to"), "kind": "say_line",
                "expected": None, "found": digest,
            })

    return {
        "checked": checked,
        "verified": verified,
        "rederived": {
            "verbatim_say": verbatim_say,
            "escalation_reason": reason_bound,
            "scaffolding_empty_say": empty_say,
        },
        "mismatches": mismatches,
        "inputs_not_rederivable": inputs_not_rederivable,
        "note": "input digests bind caller speech that the ledger never "
                "stores (fingerprint-only privacy) — counted, not "
                "re-computed; output digests re-derive from the verbatim "
                "said rows, the citations' own escalation reasons, or the "
                "graph's empty-say scaffolding binding",
    }


def assemble_transcript(call: CallSession, events: Sequence[CallEvent]) -> dict[str, Any]:
    """Assemble the full transcript dict (pure; see module docstring)."""
    turns: list[dict[str, Any]] = []
    outcome: dict[str, Any] | None = None
    escalations: list[dict[str, Any]] = []
    media_timeline: list[dict[str, Any]] = []
    unsurfaced: dict[str, int] = {}

    for event in _ordered(events):
        payload = dict(event.payload_json or {})
        etype = event.event_type
        at = _iso(event.created_at)

        if etype == TURN_EVENT:
            caller = {key: payload[key] for key in CALLER_FINGERPRINT_KEYS
                      if key in payload}
            turns.append({
                "turn": int(payload.get("turn", 0)),
                "at": at,
                "caller": caller,
                "agent_lines": [],
                "citations": [],
            })
        elif etype == SAID_EVENT:
            if not turns:  # greeting: the agent spoke before any caller turn
                turns.append(_blank_turn(event.created_at))
            turns[-1]["agent_lines"].append({
                "text": payload.get("text", ""),
                "node": payload.get("node"),
                "action": payload.get("action"),
                "tts": payload.get("tts"),
                "frames_rendered": payload.get("frames_rendered"),
            })
        elif etype == NODE_EVENT:
            if not turns:  # a decision can predate the first utterance in theory
                turns.append(_blank_turn(event.created_at))
            turns[-1]["citations"].append({
                "node": payload.get("node"),
                "from": payload.get("from"),
                "to": payload.get("to"),
                "inputs_sha256": payload.get("inputs_sha256"),
                "output_sha256": payload.get("output_sha256"),
                "escalation_reason": payload.get("escalation_reason"),
            })
        elif etype == OUTCOME_EVENT:
            outcome = {
                "at": at,
                "terminal": payload.get("terminal"),
                "escalation_reason": payload.get("escalation_reason"),
                "summary": payload.get("summary"),
                "turns": payload.get("turns"),
            }
        elif etype.startswith(ESCALATION_PREFIX):
            escalations.append({"event": etype, "at": at, "payload": payload})
        elif etype.startswith(MEDIA_PREFIXES):
            media_timeline.append({"event": etype, "at": at, "payload": payload})
        else:
            # honest accounting: surfaced nowhere, lost nowhere
            unsurfaced[etype] = unsurfaced.get(etype, 0) + 1

    return {
        "call": {
            "id": str(call.id),
            "call_sid": call.call_sid,
            "direction": call.direction,
            "mode": call.mode,
            "status": call.status,
            "provider": call.provider,
            "caller_language": call.caller_language,
            "receiver_language": call.receiver_language,
            "from_number": call.from_number,
            "to_number": call.to_number,
            "started_at": _iso(call.started_at),
            "connected_at": _iso(call.connected_at),
            "ended_at": _iso(call.ended_at),
            "duration_seconds": call.duration_seconds,
        },
        "turns": turns,
        "outcome": outcome,
        "escalations": escalations,
        "media_timeline": media_timeline,
        "citation_integrity": verify_citations(events),
        "unsurfaced_events": unsurfaced,
        "meta": {
            "privacy": {
                "caller_speech": "fingerprints only (text_len + text_sha256) — "
                                 "raw caller text never enters the ledger",
                "agent_lines": "verbatim (org-authored content)",
                "citations": "ai_agent.node sha256 digests; output digests "
                             "re-derive from the verbatim said rows, input "
                             "digests are counted but never re-computed "
                             "(caller speech is not stored)",
            },
            "turns": len(turns),
            "events_total": len(events),
        },
    }
