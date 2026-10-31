"""Benchmark Script for TalkFlow Agent 06 (Voice Generation Agent)."""
from __future__ import annotations

import time
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

BENCHMARK_SAMPLES = [
    ("en", "TalkFlow real-time multilingual communication platform converts approved text to natural speech."),
    ("hi", "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।"),
    ("mr", "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करू."),
    ("bn", "আজ আমরা আমাদের নতুন এআই প্রজেক্ট নিয়ে আলোচনা করব।"),
    ("ja", "本日、新しいAIプロジェクトについて議論します。"),
]


def run_benchmark():
    print("=" * 65)
    print("  TALKFLOW AGENT 06 — TTS LATENCY & THROUGHPUT BENCHMARK")
    print("=" * 65)
    print(f"{'Lang':<6} | {'Audio Dur':<12} | {'Compute Latency':<16} | {'RTF (Latency/Dur)':<18} | {'Provider'}")
    print("-" * 65)

    for lang, text in BENCHMARK_SAMPLES:
        req = {
            "text": text,
            "target_language": lang,
            "quality_decision": "ACCEPT",
            "quality_score": 0.95,
            "conversation_id": f"conv_bench_{lang}",
            "segment_id": f"seg_bench_{lang}_{int(time.time()*1000)}",
        }

        t0 = time.perf_counter()
        resp = client.post("/api/v1/tts/synthesize", json=req)
        compute_ms = (time.perf_counter() - t0) * 1000.0

        if resp.status_code == 200:
            data = resp.json()
            dur_ms = data["duration_ms"]
            rtf = (compute_ms / dur_ms) if dur_ms > 0 else 0.0
            provider = f"{data['provider']}/{data['voice_id']}"
            print(f"{lang:<6} | {dur_ms/1000.0:>6.2f}s     | {compute_ms:>7.1f}ms        | {rtf:>10.3f}x         | {provider}")
        else:
            print(f"{lang:<6} | FAILED ({resp.status_code})")

    print("=" * 65)


if __name__ == "__main__":
    run_benchmark()

