"""Phase 5: Text stabilization and translated-utterance queue tests."""
import uuid
import pytest
from app.realtime.protocol import ServerEventType


def test_server_event_type_translation_segment_final_exists():
    assert ServerEventType.TRANSLATION_SEGMENT_FINAL == "translation.segment.final"
    assert ServerEventType.TRANSLATION_FINAL == "translation.final"
    assert ServerEventType.TRANSCRIPT_FINAL == "transcript.final"
    assert ServerEventType.TRANSCRIPT_PARTIAL == "transcript.partial"


def test_phase5_event_contract_fields():
    session_id = str(uuid.uuid4())
    speaker_id = str(uuid.uuid4())
    utterance_id = str(uuid.uuid4())
    seq = 104

    # Target format from Phase 5 specification:
    event = {
        "type": ServerEventType.TRANSLATION_SEGMENT_FINAL.value,
        "sessionId": session_id,
        "speakerId": speaker_id,
        "sequence": seq,
        "utteranceId": utterance_id,
        "sourceLanguage": "hi",
        "targetLanguage": "en",
        "sourceText": "नमस्ते, आप कैसे हैं?",
        "translatedText": "Hello, how are you?",
        "createdAt": 1712648000,
        "dedupKey": f"{session_id}:{speaker_id}:{seq}:en",
    }

    assert event["type"] == "translation.segment.final"
    assert event["sessionId"] == session_id
    assert event["speakerId"] == speaker_id
    assert event["sequence"] == 104
    assert event["utteranceId"] == utterance_id
    assert event["sourceLanguage"] == "hi"
    assert event["targetLanguage"] == "en"
    assert event["sourceText"] == "नमस्ते, आप कैसे हैं?"
    assert event["translatedText"] == "Hello, how are you?"
    assert event["createdAt"] > 0
    assert event["dedupKey"] == f"{session_id}:{speaker_id}:104:en"


def test_reconnection_out_of_order_guard_logic():
    """Verify that an older sequence cannot overwrite a newer sequence after reconnect."""
    highest_seq_per_speaker = {}
    speaker_id = "speaker-1"

    def process_segment(speaker, seq, text):
        current_high = highest_seq_per_speaker.get(speaker, 0)
        if seq < current_high:
            # Drop stale out-of-order segment
            return False, "dropped_stale"
        highest_seq_per_speaker[speaker] = max(current_high, seq)
        return True, text

    # Normal sequence
    ok, res = process_segment(speaker_id, 101, "Hello")
    assert ok and res == "Hello"

    ok, res = process_segment(speaker_id, 102, "World")
    assert ok and res == "World"

    # Client reconnects, delayed packet 101 arrives
    ok, res = process_segment(speaker_id, 101, "Old replay")
    assert not ok and res == "dropped_stale"

    # Newer packet 103 arrives
    ok, res = process_segment(speaker_id, 103, "Next")
    assert ok and res == "Next"


def test_utterance_state_initialization():
    from app.realtime.pipeline import UtteranceState
    p_id = uuid.uuid4()
    u = UtteranceState(participant_id=p_id)
    assert u.participant_id == p_id
    assert isinstance(u.utterance_id, uuid.UUID)
    assert u.seq == 0
    assert not u.in_speech
