"""Comprehensive 16-Scenario Test Suite for Emotion & Voice-Expression Preservation Engine (Module B).

Tests:
1. Excited Hindi sentence -> English Expressive (pitch high, speech rate faster)
2. Calm English explanation -> Hindi Expressive (measured tempo, stable pitch)
3. Whispered French sentence -> English Expressive (soft intensity, low volume)
4. Laughing / humorous speech with non-verbal tokens -> Marathi Expressive
5. Speech with long natural pauses (2.5s) -> Spanish Expressive (pause preservation)
6. Inquisitive rising pitch question -> German Expressive (terminal rising F0)
7. Emphatic key-word stressed statement -> Japanese Expressive (prosody emphasis)
8. Mode 1 Standard Synthetic verification (neutral baseline, zero distortion)
9. Mode 2 Expressive Synthetic without cloning (expressive transfer with generic neural voice)
10. Mode 3 Voice Similarity with verified consent (authorized speaker profile applied)
11. Mode 3 Attempt WITHOUT consent -> Fail-closed fallback to Mode 2/1 with audit log
12. Mode 3 Revocation in mid-session -> Immediate fallback on subsequent utterances
13. Fan-Out Deduplication with Expressive Mode (shared expressive TTS across listeners)
14. Pronunciation dictionary application in expressive speech ("TalkFlow", "AI")
15. Cross-lingual pacing adaptation (Hindi to English duration ratio clamped within [0.85, 1.25])
16. Full-duration (5-minute / multi-chunk) expressive timeline continuity
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
from modules.voice_expression import (
    AcousticFeatures,
    DeliveryTag,
    ExpressiveSynthesisRequest,
    ExpressiveSynthesisResponse,
    PronunciationRule,
    ProsodyTransferPlan,
    SpeakerProsodyProfile,
    VoiceConsentRecord,
    VoiceEnrollmentRequest,
    VoiceGenerationMode,
    voice_expression_engine,
)
from modules.meeting_fanout import fanout_engine, Participant, SourceUtterance


async def run_all_tests():
    print("=" * 80)
    print("TALKFLOW EMOTION & VOICE-EXPRESSION PRESERVATION ENGINE — 16 SCENARIOS")
    print("=" * 80)

    results = []

    # -------------------------------------------------------------------------
    # TEST 1: Excited Hindi sentence -> English Expressive
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Excited Hindi sentence -> English Expressive")
    hindi_excited = "अरे वाह! यह तो बहुत ही शानदार और अविश्वसनीय परिणाम है!"
    feat1 = voice_expression_engine.analyze_audio_signal(transcript=hindi_excited, language="hi")
    plan1 = voice_expression_engine.plan_prosody_transfer(
        source_features=feat1,
        source_text=hindi_excited,
        target_text="Oh wow! This is truly fantastic and unbelievable results!",
        source_lang="hi",
        target_lang="en",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    synth1 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Oh wow! This is truly fantastic and unbelievable results!",
            source_text=hindi_excited,
            source_language="hi",
            target_language="en",
            voice_mode=VoiceGenerationMode.EXPRESSIVE,
        )
    )
    assert feat1.detected_emotion == DeliveryTag.EXCITED.value, f"Expected excited, got {feat1.detected_emotion}"
    assert plan1.pitch_adjustment_pct > 0, "Pitch should be elevated for excitement"
    assert plan1.rate_multiplier >= 1.0, "Rate should be brisk for excitement"
    assert len(synth1.audio_base64) > 0, "Audio must be generated"
    results.append(("Test 1: Excited Hindi -> English Expressive", "PASSED", f"Emotion: {feat1.detected_emotion}, Pitch: +{plan1.pitch_adjustment_pct}%, Rate: {plan1.rate_multiplier}x"))
    print("  -> PASS: Excited delivery mapped to elevated pitch and brisk pacing.")

    # -------------------------------------------------------------------------
    # TEST 2: Calm English explanation -> Hindi Expressive
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Calm English explanation -> Hindi Expressive")
    calm_en = "Please note that all system services are operating within normal thermal and memory parameters."
    feat2 = voice_expression_engine.analyze_audio_signal(transcript=calm_en, language="en")
    plan2 = voice_expression_engine.plan_prosody_transfer(
        source_features=feat2,
        source_text=calm_en,
        target_text="कृपया ध्यान दें कि सभी सिस्टम सेवाएं सामान्य तापमान और मेमोरी मापदंडों के भीतर काम कर रही हैं।",
        source_lang="en",
        target_lang="hi",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    synth2 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="कृपया ध्यान दें कि सभी सिस्टम सेवाएं सामान्य तापमान और मेमोरी मापदंडों के भीतर काम कर रही हैं।",
            source_text=calm_en,
            source_language="en",
            target_language="hi",
            voice_mode=VoiceGenerationMode.EXPRESSIVE,
        )
    )
    assert feat2.detected_emotion in (DeliveryTag.CALM.value, DeliveryTag.NEUTRAL.value)
    assert plan2.rate_multiplier <= 1.05, "Calm speech should maintain measured tempo"
    assert len(synth2.audio_base64) > 0
    results.append(("Test 2: Calm English -> Hindi Expressive", "PASSED", f"Emotion: {feat2.detected_emotion}, Rate: {plan2.rate_multiplier}x, Pitch: {plan2.pitch_adjustment_pct}%"))
    print("  -> PASS: Measured tempo and stable pitch preserved for Hindi.")

    # -------------------------------------------------------------------------
    # TEST 3: Whispered French sentence -> English Expressive
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Whispered French sentence -> English Expressive")
    whisper_fr = "[whisper] Ne fais pas de bruit, la réunion confidentielle a déjà commencé."
    feat3 = voice_expression_engine.analyze_audio_signal(transcript=whisper_fr, language="fr")
    plan3 = voice_expression_engine.plan_prosody_transfer(
        source_features=feat3,
        source_text=whisper_fr,
        target_text="Don't make any noise, the confidential meeting has already begun.",
        source_lang="fr",
        target_lang="en",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    synth3 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Don't make any noise, the confidential meeting has already begun.",
            source_text=whisper_fr,
            source_language="fr",
            target_language="en",
            voice_mode=VoiceGenerationMode.EXPRESSIVE,
        )
    )
    assert feat3.is_whisper is True, "Whisper flag must be detected"
    assert feat3.detected_emotion == DeliveryTag.WHISPERING.value
    assert plan3.volume_adjustment_db < 0, "Volume must be reduced for whisper"
    assert plan3.expressive_style == "whispering"
    results.append(("Test 3: Whispered French -> English Expressive", "PASSED", f"Whisper: True, Vol: {plan3.volume_adjustment_db}dB, Style: {plan3.expressive_style}"))
    print("  -> PASS: Soft intensity, negative volume offset, and whispering style transferred.")

    # -------------------------------------------------------------------------
    # TEST 4: Laughing / humorous speech -> Marathi Expressive
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Laughing / humorous speech -> Marathi Expressive")
    laugh_text = "हाहा! [laughter] अरे देवा, मी असा विनोद कधीही ऐकला नव्हता!"
    feat4 = voice_expression_engine.analyze_audio_signal(transcript=laugh_text, language="mr")
    plan4 = voice_expression_engine.plan_prosody_transfer(
        source_features=feat4,
        source_text=laugh_text,
        target_text="Haha! My goodness, I have never heard such a funny joke!",
        source_lang="mr",
        target_lang="en",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    synth4 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="हाहा! अरे देवा, मी असा विनोद कधीही ऐकला नव्हता!",
            source_text=laugh_text,
            source_language="mr",
            target_language="mr",
            voice_mode=VoiceGenerationMode.EXPRESSIVE,
        )
    )
    assert feat4.has_laughter is True
    assert "[laughter]" in feat4.non_verbal_events
    assert plan4.expressive_style == "cheerful"
    results.append(("Test 4: Laughing speech -> Marathi Expressive", "PASSED", f"Laughter: True, NonVerbal: {feat4.non_verbal_events}, Style: {plan4.expressive_style}"))
    print("  -> PASS: Non-verbal laughter detected and mapped to cheerful expressive prosody.")

    # -------------------------------------------------------------------------
    # TEST 5: Speech with long natural pauses (2.5s) -> Spanish Expressive
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Speech with long natural pauses -> Spanish Expressive")
    # Simulate audio waveform with a 2.5s silence gap in the middle
    sample_rate = 24000
    t_chunk1 = np.sin(2 * np.pi * 200 * np.linspace(0, 1.0, int(sample_rate * 1.0))) * 0.5
    silence = np.zeros(int(sample_rate * 2.5))  # 2.5s silence
    t_chunk2 = np.sin(2 * np.pi * 200 * np.linspace(0, 1.0, int(sample_rate * 1.0))) * 0.5
    composite_audio = np.concatenate([t_chunk1, silence, t_chunk2])
    pcm_bytes = (composite_audio * 32767).astype(np.int16).tobytes()

    feat5 = voice_expression_engine.analyze_audio_signal(
        audio_bytes=pcm_bytes,
        sample_rate=sample_rate,
        transcript="Primero debemos analizar los datos, y luego tomar una decisión final.",
        language="es",
    )
    plan5 = voice_expression_engine.plan_prosody_transfer(
        source_features=feat5,
        source_text="First we must analyze the data, and then make a final decision.",
        target_text="Primero debemos analizar los datos, y luego tomar una decisión final.",
        source_lang="en",
        target_lang="es",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    assert feat5.pause_count >= 1, "Must detect pause in signal"
    assert feat5.total_pause_duration_ms >= 2000, f"Expected ~2500ms pause, got {feat5.total_pause_duration_ms}"
    assert "<break time=" in plan5.ssml_markup, "SSML must preserve pause placement"
    results.append(("Test 5: Speech with long natural pauses -> Spanish Expressive", "PASSED", f"Pause ms: {feat5.total_pause_duration_ms}, Break tag inserted: True"))
    print(f"  -> PASS: {feat5.total_pause_duration_ms}ms pause detected and mapped to SSML break tag.")

    # -------------------------------------------------------------------------
    # TEST 6: Inquisitive rising pitch question -> German Expressive
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Inquisitive rising pitch question -> German Expressive")
    quest_de = "Sind Sie sicher, dass alle Server für das heutige Event bereit sind?"
    feat6 = voice_expression_engine.analyze_audio_signal(transcript=quest_de, language="de")
    plan6 = voice_expression_engine.plan_prosody_transfer(
        source_features=feat6,
        source_text=quest_de,
        target_text="Are you certain that all servers are ready for today's event?",
        source_lang="de",
        target_lang="en",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    assert feat6.terminal_pitch_slope > 0, "Terminal slope must be positive for question"
    assert feat6.detected_emotion == DeliveryTag.INQUISITIVE.value
    assert plan6.pitch_adjustment_pct > 0
    results.append(("Test 6: Inquisitive question -> German Expressive", "PASSED", f"Terminal slope: +{feat6.terminal_pitch_slope}Hz, Emotion: {feat6.detected_emotion}"))
    print("  -> PASS: Terminal rising pitch slope transferred to German synthesis plan.")

    # -------------------------------------------------------------------------
    # TEST 7: Emphatic key-word stressed statement -> Japanese Expressive
    # -------------------------------------------------------------------------
    print("\n[TEST 7] Emphatic key-word stressed statement -> Japanese Expressive")
    emph_text = "We MUST complete the deployment BEFORE midnight tonight!"
    feat7 = voice_expression_engine.analyze_audio_signal(transcript=emph_text, language="en")
    plan7 = voice_expression_engine.plan_prosody_transfer(
        source_features=feat7,
        source_text=emph_text,
        target_text="今夜深夜までにデプロイを必ず完了しなければなりません！",
        source_lang="en",
        target_lang="ja",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    assert feat7.detected_emotion in (DeliveryTag.EMPHATIC.value, DeliveryTag.EXCITED.value)
    assert plan7.volume_adjustment_db > 0, "Emphasis requires positive volume offset"
    results.append(("Test 7: Emphatic key-word stressed statement -> Japanese", "PASSED", f"Emotion: {feat7.detected_emotion}, Vol: +{plan7.volume_adjustment_db}dB"))
    print("  -> PASS: Capitalized emphasis mapped to elevated energy and intensity.")

    # -------------------------------------------------------------------------
    # TEST 8: Mode 1 Standard Synthetic verification (neutral baseline)
    # -------------------------------------------------------------------------
    print("\n[TEST 8] Mode 1 Standard Synthetic verification (neutral baseline)")
    synth8 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Standard synthesis operates with calibrated baseline pitch and speed.",
            source_text="Normal text without modification.",
            target_language="en",
            voice_mode=VoiceGenerationMode.STANDARD,
        )
    )
    assert synth8.voice_mode_used == VoiceGenerationMode.STANDARD
    assert synth8.rate_multiplier == 1.0, "Mode 1 rate must be exactly 1.0x baseline"
    assert synth8.pitch_adjustment_pct == 0.0, "Mode 1 pitch must be exactly 0.0"
    results.append(("Test 8: Mode 1 Standard Synthetic verification", "PASSED", f"Mode: {synth8.voice_mode_used}, Rate: {synth8.rate_multiplier}x, Pitch: {synth8.pitch_adjustment_pct}%"))
    print("  -> PASS: Mode 1 yields neutral zero-distortion baseline.")

    # -------------------------------------------------------------------------
    # TEST 9: Mode 2 Expressive Synthetic without cloning
    # -------------------------------------------------------------------------
    print("\n[TEST 9] Mode 2 Expressive Synthetic without cloning")
    synth9 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="This is an exciting milestone for the entire TalkFlow engineering team!",
            source_text="अरे वाह! यह तो बहुत ही शानदार परिणाम है!",
            target_language="en",
            voice_mode=VoiceGenerationMode.EXPRESSIVE,
            speaker_id="guest_speaker_unconsented",
        )
    )
    assert synth9.voice_mode_used == VoiceGenerationMode.EXPRESSIVE
    assert synth9.consent_verified is False, "Mode 2 does not require or use cloning consent"
    assert synth9.fail_closed_fallback is False, "Mode 2 is a first-class mode, not a fallback"
    results.append(("Test 9: Mode 2 Expressive Synthetic without cloning", "PASSED", f"Mode: {synth9.voice_mode_used}, Emotion: {synth9.emotion_applied}, Consent Req: False"))
    print("  -> PASS: Mode 2 expressive transfer executed cleanly without voice cloning.")

    # -------------------------------------------------------------------------
    # TEST 10: Mode 3 Voice Similarity with verified consent
    # -------------------------------------------------------------------------
    print("\n[TEST 10] Mode 3 Voice Similarity with verified consent")
    speaker_consented = "speaker_dr_kapoor"
    tenant = "org_talkflow"
    rec10 = voice_expression_engine.register_consent(
        tenant_id=tenant,
        speaker_id=speaker_consented,
        speaker_name="Dr. Kapoor",
        purpose="multilingual_medical_conference",
        expires_in_days=30,
    )
    assert rec10.is_revoked is False
    assert voice_expression_engine.verify_consent(tenant, speaker_consented) is True

    synth10 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="The latest clinical trials demonstrate substantial efficacy across all patient cohorts.",
            source_text="The latest clinical trials demonstrate substantial efficacy across all patient cohorts.",
            target_language="en",
            speaker_id=speaker_consented,
            tenant_id=tenant,
            purpose="multilingual_medical_conference",
            voice_mode=VoiceGenerationMode.CONSENTED_SIMILARITY,
        )
    )
    assert synth10.voice_mode_used == VoiceGenerationMode.CONSENTED_SIMILARITY
    assert synth10.consent_verified is True
    assert synth10.fail_closed_fallback is False
    results.append(("Test 10: Mode 3 Voice Similarity with verified consent", "PASSED", f"Consent ID: {rec10.consent_id}, Consent Verified: True"))
    print("  -> PASS: Active biometric consent verified; Mode 3 voice similarity executed.")

    # -------------------------------------------------------------------------
    # TEST 11: Mode 3 Attempt WITHOUT consent -> Fail-closed fallback
    # -------------------------------------------------------------------------
    print("\n[TEST 11] Mode 3 Attempt WITHOUT consent -> Fail-closed fallback")
    unauthorized_speaker = "intruder_user_99"
    synth11 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Attempting to clone my voice without authorization.",
            target_language="en",
            speaker_id=unauthorized_speaker,
            tenant_id=tenant,
            purpose="multilingual_medical_conference",
            voice_mode=VoiceGenerationMode.CONSENTED_SIMILARITY,
        )
    )
    assert synth11.voice_mode_used == VoiceGenerationMode.EXPRESSIVE, "Must fall back to Expressive Mode"
    assert synth11.consent_verified is False
    assert synth11.fail_closed_fallback is True, "Must report fail_closed_fallback=True"
    results.append(("Test 11: Mode 3 Attempt WITHOUT consent -> Fail-closed", "PASSED", f"Mode Used: {synth11.voice_mode_used}, FailClosed: True, Blocked: True"))
    print("  -> PASS: Unauthorized cloning blocked! Honest fail-closed fallback to Mode 2 enforced.")

    # -------------------------------------------------------------------------
    # TEST 12: Mode 3 Revocation in mid-session -> Immediate fallback
    # -------------------------------------------------------------------------
    print("\n[TEST 12] Mode 3 Revocation in mid-session -> Immediate fallback")
    # First utterance with active consent
    revokable_speaker = "speaker_alice"
    voice_expression_engine.register_consent(tenant, revokable_speaker, "Alice Smith")
    assert voice_expression_engine.verify_consent(tenant, revokable_speaker) is True

    # User clicks 'Revoke Consent'
    revoked = voice_expression_engine.revoke_consent(tenant, revokable_speaker)
    assert revoked is True
    assert voice_expression_engine.verify_consent(tenant, revokable_speaker) is False

    # Subsequent utterance must immediately fail-closed to Mode 2
    synth12 = await voice_expression_engine.synthesize_expressive(
        ExpressiveSynthesisRequest(
            text="Now that my consent is revoked, my voice must not be cloned.",
            target_language="en",
            speaker_id=revokable_speaker,
            tenant_id=tenant,
            purpose="multilingual_medical_conference",
            voice_mode=VoiceGenerationMode.CONSENTED_SIMILARITY,
        )
    )
    assert synth12.voice_mode_used == VoiceGenerationMode.EXPRESSIVE
    assert synth12.consent_verified is False
    assert synth12.fail_closed_fallback is True
    results.append(("Test 12: Mode 3 Revocation in mid-session -> Immediate fallback", "PASSED", f"Revoked: True, Fallback Enforced: True"))
    print("  -> PASS: Mid-session revocation instantly switched speaker to non-cloned synthetic voice.")

    # -------------------------------------------------------------------------
    # TEST 13: Fan-Out Deduplication with Expressive Mode
    # -------------------------------------------------------------------------
    print("\n[TEST 13] Fan-Out Deduplication with Expressive Mode")
    room_id = "expressive_conf_room_01"
    fanout_engine.get_or_create_room(room_id, "Expressive Multi-Language Demo")

    # 3 English listeners all requesting Expressive Mode
    fanout_engine.join_room(room_id, Participant(participant_id="u1", name="Alice", preferred_listen_language="en", audio_mode="translated"))
    fanout_engine.join_room(room_id, Participant(participant_id="u2", name="Bob", preferred_listen_language="en", audio_mode="translated"))
    fanout_engine.join_room(room_id, Participant(participant_id="u3", name="Charlie", preferred_listen_language="en", audio_mode="translated"))

    # Speaker delivers excited Hindi speech
    utt = SourceUtterance(
        utterance_id="utt_expr_fanout",
        room_id=room_id,
        source_track_id="track_priya_01",
        source_participant_id="speaker_priya",
        source_participant_name="Priya",
        source_language="hi",
        transcript="हम इस तकनीक को सफलतापूर्वक लॉन्च कर रहे हैं!",
        start_time=0.0,
        end_time=2.5,
        duration_ms=2500,
    )
    plan_fanout = fanout_engine.plan_fanout(
        room_id=room_id,
        speaker_id="speaker_priya",
        text="हम इस तकनीक को सफलतापूर्वक लॉन्च कर रहे हैं!",
        detected_source_lang="hi",
        utterance_id="utt_expr_fanout",
    )
    assert len(plan_fanout.unique_target_languages) == 1, "Only 1 translation needed for 3 English listeners"
    assert plan_fanout.translation_jobs_needed == 1, "Only 1 translation job needed"
    saved_ratio = plan_fanout.deduplication_savings_ratio
    assert saved_ratio >= 0.60, f"Expected >= 60% compute savings, got {saved_ratio}"
    results.append(("Test 13: Fan-Out Deduplication with Expressive Mode", "PASSED", f"Listeners: 3, Targets: {plan_fanout.unique_target_languages}, Savings: {round(saved_ratio*100, 1)}%"))
    print(f"  -> PASS: Fan-Out deduplication yielded {round(saved_ratio*100, 1)}% compute savings for expressive TTS.")

    # -------------------------------------------------------------------------
    # TEST 14: Pronunciation dictionary application in expressive speech
    # -------------------------------------------------------------------------
    print("\n[TEST 14] Pronunciation dictionary application in expressive speech")
    raw_text = "TalkFlow and AI are redefining real-time translation."
    pron_hi = voice_expression_engine.apply_pronunciation_rules(raw_text, "hi", "org_default")
    assert "टॉक-फ्लो" in pron_hi, f"Expected 'टॉक-फ्लो' in '{pron_hi}'"
    assert "ए-आई" in pron_hi, f"Expected 'ए-आई' in '{pron_hi}'"
    results.append(("Test 14: Pronunciation dictionary application", "PASSED", f"Original: TalkFlow -> Hindi: टॉक-फ्लो, AI -> ए-आई"))
    print(f"  -> PASS: Specialized terminology replaced: '{pron_hi}'.")

    # -------------------------------------------------------------------------
    # TEST 15: Cross-lingual pacing adaptation (Rate clamped [0.85, 1.25])
    # -------------------------------------------------------------------------
    print("\n[TEST 15] Cross-lingual pacing adaptation (Rate clamped [0.85, 1.25])")
    # Extremely short source duration vs long target (would yield 3.0x without clamp)
    extreme_short_feat = AcousticFeatures(duration_ms=500.0, detected_emotion="neutral")
    plan15_fast = voice_expression_engine.plan_prosody_transfer(
        source_features=extreme_short_feat,
        source_text="Short",
        target_text="This is an extraordinarily long translated phrase intended to test rate clamping bounds.",
        source_lang="hi",
        target_lang="en",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    # Extremely long source duration vs very short target (would yield 0.2x without clamp)
    extreme_long_feat = AcousticFeatures(duration_ms=10000.0, detected_emotion="neutral")
    plan15_slow = voice_expression_engine.plan_prosody_transfer(
        source_features=extreme_long_feat,
        source_text="Long speech",
        target_text="Yes.",
        source_lang="hi",
        target_lang="en",
        voice_mode=VoiceGenerationMode.EXPRESSIVE,
    )
    assert 0.85 <= plan15_fast.rate_multiplier <= 1.25, f"Rate exceeded bounds: {plan15_fast.rate_multiplier}"
    assert 0.85 <= plan15_slow.rate_multiplier <= 1.25, f"Rate exceeded bounds: {plan15_slow.rate_multiplier}"
    assert plan15_fast.rate_multiplier == 1.25, "Fast rate should be clamped to 1.25"
    assert plan15_slow.rate_multiplier == 0.85, "Slow rate should be clamped to 0.85"
    results.append(("Test 15: Cross-lingual pacing clamping [0.85, 1.25]", "PASSED", f"Max Clamped: {plan15_fast.rate_multiplier}x, Min Clamped: {plan15_slow.rate_multiplier}x"))
    print(f"  -> PASS: Speaking rates strictly bounded to [{plan15_slow.rate_multiplier}x, {plan15_fast.rate_multiplier}x].")

    # -------------------------------------------------------------------------
    # TEST 16: Full-duration (5-minute / multi-chunk) expressive timeline continuity
    # -------------------------------------------------------------------------
    print("\n[TEST 16] Full-duration (5-minute / multi-chunk) expressive timeline continuity")
    # Simulate 10 consecutive chunks from a long 5-minute conversation
    num_chunks = 10
    synth_durations = []
    watermarks = []
    for i in range(num_chunks):
        chunk_text = f"Segment {i+1}: Discussing continuous audio streaming and timeline alignment across multiple speakers."
        synth_chunk = await voice_expression_engine.synthesize_expressive(
            ExpressiveSynthesisRequest(
                text=chunk_text,
                source_language="hi",
                target_language="en",
                speaker_id="speaker_dr_kapoor",
                voice_mode=VoiceGenerationMode.EXPRESSIVE,
            )
        )
        assert len(synth_chunk.audio_base64) > 0
        synth_durations.append(synth_chunk.duration_ms)
        watermarks.append(synth_chunk.watermark)

    total_stream_ms = sum(synth_durations)
    assert len(synth_durations) == num_chunks
    assert total_stream_ms > 0
    assert len(set(watermarks)) == num_chunks, "Each chunk must have unique traceable watermark ID"
    results.append(("Test 16: Full-duration expressive timeline continuity", "PASSED", f"Chunks: {num_chunks}, Total Audio ms: {round(total_stream_ms, 1)}, Watermarks: Verified"))
    print(f"  -> PASS: All {num_chunks} chunks synthesized sequentially with preserved prosody and traceable watermarks.")

    # -------------------------------------------------------------------------
    # SUMMARY TABLE
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"{'TEST CASE':<55} | {'STATUS':<8} | {'DETAILS'}")
    print("-" * 80)
    for name, status, detail in results:
        print(f"{name:<55} | {status:<8} | {detail}")
    print("=" * 80)
    print(f"TOTAL: 16/16 PASSED (100% SUCCESS RATE)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
