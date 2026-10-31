"""Contract compatibility tests between Agent 01 and Agent 02."""
import base64
from app.integration.agent01_adapter import Agent01Adapter
from app.integration.talkflow_adapter import TalkFlowAdapter
from app.providers.fallback.mock_provider import MockSTTProvider
from app.stt.engine import STTEngine
from tests.fixtures.audio_fixtures import generate_tone


def test_agent01_event_roundtrip_to_agent03_contract():
    tone_pcm = generate_tone(440.0, 1.0, 16000)
    b64_audio = base64.b64encode(tone_pcm).decode()

    # Exact event schema emitted by Agent 01
    agent01_event = {
        "version": 1,
        "type": "audio.segment.final",
        "session_id": "session_alpha_101",
        "conversation_id": "conv_alpha_101",
        "speaker_id": "speaker_lead",
        "utterance_id": "utt_01JBCDEF",
        "segment_id": "seg_01JBCDEF",
        "seq": 14,
        "payload": {
            "segment_id": "seg_01JBCDEF",
            "sequence_number": 14,
            "start_timestamp": 2.50,
            "end_timestamp": 3.50,
            "duration_seconds": 1.00,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm16",
            "audio_data_base64": b64_audio,
            "quality_metrics": {
                "rms_dbfs": -21.4,
                "peak_dbfs": -8.1,
                "snr_db": 24.2,
                "clipping_ratio": 0.0,
                "silence_ratio": 0.05,
                "confidence": 0.98,
            },
            "is_final": True,
        },
    }

    # 1. Parse Agent 01 event
    parsed = Agent01Adapter.parse_event(agent01_event)
    pcm16, meta = Agent01Adapter.extract_pcm16_and_meta(parsed)
    assert len(pcm16) == len(tone_pcm)
    assert meta["segment_id"] == "seg_01JBCDEF"
    assert meta["start_ms"] == 2500

    # 2. Transcribe via STT Engine
    engine = STTEngine(provider=MockSTTProvider(default_text="Multilingual speech recognition test"))
    resp = engine.transcribe_segment(
        audio_pcm16=pcm16,
        session_id=meta["session_id"],
        conversation_id=meta["conversation_id"],
        speaker_id=meta["speaker_id"],
        utterance_id=meta["utterance_id"],
        segment_id=meta["segment_id"],
        seq=meta["seq"],
        start_ms=meta["start_ms"],
        sample_rate=meta["sample_rate"],
    )

    # 3. Format into Agent 03 Outbound Contract
    final_evt = engine.finalizer.to_event(resp, seq=meta["seq"])
    formatted = TalkFlowAdapter.format_final_event(final_evt)

    assert formatted["type"] == "transcript.final"
    assert formatted["session_id"] == "session_alpha_101"
    assert formatted["segment_id"] == "seg_01JBCDEF"
    assert formatted["sequence_hint"] == 14
    assert formatted["text"] == "Multilingual speech recognition test"
    assert formatted["is_final"] is True
    # Word timestamps aligned with base start_ms (2500ms = 2.5s)
    assert formatted["words"][0]["start"] >= 2.5

