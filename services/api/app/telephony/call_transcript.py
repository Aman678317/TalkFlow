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
        "unsurfaced_events": unsurfaced,
        "meta": {
            "privacy": {
                "caller_speech": "fingerprints only (text_len + text_sha256) — "
                                 "raw caller text never enters the ledger",
                "agent_lines": "verbatim (org-authored content)",
                "citations": "ai_agent.node sha256 digests, resolved against "
                             "call_events rows",
            },
            "turns": len(turns),
            "events_total": len(events),
        },
    }
