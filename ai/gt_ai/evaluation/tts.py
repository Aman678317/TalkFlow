"""Target-language TTS voice benchmark (Phase 3).

The capability registry is explicit that its quality numbers are "filled by the
evaluation harness, not marketing" — but until now the harness only measured
translation and speech recognition. Speech *output* was promoted or demoted on
the strength of a model card, and nothing in the repo could answer the question
a deployment actually has: of the voices available for Hindi, which one should
the room use?

This measures what a listener experiences, per (language, provider, voice):

* ``first_audio_ms``   — how long after the sentence is known the first bytes
  arrive. This is the number that decides whether translated speech feels like
  a simultaneous feed or like a dub lagging the speaker.
* ``realtime_factor``  — synthesis time divided by the audio it produced. Above
  1.0 the voice cannot keep a meeting live, however pleasant it sounds.
* ``audio_ms`` and peak amplitude — proof the voice said something. A model that
  returns a second of digital silence for a Devanagari sentence is not a
  candidate; it is a failure that looks like a pass.

A voice whose weights are not on the machine is reported as **unavailable by
name**, with the provider's own reason. It is never scored, never rounded down,
and never silently swapped for a voice of another language — a benchmark that
guesses is worse than no benchmark, because its output looks like evidence.

Usage:
    python scripts/bench_tts_voices.py --lang hi
    python scripts/bench_tts_voices.py --lang en,hi,ur --provider piper --out tts.json
    python scripts/bench_tts_voices.py --lang hi --provider piper --voice hi_IN-priyamvada-medium

(`python -m gt_ai.evaluation.tts` only works from a directory that resolves
``gt_ai`` to this package; from the repo root it picks up the unrelated HTTP SDK
copy, which is why the script wrapper exists.)

The sentences come from the golden translation dataset (the target-language side
of each pair), so the corpus is the curated one and not invented text.
"""
from __future__ import annotations

import argparse
import array
import asyncio
import json
import logging
import os
import time
import wave
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

log = logging.getLogger("gt_ai.eval.tts")

DATASET_DIR = os.path.join(os.path.dirname(__file__), "datasets")
DEFAULT_DATASET = "golden_india_pairs"

#: A sentence is long enough to expose per-sentence overhead without turning the
#: benchmark into a wait; three is enough to see a voice choke on one of them.
MAX_CASES_PER_LANGUAGE = 3

# Promotion gates for speech output (Phase 3: benchmark target-language voices).
# Latency budgets are the pipeline's own: `rt_target_latency_ms` is 2500 ms for a
# whole turn, so a voice that needs most of a second before its first byte cannot
# be the room's default. Tighten per deployment; do not loosen to make a
# measurement pass.
GATES = {
    "max_first_audio_p95_ms": 900.0,
    "max_realtime_factor": 1.0,
    "min_audio_ms_per_case": 200.0,
    "max_failure_rate": 0.0,
}


@dataclass
class CaseResult:
    """One sentence, one voice."""
    case_id: str
    text: str
    ok: bool
    first_audio_ms: float = 0.0
    total_ms: float = 0.0
    audio_ms: float = 0.0
    realtime_factor: float = 0.0
    peak_amplitude: int = 0
    sample_rate: int = 0
    bytes_out: int = 0
    error: str | None = None
    #: The provider raised instead of producing audio. Only this can turn a voice
    #: into "unmeasured": a voice that produced silence did *something*, and what
    #: it did is a result.
    unavailable: bool = False


@dataclass
class VoiceReport:
    """One voice in one language — the unit a deployment chooses between."""
    lang: str
    provider: str
    voice: str
    available: bool
    n_cases: int = 0
    first_audio_p50_ms: float = 0.0
    first_audio_p95_ms: float = 0.0
    synthesis_p95_ms: float = 0.0
    realtime_factor: float = 0.0
    audio_ms_total: float = 0.0
    silent_cases: int = 0
    failure_rate: float = 0.0
    passed_gates: bool = False
    #: Why a voice was never measured ("piper voice missing: …"), verbatim from
    #: the provider. Distinct from a case failing: this one is not a result.
    unavailable_reason: str = ""
    gate_details: dict[str, Any] = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# corpus
# --------------------------------------------------------------------------- #
def load_texts(lang: str, dataset: str = DEFAULT_DATASET,
               limit: int = MAX_CASES_PER_LANGUAGE) -> list[tuple[str, str]]:
    """(case_id, text) in `lang`, taken from the golden dataset.

    A row contributes its `reference` when the pair translates *into* `lang` and
    its `source` when it translates *out of* it: both are sentences written in
    `lang` by whoever curated the pair.
    """
    path = os.path.join(DATASET_DIR, f"{dataset}.jsonl")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"dataset not found: {path}")
    out: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            text = ""
            if row.get("target_lang") == lang:
                text = row.get("reference") or ""
            elif row.get("source_lang") == lang:
                text = row.get("source") or ""
            text = text.strip()
            if text:
                out.append((str(row.get("id", f"{lang}_{len(out)}")), text))
            if len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- #
# measurement
# --------------------------------------------------------------------------- #
def _decode(chunk: Any) -> tuple[bytes, int]:
    """The raw PCM in one provider chunk, and its sample rate."""
    data = getattr(chunk, "data", b"") or b""
    rate = int(getattr(chunk, "sample_rate", 0) or 0)
    fmt = getattr(chunk, "format", "")
    if data[:4] == b"RIFF" and fmt in ("wav", ""):
        import io
        with wave.open(io.BytesIO(data), "rb") as wf:
            return wf.readframes(wf.getnframes()), wf.getframerate()
    return data, rate


def _peak(pcm: bytes) -> int:
    if len(pcm) < 2:
        return 0
    samples = array.array("h")
    samples.frombytes(pcm[:len(pcm) - len(pcm) % 2])
    return max((abs(s) for s in samples), default=0)


async def bench_case(provider: Any, lang: str, voice: str | None,
                     case_id: str, text: str) -> CaseResult:
    """Time one sentence through one voice, streaming as the room would."""
    t0 = time.perf_counter()
    first_audio_ms = -1.0
    audio_ms = 0.0
    pcm_all = bytearray()
    bytes_out = 0
    rate = 0
    try:
        stream = provider.synthesize_stream(text, lang, voice)
        async for chunk in stream:
            if first_audio_ms < 0:
                first_audio_ms = (time.perf_counter() - t0) * 1000
            pcm, chunk_rate = _decode(chunk)
            rate = chunk_rate or rate
            declared = float(getattr(chunk, "duration_ms", 0.0) or 0.0)
            bytes_out += len(pcm)
            audio_ms += declared or (
                len(pcm) / (rate * 2) * 1000 if rate else 0.0)
            pcm_all.extend(pcm)
        total_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:  # noqa: BLE001 - the harness records every failure
        return CaseResult(case_id=case_id, text=text, ok=False, unavailable=True,
                          error=f"{type(exc).__name__}: {exc}")
    peak = _peak(bytes(pcm_all))
    if first_audio_ms < 0:              # a stream that produced nothing
        return CaseResult(case_id=case_id, text=text, ok=False,
                          total_ms=round(total_ms, 1),
                          error="provider streamed no audio")
    silent = peak == 0
    return CaseResult(
        case_id=case_id, text=text, ok=not silent,
        first_audio_ms=round(first_audio_ms, 1), total_ms=round(total_ms, 1),
        audio_ms=round(audio_ms, 1),
        realtime_factor=round(total_ms / audio_ms, 3) if audio_ms else 0.0,
        peak_amplitude=peak, sample_rate=rate, bytes_out=bytes_out,
        error="digital silence" if silent else None)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct))]


async def bench_voice(provider: Any, lang: str, voice: str | None,
                      cases: Iterable[tuple[str, str]],
                      gates: dict[str, float] | None = None) -> VoiceReport:
    """Benchmark one voice, or record that it could not be benchmarked."""
    gates = gates or GATES
    name = voice or ""
    results: list[CaseResult] = []
    for case_id, text in cases:
        r = await bench_case(provider, lang, name or None, case_id, text)
        if r.unavailable and not results:
            # The provider raised before producing anything at all: that is an
            # availability statement, not a measurement. Nothing is scored, and
            # no number is invented for it.
            return VoiceReport(lang=lang, provider=getattr(provider, "name", "?"),
                               voice=name or "(provider default)",
                               available=False, unavailable_reason=r.error)
        results.append(r)

    firsts = [r.first_audio_ms for r in results]
    totals = [r.total_ms for r in results]
    audio = sum(r.audio_ms for r in results)
    synth = sum(r.total_ms for r in results)
    failures = sum(1 for r in results if not r.ok)
    silent = sum(1 for r in results if r.error == "digital silence")
    rtf = synth / audio if audio else 0.0
    rate = failures / max(1, len(results))
    gate_details = {
        "first_audio_ok": _percentile(firsts, 0.95) <= gates["max_first_audio_p95_ms"],
        "realtime_ok": rtf <= gates["max_realtime_factor"],
        "audio_ok": (audio / max(1, len(results))) >= gates["min_audio_ms_per_case"],
        "failures_ok": rate <= gates["max_failure_rate"],
    }
    return VoiceReport(
        lang=lang, provider=getattr(provider, "name", "?"),
        voice=name or "(provider default)", available=True, n_cases=len(results),
        first_audio_p50_ms=round(_percentile(firsts, 0.5), 1),
        first_audio_p95_ms=round(_percentile(firsts, 0.95), 1),
        synthesis_p95_ms=round(_percentile(totals, 0.95), 1),
        realtime_factor=round(rtf, 3), audio_ms_total=round(audio, 1),
        silent_cases=silent, failure_rate=round(rate, 4),
        passed_gates=all(gate_details.values()), gate_details=gate_details,
        cases=results)


def candidate_voices(provider: Any, lang: str) -> list[str]:
    """The voices one provider offers for one language, asked of the provider.

    A provider that cannot answer is treated as offering its default voice only:
    the benchmark then measures exactly what the realtime path would hear.
    """
    listing = getattr(provider, "voices_for", None)
    if listing is None:
        return []
    try:
        return list(listing(lang))
    except Exception as exc:  # noqa: BLE001 - a broken listing is itself a result
        log.warning("%s could not list %s voices: %s",
                    getattr(provider, "name", provider), lang, exc)
        return []


async def run_bench(providers: list[Any], langs: list[str],
                    voices: dict[str, list[str]] | None = None,
                    dataset: str = DEFAULT_DATASET) -> list[VoiceReport]:
    """Every (language, provider, voice) combination worth timing.

    A provider that lists no voice for a language is still measured once with no
    voice named, because that is precisely what the realtime path would do — and
    the room deserves a report line saying what it hears.
    """
    reports: list[VoiceReport] = []
    for lang in langs:
        cases = load_texts(lang, dataset)
        if not cases:
            reports.append(VoiceReport(
                lang=lang, provider="(dataset)", voice="-", available=False,
                unavailable_reason=f"no {lang} sentences in {dataset}.jsonl"))
            continue
        for provider in providers:
            explicit = (voices or {}).get(lang)
            named = explicit if explicit is not None else candidate_voices(provider, lang)
            for voice in (named or [""]):
                reports.append(await bench_voice(provider, lang, voice, cases))
    return reports


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def _build(provider_name: str, model_dir: str) -> Any:
    from gt_ai.registry import create
    if provider_name == "piper":
        return create("tts", "piper", model_dir=model_dir)
    return create("tts", provider_name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", default="en,hi",
                    help="comma-separated target languages (default: en,hi)")
    ap.add_argument("--provider", default="piper",
                    help="tts provider: piper | kokoro | dev_tone | …")
    ap.add_argument("--voice", default="",
                    help="restrict to these voice names (comma-separated); "
                         "default: every voice the provider offers for the language")
    ap.add_argument("--model-dir", default="model_cache/piper")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--out", default="", help="write the JSON report here too")
    args = ap.parse_args()

    provider = _build(args.provider, args.model_dir)
    langs = [x.strip() for x in args.lang.split(",") if x.strip()]
    voices = None
    if args.voice:
        # An explicit voice list applies to every requested language; naming a
        # voice for the wrong language is reported by the case itself.
        voices = {l: [v.strip() for v in args.voice.split(",") if v.strip()]
                  for l in langs}

    reports = asyncio.run(run_bench([provider], langs, voices=voices,
                                    dataset=args.dataset))

    print(json.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in reports], f, ensure_ascii=False, indent=2)
    unmeasured = [r for r in reports if not r.available]
    passed = [r for r in reports if r.passed_gates]
    print(f"\n{len(reports)} voice(s) asked about, {len(passed)} pass the gates, "
          f"{len(unmeasured)} could not be measured at all.")
    for r in unmeasured:
        print(f"  NOT MEASURED {r.lang}/{r.provider}/{r.voice}: {r.unavailable_reason}")


if __name__ == "__main__":
    main()
