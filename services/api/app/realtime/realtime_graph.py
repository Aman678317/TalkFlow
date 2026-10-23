"""Experimental LangGraph control plane for TalkFlow realtime calls.

The existing WebSocket, PCM16 binary transport, AgentBus and four realtime
agents remain the data plane. This graph only plans a control action for a
completed protocol/agent event; it does not process audio bytes, call inference
providers, or replace the production pipeline.

Keep it off the audio-frame hot path. Enable shadow observation first and
measure the overhead before connecting any decision to live dispatch.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypedDict


class RealtimeControlState(TypedDict, total=False):
    """Small, serializable state envelope for one control-plane decision."""

    event_type: str
    meeting_id: str
    speaker_id: str
    correlation_id: str
    segment_id: str
    source_language: str
    target_languages: list[str]
    transcript_text: str
    translated_text: str
    is_final: bool
    policy_allowed: bool
    consent_required: bool
    consent_granted: bool
    barge_in: bool
    reconnect: bool
    last_sequence: int
    failure_stage: str
    failure_code: str
    translation_ok: bool
    chunk_index: int | None
    payload_bytes: int
    route: str
    action: str
    next_agent: str
    reason: str
    should_translate: bool
    should_synthesize: bool
    should_duck_audio: bool
    should_emit_tts_metadata: bool
    original_audio_passthrough: bool
    replay_after_sequence: int
    cancel_speaker_id: str
    canonical_target_languages: list[str]


_DEFAULTS: dict[str, Any] = {
    "event_type": "",
    "meeting_id": "",
    "speaker_id": "",
    "correlation_id": "",
    "segment_id": "",
    "source_language": "",
    "target_languages": [],
    "transcript_text": "",
    "translated_text": "",
    "is_final": False,
    "policy_allowed": True,
    "consent_required": False,
    "consent_granted": False,
    "barge_in": False,
    "reconnect": False,
    "last_sequence": 0,
    "failure_stage": "",
    "failure_code": "",
    "translation_ok": True,
    "chunk_index": None,
    "payload_bytes": 0,
    "route": "end",
    "action": "no_op",
    "next_agent": "",
    "reason": "",
    "should_translate": False,
    "should_synthesize": False,
    "should_duck_audio": False,
    "should_emit_tts_metadata": False,
    "original_audio_passthrough": True,
    "replay_after_sequence": 0,
    "cancel_speaker_id": "",
    "canonical_target_languages": [],
}


def normalize_control_event(event: Mapping[str, Any]) -> RealtimeControlState:
    """Fill every known field so checkpoints cannot leak stale event flags."""
    values = dict(_DEFAULTS)
    values.update(event)
    if not values.get("event_type") and values.get("type"):
        values["event_type"] = values["type"]
    values["event_type"] = str(values.get("event_type") or "").strip().lower()

    raw_targets = values.get("target_languages")
    if isinstance(raw_targets, str):
        raw_targets = [raw_targets]
    if not isinstance(raw_targets, (list, tuple, set)):
        raw_targets = []
    values["target_languages"] = list(raw_targets)

    for name in ("last_sequence", "payload_bytes"):
        try:
            values[name] = max(0, int(values.get(name) or 0))
        except (TypeError, ValueError):
            values[name] = 0
    return values  # type: ignore[return-value]


def _unique_target_languages(targets: Sequence[Any], source_language: str = "") -> list[str]:
    """Normalize language tags and preserve first-seen order, once per language."""
    source = str(source_language or "").strip().lower()
    seen: set[str] = set()
    result: list[str] = []
    for value in targets:
        if not isinstance(value, str):
            continue
        lang = value.strip().lower()
        if not lang or lang == source or lang in seen:
            continue
        seen.add(lang)
        result.append(lang)
    return result


def _supervisor(state: RealtimeControlState) -> dict[str, Any]:
    """Apply safety/recovery decisions before selecting a logical agent."""
    event_type = state.get("event_type", "")
    base: dict[str, Any] = {
        "route": "end",
        "action": "no_op",
        "next_agent": "",
        "reason": "",
        "should_translate": False,
        "should_synthesize": False,
        "should_duck_audio": False,
        "should_emit_tts_metadata": False,
        "original_audio_passthrough": True,
        "replay_after_sequence": 0,
        "cancel_speaker_id": "",
        "canonical_target_languages": [],
    }

    if not state.get("policy_allowed", True):
        return {**base, "action": "block_ai_processing",
                "reason": "policy_blocked"}
    if state.get("consent_required") and not state.get("consent_granted"):
        return {**base, "action": "pause_for_approval",
                "reason": "consent_required"}

    # Cancellation must be scoped to the initiating speaker. Never cancel all
    # recipients or another participant's current TTS queue.
    if state.get("barge_in") or event_type == "interrupt":
        speaker = str(state.get("speaker_id") or "").strip()
        if not speaker:
            return {**base, "action": "reject_unscoped_interrupt",
                    "reason": "speaker_id_required_for_barge_in"}
        return {
            **base,
            "action": "cancel_speaker_audio",
            "next_agent": "Supervisor",
            "reason": "speaker_barge_in",
            "should_duck_audio": True,
            "cancel_speaker_id": speaker,
        }

    if state.get("reconnect") or event_type in {"session.resume", "session.resumed"}:
        return {
            **base,
            "action": "replay_after_sequence",
            "next_agent": "Supervisor",
            "reason": "session_reconnect",
            "replay_after_sequence": max(0, state.get("last_sequence", 0)),
        }

    if event_type == "language.changed":
        targets = _unique_target_languages(
            state.get("target_languages", []), state.get("source_language", ""))
        return {
            **base,
            "action": "refresh_recipient_routes",
            "next_agent": "Supervisor",
            "reason": "recipient_language_changed",
            "canonical_target_languages": targets,
        }

    if event_type == "session.closed":
        return {**base, "action": "close_control_session",
                "next_agent": "Supervisor", "reason": "session_closed"}

    if event_type in {"stage.failed", "translation.failed", "tts.failed", "stt.failed"}:
        return {**base, "route": "failure", "next_agent": "Supervisor",
                "reason": state.get("failure_stage") or event_type}

    if event_type == "transcript.partial":
        return {**base, "action": "wait_for_final_transcript",
                "next_agent": "ListeningAgent", "reason": "partial_is_unstable"}

    if event_type == "transcript.final":
        return {**base, "route": "listening", "next_agent": "ListeningAgent",
                "reason": "canonical_source_finalized"}

    if event_type == "translation.ready":
        return {**base, "route": "voice", "next_agent": "VoiceAgent",
                "reason": "translation_ready_for_tts"}

    if event_type == "tts.chunk.ready":
        return {**base, "route": "deliver", "next_agent": "Supervisor",
                "reason": "tts_chunk_ready"}

    return {**base, "reason": "unsupported_or_observational_event"}


def _listening_gate(state: RealtimeControlState) -> dict[str, Any]:
    """Never request translation from partial or empty source text."""
    event_type = state.get("event_type", "")
    is_final = event_type == "transcript.final" or bool(state.get("is_final"))
    text = str(state.get("transcript_text") or "").strip()
    if not is_final:
        return {"route": "end", "action": "wait_for_final_transcript",
                "should_translate": False, "next_agent": "ListeningAgent",
                "reason": "partial_is_unstable"}
    if not text:
        return {"route": "end", "action": "ignore_empty_final",
                "should_translate": False, "reason": "empty_canonical_transcript"}
    return {"route": "translation", "action": "plan_translation",
            "should_translate": False, "reason": "final_transcript_accepted"}


def _translation_gate(state: RealtimeControlState) -> dict[str, Any]:
    """Plan one translation per unique requested target language."""
    targets = _unique_target_languages(
        state.get("target_languages", []), state.get("source_language", ""))
    if not targets:
        return {"route": "end", "action": "no_translation_targets",
                "canonical_target_languages": [],
                "should_translate": False, "next_agent": "",
                "reason": "no_distinct_target_languages"}
    return {
        "route": "end",
        "action": "request_translation",
        "next_agent": "TranslationAgent",
        "canonical_target_languages": targets,
        "should_translate": True,
        "reason": "final_only_deduplicated_fanout",
    }


def _voice_gate(state: RealtimeControlState) -> dict[str, Any]:
    """Schedule synthesis only after a successful translation result."""
    text = str(state.get("translated_text") or "").strip()
    target = str((state.get("target_languages") or [""])[0] or "").strip()
    if not state.get("translation_ok", True) or not text:
        return {
            "route": "end",
            "action": "emit_translation_failed_keep_original",
            "next_agent": "Supervisor",
            "should_synthesize": False,
            "original_audio_passthrough": True,
            "reason": "translation_missing_or_failed",
        }
    if not target:
        return {"route": "end", "action": "skip_tts_missing_target",
                "should_synthesize": False, "reason": "target_language_required"}
    return {"route": "end", "action": "request_tts",
            "next_agent": "VoiceAgent", "should_synthesize": True,
            "reason": "translation_ready"}


def _deliver_gate(state: RealtimeControlState) -> dict[str, Any]:
    """Permit binary chunk delivery based on metadata; audio bytes stay elsewhere."""
    return {
        "route": "end",
        "action": "deliver_tts_chunk_binary",
        "next_agent": "Supervisor",
        "should_emit_tts_metadata": True,
        "reason": "metadata_only_control_event",
    }


def _failure_gate(state: RealtimeControlState) -> dict[str, Any]:
    """Fail open for the meeting while retaining original audio/captions."""
    stage = str(state.get("failure_stage") or state.get("event_type") or "").lower()
    if stage in {"mt", "translation", "translation.failed"}:
        action = "emit_translation_failed_keep_original"
    elif stage in {"tts", "tts.failed"}:
        action = "emit_tts_failed_keep_captions"
    elif stage in {"stt", "stt.failed"}:
        action = "emit_stt_failed_keep_original_audio"
    else:
        action = "emit_recoverable_stage_failure"
    return {
        "route": "end",
        "action": action,
        "next_agent": "Supervisor",
        "should_translate": False,
        "should_synthesize": False,
        "original_audio_passthrough": True,
        "reason": str(state.get("failure_code") or stage or "stage_failed"),
    }


def _after_supervisor(state: RealtimeControlState) -> str:
    return state.get("route", "end")


def _after_listening(state: RealtimeControlState) -> str:
    return state.get("route", "end")


def create_realtime_graph(
    *,
    checkpointer: Any = None,
    interrupt_before: Sequence[str] = (),
) -> Any:
    """Build the optional LangGraph planner.

    Pass InMemorySaver() for local experiments or a durable checkpointer
    for production session recovery. No checkpointer is created implicitly.
    Static interrupt breakpoints are opt-in for operator/debug flows only; do
    not pause every live utterance in the real-time call path.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # serverless requirements intentionally omit it
        raise RuntimeError(
            "LangGraph is not installed in this runtime. For local development "
            "run python -m pip install -e '.[dev]' from services/api."
        ) from exc

    allowed_nodes = {
        "supervisor", "listening_gate", "translation_gate",
        "voice_gate", "deliver_gate", "failure_gate",
    }
    unknown = set(interrupt_before) - allowed_nodes
    if unknown:
        raise ValueError(f"Unknown interrupt_before node(s): {sorted(unknown)}")

    graph = StateGraph(RealtimeControlState)
    graph.add_node("supervisor", _supervisor)
    graph.add_node("listening_gate", _listening_gate)
    graph.add_node("translation_gate", _translation_gate)
    graph.add_node("voice_gate", _voice_gate)
    graph.add_node("deliver_gate", _deliver_gate)
    graph.add_node("failure_gate", _failure_gate)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", _after_supervisor, {
        "listening": "listening_gate",
        "voice": "voice_gate",
        "deliver": "deliver_gate",
        "failure": "failure_gate",
        "end": END,
    })
    graph.add_conditional_edges("listening_gate", _after_listening, {
        "translation": "translation_gate",
        "end": END,
    })
    for node in ("translation_gate", "voice_gate", "deliver_gate", "failure_gate"):
        graph.add_edge(node, END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=list(interrupt_before) or None,
    )


def thread_config(meeting_id: str) -> dict[str, dict[str, str]]:
    """LangGraph checkpoint config; use one bounded thread id per meeting."""
    thread_id = str(meeting_id or "").strip()
    if not thread_id:
        raise ValueError("meeting_id is required for checkpointed graph runs")
    if len(thread_id) > 200:
        raise ValueError("meeting_id/thread_id must be 200 characters or fewer")
    return {"configurable": {"thread_id": f"talkflow:{thread_id}"}}


def plan_realtime_event(
    graph: Any,
    event: Mapping[str, Any],
    *,
    meeting_id: str | None = None,
) -> RealtimeControlState:
    """Normalize and evaluate one event, optionally checkpointed by meeting."""
    normalized = normalize_control_event(event)
    config = thread_config(meeting_id) if meeting_id else None
    return graph.invoke(normalized, config=config)
