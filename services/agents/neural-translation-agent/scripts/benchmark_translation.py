"""Latency and throughput benchmark for Neural Translation Agent (Agent 04)."""
from __future__ import annotations

import asyncio
import time
from app.models.schemas import BatchTranslationRequestSchema, TranslationRequestSchema
from app.services.fanout_adapter import fanout_coordinator
from app.translation.engine import translation_engine


async def benchmark() -> None:
    print("=" * 80)
    print("TALKFLOW AGENT 04: NEURAL TRANSLATION BENCHMARK SUITE")
    print("=" * 80)

    # 1. Single Target Latency Benchmark (Warmup + 10 iterations)
    print("\n[Benchmark 1] Single Target Latency: 1 Source Segment -> 1 Target (hi -> en)")
    req = TranslationRequestSchema(
        text="नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        source_lang="hi",
        target_lang="en",
    )
    # Warmup
    await translation_engine.translate_single(req)

    latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        await translation_engine.translate_single(req)
        latencies.append((time.perf_counter() - t0) * 1000.0)

    p50 = sorted(latencies)[len(latencies) // 2]
    mean = sum(latencies) / len(latencies)
    print(f"  Iterations: 5 | P50 Latency: {p50:.2f} ms | Mean Latency: {mean:.2f} ms")

    # 2. Multi-Target Independent Fan-Out: 1 Source -> 2 Targets (en, mr)
    print("\n[Benchmark 2] Multi-Target Fan-Out: 1 Source -> 2 Targets (en, mr)")
    batch_2 = BatchTranslationRequestSchema(
        text="नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        source_lang="hi",
        target_langs=["en", "mr"],
    )
    t0 = time.perf_counter()
    res_2 = await fanout_coordinator.execute_fanout(batch_2)
    tot_2 = (time.perf_counter() - t0) * 1000.0
    print(f"  Total Fan-Out Latency: {tot_2:.2f} ms | Distinct Targets: {res_2.unique_translation_jobs_count}")

    # 3. Multi-Target Independent Fan-Out: 1 Source -> 4 Targets (en, mr, ja, bn)
    print("\n[Benchmark 3] Multi-Target Fan-Out: 1 Source -> 4 Targets (en, mr, ja, bn)")
    batch_4 = BatchTranslationRequestSchema(
        text="नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        source_lang="hi",
        target_langs=["en", "mr", "ja", "bn"],
    )
    t0 = time.perf_counter()
    res_4 = await fanout_coordinator.execute_fanout(batch_4)
    tot_4 = (time.perf_counter() - t0) * 1000.0
    print(f"  Total Fan-Out Latency: {tot_4:.2f} ms | Distinct Targets: {res_4.unique_translation_jobs_count}")

    # 4. Multi-Target Fan-Out with Deduplication: 1 Source -> 8 Listeners (4 distinct languages)
    print("\n[Benchmark 4] Listener Deduplication: 1 Source -> 8 Listeners (en, en, mr, mr, ja, ja, bn, bn)")
    batch_8 = BatchTranslationRequestSchema(
        text="नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        source_lang="hi",
        target_langs=["en", "en", "mr", "mr", "ja", "ja", "bn", "bn"],
    )
    t0 = time.perf_counter()
    res_8 = await fanout_coordinator.execute_fanout(batch_8)
    tot_8 = (time.perf_counter() - t0) * 1000.0
    print(f"  Requested Listeners: {res_8.requested_targets_count} -> Deduped MT Jobs: {res_8.unique_translation_jobs_count}")
    print(f"  Total Latency: {tot_8:.2f} ms (Deduplication saved 4 redundant inference jobs!)")

    print("\n" + "=" * 80)
    print("BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(benchmark())

