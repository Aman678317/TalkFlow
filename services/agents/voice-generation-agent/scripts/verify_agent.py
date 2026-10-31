"""Standalone Verification Script for TalkFlow Agent 06 (Voice Generation Agent)."""
from __future__ import annotations

import base64
import sys
import time
from fastapi.testclient import TestClient

from app.audio.binary_framing import decode_binary_tts_frame
from app.main import app

client = TestClient(app)


def run_verification():
    print("=" * 65)
    print("  TALKFLOW AGENT 06 — VOICE GENERATION AGENT (TTS) VERIFICATION")
    print("=" * 65)

    passes = 0
    total = 0

    # 1. Health check
    total += 1
    resp = client.get("/api/v1/tts/health")
    if resp.status_code == 200 and resp.json().get("status") == "healthy":
        print("[PASS] 1. Health check returned 200 OK & healthy.")
        passes += 1
    else:
        print(f"[FAIL] 1. Health check failed: {resp.status_code} {resp.text}")

    # 2. Voice registry enumeration
    total += 1
    resp = client.get("/api/v1/tts/voices")
    data = resp.json()
    if resp.status_code == 200 and data.get("count", 0) > 0:
        voices = data.get("voices", [])
        print(f"[PASS] 2. Voice registry populated ({len(voices)} voice profiles loaded).")
        passes += 1
    else:
        print(f"[FAIL] 2. Voice registry check failed: {resp.text}")

    # 3. Quality Gate Enforcement (REJECT must be blocked with HTTP 422)
    total += 1
    bad_req = {
        "text": "Unapproved text that must never be synthesized.",
        "target_language": "en",
        "quality_decision": "REJECT",
        "quality_score": 0.20,
        "conversation_id": "conv_verify_01",
        "segment_id": "seg_verify_01",
    }
    resp = client.post("/api/v1/tts/synthesize", json=bad_req)
    if resp.status_code == 422:
        print("[PASS] 3. Quality gate strictly blocked REJECT decision (HTTP 422).")
        passes += 1
    else:
        print(f"[FAIL] 3. Quality gate failed to block rejected translation: {resp.status_code}")

    # 4. Cross-Language Voice Substitution Prohibition
    total += 1
    mismatch_req = {
        "text": "आज हम चर्चा करेंगे",
        "target_language": "hi",
        "requested_voice_id": "system-david",  # English voice requested for Hindi
        "quality_decision": "ACCEPT",
        "quality_score": 0.95,
        "conversation_id": "conv_verify_02",
        "segment_id": "seg_verify_02",
    }
    resp = client.post("/api/v1/tts/synthesize", json=mismatch_req)
    if resp.status_code == 400 and "cross-language" in resp.text.lower():
        print("[PASS] 4. Cross-language silent substitution prohibited (HTTP 400).")
        passes += 1
    else:
        print(f"[FAIL] 4. Failed to prohibit cross-language substitution: {resp.status_code} {resp.text}")

    # 5. Synthesis: English (en)
    total += 1
    en_req = {
        "text": "Welcome to TalkFlow real-time multilingual communication platform.",
        "target_language": "en",
        "quality_decision": "ACCEPT",
        "quality_score": 0.95,
        "conversation_id": "conv_verify_en",
        "segment_id": "seg_verify_en",
    }
    t0 = time.perf_counter()
    resp = client.post("/api/v1/tts/synthesize", json=en_req)
    en_lat = (time.perf_counter() - t0) * 1000.0
    if resp.status_code == 200:
        d = resp.json()
        assert d["synthetic"] is True
        print(f"[PASS] 5. Synthesized English audio ({d['duration_ms']:.0f}ms audio, latency={en_lat:.1f}ms, provider={d['provider']}).")
        passes += 1
    else:
        print(f"[FAIL] 5. English synthesis failed: {resp.status_code} {resp.text}")

    # 6. Synthesis: Hindi (hi)
    total += 1
    hi_req = {
        "text": "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।",
        "target_language": "hi",
        "quality_decision": "ACCEPT",
        "quality_score": 0.94,
        "conversation_id": "conv_verify_hi",
        "segment_id": "seg_verify_hi",
    }
    t0 = time.perf_counter()
    resp = client.post("/api/v1/tts/synthesize", json=hi_req)
    hi_lat = (time.perf_counter() - t0) * 1000.0
    if resp.status_code == 200:
        d = resp.json()
        assert d["synthetic"] is True
        print(f"[PASS] 6. Synthesized Hindi audio ({d['duration_ms']:.0f}ms audio, latency={hi_lat:.1f}ms, provider={d['provider']}).")
        passes += 1
    else:
        print(f"[FAIL] 6. Hindi synthesis failed: {resp.status_code} {resp.text}")

    # 7. Synthesis: Marathi (mr) via Agent 05 Inbound Webhook
    total += 1
    mr_webhook = {
        "evaluation_id": "eval_verify_mr_01",
        "candidate_hash": "cand_hash_mr_01",
        "session_id": "sess_mr_call",
        "conversation_id": "conv_mr_call",
        "segment_id": "seg_mr_verify_01",
        "translation_id": "trans_mr_verify_01",
        "source_lang": "hi",
        "target_lang": "mr",
        "source_text": "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।",
        "target_text": "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करू.",
        "decision": "ACCEPT",
        "overall_score": 0.95,
        "is_safe_for_voice": True,
    }
    t0 = time.perf_counter()
    resp = client.post("/api/v1/tts/segment", json=mr_webhook)
    mr_lat = (time.perf_counter() - t0) * 1000.0
    if resp.status_code == 200:
        d = resp.json()
        assert d["synthetic"] is True
        print(f"[PASS] 7. Agent 05 Marathi webhook handoff succeeded ({d['duration_ms']:.0f}ms audio, latency={mr_lat:.1f}ms, provider={d['provider']}).")
        passes += 1
    else:
        print(f"[FAIL] 7. Marathi webhook handoff failed: {resp.status_code} {resp.text}")

    # 8. TalkFlow Binary Wire Frame Verification (0x54 magic prefix)
    total += 1
    from app.audio.binary_framing import build_binary_tts_frame
    pcm_test = b"\x10\x20\x30\x40\x50\x60\x70\x80"
    frame = build_binary_tts_frame("seg_1234567890abcdef", "hi", chunk_index=1, audio_pcm_bytes=pcm_test)
    decoded = decode_binary_tts_frame(frame)
    if frame[0] == 0x54 and decoded["pcm"] == pcm_test and decoded["chunk_index"] == 1:
        print("[PASS] 8. TalkFlow binary wire framing validated (0x54 magic byte, uint32 chunk index).")
        passes += 1
    else:
        print("[FAIL] 8. Binary wire framing mismatch.")

    # 9. Barge-in / Cancellation
    total += 1
    cancel_req = {"session_id": "sess_mr_call", "segment_id": "seg_mr_verify_01", "reason": "barge_in_interruption"}
    resp = client.post("/api/v1/tts/cancel", json=cancel_req)
    if resp.status_code == 200 and resp.json().get("cancelled") is True:
        print("[PASS] 9. Barge-in cancellation acknowledged and verified.")
        passes += 1
    else:
        print(f"[FAIL] 9. Cancellation failed: {resp.text}")

    # 10. Telemetry & Metrics
    total += 1
    resp = client.get("/metrics")
    if resp.status_code == 200 and "talkflow_tts_requests_total" in resp.text:
        print("[PASS] 10. Prometheus metrics endpoint validated (/metrics).")
        passes += 1
    else:
        print(f"[FAIL] 10. Metrics endpoint failed: {resp.text}")

    print("-" * 65)
    print(f"VERIFICATION SUMMARY: {passes}/{total} TESTS PASSED.")
    print("=" * 65)

    if passes == total:
        print("ALL VERIFICATION CHECKS PASSED SUCCESSFULLY.")
        return 0
    else:
        print("SOME CHECKS FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(run_verification())

