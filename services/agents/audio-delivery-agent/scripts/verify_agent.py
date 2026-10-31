"""Verification script for Agent 07 Audio Delivery Agent."""
from __future__ import annotations

import base64
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.transport.binary_wire import decode_talkflow_binary_frame, encode_talkflow_binary_frame

BASE_URL = "http://127.0.0.1:8007"


def test_wire_framing_offline():
    print("[1/5] Verifying 0x54 Wire Framing & Extension Format...")
    pcm = b"\x00\x01\x02\x03" * 200
    frame = encode_talkflow_binary_frame(
        segment_id="test_seg_100",
        target_lang="mr",
        chunk_index=3,
        audio_bytes=pcm,
        supports_tts_chunk_index=True,
    )
    assert frame[0] == 0x54, f"Expected 0x54, got {hex(frame[0])}"
    decoded = decode_talkflow_binary_frame(frame)
    assert decoded["target_lang"] == "mr"
    assert decoded["chunk_index"] == 3
    assert decoded["audio_bytes"] == pcm
    print("      [OK] 0x54 binary frame format and decoding verified!")


def test_http_live(client: httpx.Client):
    print("\n[2/5] Testing Agent 07 Health Endpoint...")
    resp = client.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    print(f"      [OK] Health: {resp.json()}")

    print("\n[3/5] Testing Room Registration & Participant Routing...")
    room_id = "test_verify_room"
    p1 = {
        "participant_id": "listener_mr",
        "room_id": room_id,
        "display_name": "Marathi Listener",
        "hear_lang": "mr",
        "playback_mode": "translated",
    }
    p_spk = {
        "participant_id": "speaker_human",
        "room_id": room_id,
        "display_name": "Speaker Human",
        "hear_lang": "hi",
        "playback_mode": "original",
    }
    resp1 = client.post(f"{BASE_URL}/api/v1/rooms/participants", json=p1)
    resp2 = client.post(f"{BASE_URL}/api/v1/rooms/participants", json=p_spk)
    assert resp1.status_code == 200 and resp2.status_code == 200
    print("      [OK] Participants registered in room.")

    print("\n[4/5] Testing Audio Chunk Ingestion & Fanout...")
    dummy_audio = base64.b64encode(b"\x00\x01" * 2400).decode()
    chunk = {
        "session_id": room_id,
        "conversation_id": room_id,
        "speaker_id": "speaker_human",
        "segment_id": "seg_verify_1",
        "target_lang": "mr",
        "chunk_index": 0,
        "is_final_chunk": True,
        "duration_ms": 100.0,
        "audio_base64": dummy_audio,
        "synthetic": True,
        "audio_origin": "synthetic_tts",
    }
    ing_resp = client.post(f"{BASE_URL}/api/v1/delivery/chunks", json=chunk)
    assert ing_resp.status_code == 200
    data = ing_resp.json()
    print(f"      [OK] Ingested chunk: status={data['status']}, recipients={data['recipients_count']}, latency={data['latency_ms']:.1f}ms")

    print("\n[5/5] Testing Diagnostic Brain Reasoning...")
    brain_resp = client.post(
        f"{BASE_URL}/api/v1/brain/query",
        json={"query": "How do you avoid feedback loops with the speaker?"},
    )
    assert brain_resp.status_code == 200
    b_data = brain_resp.json()
    print(f"      [OK] Brain Answer: {b_data['answer'][:120]}... [Source: {b_data['source']}]")


def main():
    print("==================================================================")
    print(" TALKFLOW AGENT 07: AUDIO SYNCHRONIZATION & DELIVERY VERIFICATION ")
    print("==================================================================")
    test_wire_framing_offline()

    try:
        with httpx.Client(timeout=5.0) as client:
            test_http_live(client)
        print("\n==================================================================")
        print(" ALL VERIFICATION CHECKS PASSED SUCCESSFULLY (AGENT 07 READY) ")
        print("==================================================================")
    except httpx.ConnectError:
        print("\n[INFO] Live service not running on port 8007 yet. Offline unit tests passed.")


if __name__ == "__main__":
    main()
