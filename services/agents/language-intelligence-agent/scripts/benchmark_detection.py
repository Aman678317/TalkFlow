"""Performance and Latency Benchmark for Language Intelligence Agent."""
import os
import sys
import time
import statistics

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.detection.engine import LanguageIntelligenceEngine


def benchmark():
    engine = LanguageIntelligenceEngine()
    sentences = [
        "Welcome to our meeting today.",
        "Hello everyone, aaj hum artificial intelligence ke baare mein discuss karenge.",
        "नमस्ते दोस्तों, आज हम एआई के बारे में बात करेंगे।",
        "नमस्कार मित्रांनो, आज आपण काय करणार आहोत?",
        "Bonjour tout le monde, comment allez-vous?",
        "Good morning, let us start the presentation.",
    ]

    print("=" * 80)
    print("TALKFLOW AGENT 03 PERFORMANCE & LATENCY BENCHMARK")
    print("=" * 80)

    # Warmup
    for s in sentences:
        engine.analyze_text(s)

    latencies_ms = []
    iterations = 200

    print(f"Executing {iterations} iterations across diverse multilingual utterances...")
    t_start = time.perf_counter()

    for i in range(iterations):
        s = sentences[i % len(sentences)]
        t0 = time.perf_counter()
        engine.analyze_text(s)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    total_time = time.perf_counter() - t_start
    throughput = iterations / total_time

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
    avg = statistics.mean(latencies_ms)

    print(f"\nThroughput : {throughput:.1f} requests/second")
    print(f"Average    : {avg:.2f} ms")
    print(f"P50 Median : {p50:.2f} ms")
    print(f"P95        : {p95:.2f} ms")
    print(f"P99        : {p99:.2f} ms")
    print("=" * 80)
    assert p95 < 10.0, "P95 latency exceeded budget!"


if __name__ == "__main__":
    benchmark()

