"""Control-plane planner tests; no real audio, DB or provider calls."""
from __future__ import annotations

import pytest

from app.realtime.realtime_graph import (
    _deliver_gate,
    _failure_gate,
    _listening_gate,
    _supervisor,
    _translation_gate,
    _voice_gate,
    create_realtime_graph,
    normalize_control_event,
    plan_realtime_event,
    thread_config,
)


def test_partial_transcript_never_reaches_translation():
    state = normalize_control_event({
        "event_type": "transcript.partial",
        "transcript_text": "hello",
        "target_languages": ["hi", "fr"],
    })

    result = _supervisor(state)

    assert result["action"] == "wait_for_final_transcript"
    assert result["route"] == "end"
    assert result["should_translate"] is False


def test_final_transcript_plans_one_translation_per_distinct_target():
    state = normalize_control_event({
        "event_type": "transcript.final",
        "meeting_id": "meeting-1",
        "speaker_id": "speaker-1",
        "segment_id": "segment-7",
        "source_language": "hi",
        "transcript_text": "Namaste",
        "target_languages": ["en", "EN", "fr", "hi", " fr "],
    })

    supervised = {**state, **_supervisor(state)}
    listening = {**supervised, **_listening_gate(supervised)}
    result = _translation_gate(listening)

    assert result["action"] == "request_translation"
    assert result["next_agent"] == "TranslationAgent"
    assert result["should_translate"] is True
    assert result["canonical_target_languages"] == ["en", "fr"]


def test_empty_final_transcript_is_ignored():
    state = normalize_control_event({
        "event_type": "transcript.final",
        "transcript_text": "   ",
        "target_languages": ["en"],
    })

    result = _listening_gate({**state, **_supervisor(state)})

    assert result["action"] == "ignore_empty_final"
    assert result["should_translate"] is False


def test_consent_gate_pauses_ai_work_but_keeps_original_audio_path():
    state = normalize_control_event({
        "event_type": "transcript.final",
        "consent_required": True,
        "consent_granted": False,
    })

    result = _supervisor(state)

    assert result["action"] == "pause_for_approval"
    assert result["reason"] == "consent_required"
    assert result["original_audio_passthrough"] is True
    assert result["route"] == "end"


def test_barge_in_cancels_only_the_initiating_speaker():
    state = normalize_control_event({
        "event_type": "interrupt",
        "speaker_id": "speaker-a",
    })

    result = _supervisor(state)

    assert result["action"] == "cancel_speaker_audio"
    assert result["cancel_speaker_id"] == "speaker-a"
    assert result["should_duck_audio"] is True
    assert result["original_audio_passthrough"] is True


def test_unscoped_barge_in_is_rejected_instead_of_cancelling_everyone():
    state = normalize_control_event({"event_type": "interrupt"})

    result = _supervisor(state)

    assert result["action"] == "reject_unscoped_interrupt"
    assert result["cancel_speaker_id"] == ""


def test_reconnect_replays_after_last_confirmed_sequence():
    state = normalize_control_event({
        "event_type": "session.resume",
        "last_sequence": "42",
    })

    result = _supervisor(state)

    assert result["action"] == "replay_after_sequence"
    assert result["replay_after_sequence"] == 42


def test_language_change_rebuilds_only_the_requested_language_set():
    state = normalize_control_event({
        "event_type": "language.changed",
        "source_language": "en",
        "target_languages": ["fr", "FR", "en", "de"],
    })

    result = _supervisor(state)

    assert result["action"] == "refresh_recipient_routes"
    assert result["canonical_target_languages"] == ["fr", "de"]


def test_translation_failure_keeps_original_audio_and_captions_available():
    state = normalize_control_event({
        "event_type": "stage.failed",
        "failure_stage": "translation",
        "failure_code": "provider_timeout",
    })

    supervised = {**state, **_supervisor(state)}
    result = _failure_gate(supervised)

    assert result["action"] == "emit_translation_failed_keep_original"
    assert result["original_audio_passthrough"] is True
    assert result["should_translate"] is False
    assert result["should_synthesize"] is False


def test_voice_gate_requests_tts_only_for_a_successful_translation():
    good = normalize_control_event({
        "event_type": "translation.ready",
        "translation_ok": True,
        "translated_text": "Hello",
        "target_language": "en",
    })
    ready = _voice_gate(good)

    assert ready["action"] == "request_tts"
    assert ready["should_synthesize"] is True

    bad = normalize_control_event({
        "event_type": "translation.ready",
        "translation_ok": False,
        "translated_text": "",
        "target_languages": ["en"],
    })
    failed = _voice_gate(bad)
    assert failed["action"] == "emit_translation_failed_keep_original"
    assert failed["original_audio_passthrough"] is True


def test_tts_chunk_control_event_never_contains_raw_audio():
    state = normalize_control_event({
        "event_type": "tts.chunk.ready",
        "chunk_index": 3,
        "payload_bytes": 12800,
    })

    result = _deliver_gate(state)

    assert result["action"] == "deliver_tts_chunk_binary"
    assert result["should_emit_tts_metadata"] is True
    assert "audio_bytes" not in state
    assert "audio" not in state


def test_thread_config_is_scoped_and_bounded():
    assert thread_config("meeting-7") == {
        "configurable": {"thread_id": "talkflow:meeting-7"}
    }
    with pytest.raises(ValueError):
        thread_config("")
    with pytest.raises(ValueError):
        thread_config("m" * 201)


def test_compiled_graph_routes_a_final_transcript_end_to_end():
    pytest.importorskip("langgraph.graph")
    graph = create_realtime_graph()
    result = plan_realtime_event(graph, {
        "event_type": "transcript.final",
        "meeting_id": "meeting-1",
        "speaker_id": "speaker-1",
        "segment_id": "segment-1",
        "source_language": "hi",
        "transcript_text": "Namaste",
        "target_languages": ["en", "EN", "fr"],
    })

    assert result["action"] == "request_translation"
    assert result["canonical_target_languages"] == ["en", "fr"]
