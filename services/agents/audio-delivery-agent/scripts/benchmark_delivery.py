"""Performance and latency benchmark for Agent 07 Audio Delivery Agent."""
from __future__ import annotations

import base64
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

BASE_URL = "http://127.0.0.1:8007"
NUM_CHUNKS = 100


def benchmark_delivery():
    print(f"Benchmarking Agent 07 Delivery with {NUM_CHUNKS} consecutive audio chunks...")

    # Register participants
    room_id = "bench_room"
    with httpx.Client(timeout=10.0) as client:
        client.post(
            f"{BASE_URL}/api/v1/rooms/participants",
            json={
                "participant_id": "bench_listener_1",
                "room_id": room_id,
                "hear_lang": "mr",
                "playback_mode": "translated",
            },
        )
        client.post(
            f"{BASE_URL}/api/v1/rooms/participants",
            json={
                "participant_id": "bench_listener_2",
                "room_id": room_id,
                "hear_lang": "mr",
                "playback_mode": "translated",
            },
        )

        dummy_audio = base64.b64encode(b"\x00\x02" * 2400).decode()
        latencies = []

        start_total = time.time()
        for i in range(NUM_CHUNKS):
            payload = {
                "session_id": room_id,
                "conversation_id": room_id,
                "speaker_id": "speaker_test",
                "segment_id": "seg_bench",
                "target_lang": "mr",
                "chunk_index": i,
                "is_final_chunk": (i == NUM_CHUNKS - 1),
                "duration_ms": 100.0,
                "audio_base64": dummy_audio,
                "synthetic": True,
                "audio_origin": "synthetic_tts",
            }
            t0 = time.time()
            resp = client.post(f"{BASE_URL}/api/v1/delivery/chunks", json=payload)
            t_ms = (time.time() - t0) * 1000.0
            assert resp.status_code == 200
            latencies.append(t_ms)

        total_elapsed = time.time() - start_total
        avg_ms = sum(latencies) / len(latencies)
        p95_ms = sorted(latencies)[int(len(latencies) * 0.95)]
        throughput = NUM_CHUNKS / total_elapsed

        print("\n=======================================================")
        print(" BENCHMARK RESULTS")
        print("=======================================================")
        print(f" Total Chunks Ingested: {NUM_CHUNKS}")
        print(f" Total Time:            {total_elapsed:.2f}s")
        print(f" Average Latency:       {avg_ms:.2f} ms")
        print(f" 95th Percentile (P95): {p95_ms:.2f} ms")
        print(f" Throughput:            {throughput:.1f} chunks/sec")
        print("=======================================================")


if __name__ == "__main__":
    benchmark_delivery()

