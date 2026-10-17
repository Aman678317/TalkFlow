#!/usr/bin/env python3
"""Offline benchmark for the realtime translation fan-out.

The workload models one finalized utterance sent to several distinct target
languages.  Each provider call has a fixed delay, so the benchmark isolates the
fan-out scheduler rather than depending on network services or model weights.

Run from the repository root::

    python scripts/benchmark_translation_fanout.py

The serial control is the pre-optimization orchestration.  The concurrent run
calls the production ``TranslationAgent.fan_out`` implementation.  Both use the
same provider, data, result validation, and repetitions.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.realtime.agents.bus import AgentBus  # noqa: E402
from app.realtime.agents.contracts import TranscriptSegment, TranslationSegment  # noqa: E402
from app.realtime.agents.translation import (  # noqa: E402
    ProviderTranslation,
    TranslationAgent,
)


DEFAULT_LANGUAGES = ("en", "ur", "mr", "ta", "bn", "ja", "de", "fr")


class DelayedTranslator:
    """Deterministic async provider used by the benchmark only."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: tuple[str, ...] = (),
        *,
        segment_id: str | None = None,
        speaker_id: str | None = None,
    ) -> ProviderTranslation:
        self.calls.append(target_lang)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay_seconds)
            return ProviderTranslation(
                text=f"[{target_lang}] {text}",
                provider="benchmark",
                model="benchmark",
            )
        finally:
            self.active -= 1


def _segment() -> TranscriptSegment:
    return TranscriptSegment(
        correlation_id="benchmark-utterance",
        meeting_id="benchmark-meeting",
        speaker_id="benchmark-speaker",
        segment_id="benchmark-segment",
        sequence_number=1,
        source_language="hi",
        recognized_text="नमस्ते, आज हम योजना पर चर्चा करेंगे।",
        is_final=True,
    )


def _recipients(languages: tuple[str, ...]) -> dict[str, list[str]]:
    return {language: [f"listener-{language}"] for language in languages}


async def _serial_reference(
    agent: TranslationAgent,
    segment: TranscriptSegment,
    recipients_by_lang: dict[str, list[str]],
) -> list[TranslationSegment]:
    """Run the pre-optimization serial orchestration as a benchmark control."""
    languages = sorted({
        language
        for language, recipients in recipients_by_lang.items()
        if recipients and language != segment.source_language
    })
    prior_context = agent.context_for(segment.speaker_id)
    produced: list[TranslationSegment] = []
    for language in languages:
        recipients = list(recipients_by_lang[language])
        one = await agent.translate_one(
            segment, language, recipients, prior_context=prior_context
        )
        produced.extend(
            one.model_copy(update={"recipient_id": recipient})
            for recipient in (recipients or [""])
        )
    if languages:
        agent.note_source(segment.speaker_id, segment.recognized_text.strip())
    return produced


async def _measure_once(
    strategy: str,
    languages: tuple[str, ...],
    delay_seconds: float,
) -> tuple[float, int, int, int]:
    provider = DelayedTranslator(delay_seconds)
    agent = TranslationAgent(AgentBus(), provider, meeting_id="benchmark-meeting")
    segment = _segment()
    recipients = _recipients(languages)
    start = time.perf_counter()
    if strategy == "serial":
        output = await _serial_reference(agent, segment, recipients)
    else:
        output = await agent.fan_out(segment, recipients_by_lang=recipients)
    elapsed_ms = (time.perf_counter() - start) * 1000
    expected = len(languages)
    if len(provider.calls) != expected or len(output) != expected:
        raise AssertionError(
            f"unexpected fan-out result: calls={len(provider.calls)} "
            f"output={len(output)} expected={expected}"
        )
    return elapsed_ms, len(provider.calls), len(output), provider.max_active


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, int(len(ordered) * percentile))
    return ordered[index]


async def _run(args: argparse.Namespace) -> None:
    languages = tuple(dict.fromkeys(
        language.strip().lower()
        for language in args.languages.split(",")
        if language.strip()
    ))
    if not languages:
        raise SystemExit("--languages must contain at least one language")

    for _ in range(args.warmups):
        await _measure_once("serial", languages, args.delay_ms / 1000)
        await _measure_once("concurrent", languages, args.delay_ms / 1000)

    measurements: dict[str, list[tuple[float, int]]] = {"serial": [], "concurrent": []}
    for _ in range(args.iterations):
        for strategy in measurements:
            elapsed_ms, _calls, _output, max_active = await _measure_once(
                strategy, languages, args.delay_ms / 1000
            )
            measurements[strategy].append((elapsed_ms, max_active))

    serial_samples = [elapsed for elapsed, _ in measurements["serial"]]
    concurrent_samples = [elapsed for elapsed, _ in measurements["concurrent"]]
    serial_median = statistics.median(serial_samples)
    concurrent_median = statistics.median(concurrent_samples)
    speedup = serial_median / concurrent_median
    improvement = (serial_median - concurrent_median) / serial_median * 100

    print(f"workload: {len(languages)} target languages, {args.delay_ms:g}ms/provider call")
    print(f"languages: {','.join(languages)}")
    print(f"iterations: {args.iterations} (+ {args.warmups} warmup)")
    print(f"serial_samples_ms: {','.join(f'{sample:.1f}' for sample in serial_samples)}")
    print(f"concurrent_samples_ms: {','.join(f'{sample:.1f}' for sample in concurrent_samples)}")
    print(f"serial_median_ms: {serial_median:.1f}")
    print(f"concurrent_median_ms: {concurrent_median:.1f}")
    print(f"median_improvement_percent: {improvement:.1f}")
    print(f"median_speedup: {speedup:.2f}x")
    print(f"max_parallel_calls: {max(active for _, active in measurements['concurrent'])}")
    print(f"serial_p95_ms: {_percentile(serial_samples, 0.95):.1f}")
    print(f"concurrent_p95_ms: {_percentile(concurrent_samples, 0.95):.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", default=",".join(DEFAULT_LANGUAGES))
    parser.add_argument("--delay-ms", type=float, default=20.0)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    args = parser.parse_args()
    if args.delay_ms < 0 or args.iterations < 1 or args.warmups < 0:
        parser.error("delay and iteration counts must be non-negative; iterations must be > 0")
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
