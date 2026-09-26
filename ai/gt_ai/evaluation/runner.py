"""Evaluation runner (PDD §43, §44).

Runs golden datasets through the *configured provider chain* and produces a
report per language pair: BLEU, number preservation, terminology accuracy,
latency, failure rate. A language pair is promoted to PRODUCTION in the
capability registry only when its report passes the gates — never from model
metadata alone.

Usage:
    python -m gt_ai.evaluation.runner --dataset golden_hi_en --provider-chain auto
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from gt_ai.evaluation.metrics import (
    bleu,
    cer,
    number_preservation_score,
    terminology_accuracy,
    wer,
)

log = logging.getLogger("gt_ai.eval")

DATASET_DIR = os.path.join(os.path.dirname(__file__), "datasets")

# Promotion gates (PDD §8: per-pair enablement)
GATES = {
    "min_bleu": 15.0,
    "max_failure_rate": 0.05,
    "min_number_preservation": 0.95,
    "max_p95_latency_ms": 5000.0,
}


@dataclass
class CaseResult:
    case_id: str
    source: str
    reference: str
    output: str
    bleu: float
    cer: float
    number_preservation: float
    terminology_accuracy: float
    latency_ms: float
    error: str | None = None


@dataclass
class PairReport:
    pair: str
    domain: str
    n_cases: int
    bleu_avg: float
    cer_avg: float
    number_preservation_avg: float
    terminology_accuracy_avg: float
    latency_p50_ms: float
    latency_p95_ms: float
    failure_rate: float
    passed_gates: bool
    gate_details: dict[str, Any] = field(default_factory=dict)
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def load_dataset(name: str) -> list[dict]:
    path = os.path.join(DATASET_DIR, f"{name}.jsonl")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"dataset not found: {path}")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def run_dataset(
    name: str,
    translate_fn: Any,  # async (text, src, tgt, domain, glossary) -> TranslationResult
    gates: dict[str, float] | None = None,
) -> list[PairReport]:
    gates = gates or GATES
    rows = load_dataset(name)
    by_pair: dict[tuple[str, str, str], list[dict]] = {}
    for r in rows:
        key = (r["source_lang"], r["target_lang"], r.get("domain", "general"))
        by_pair.setdefault(key, []).append(r)

    reports: list[PairReport] = []
    for (src, tgt, domain), cases in by_pair.items():
        results: list[CaseResult] = []
        for c in cases:
            t0 = time.perf_counter()
            err = None
            out = ""
            try:
                tr = await translate_fn(
                    c["source"], src, tgt, domain, c.get("glossary") or None
                )
                out = tr.text
            except Exception as e:  # noqa: BLE001 - eval harness records all failures
                err = f"{type(e).__name__}: {e}"
            latency = (time.perf_counter() - t0) * 1000
            results.append(CaseResult(
                case_id=c.get("id", ""),
                source=c["source"],
                reference=c["reference"],
                output=out,
                bleu=bleu(c["reference"], out) * 100 if not err else 0.0,
                cer=cer(c["reference"], out) if not err else 1.0,
                number_preservation=number_preservation_score(c["source"], out) if not err else 0.0,
                terminology_accuracy=terminology_accuracy(
                    c["source"], out, c.get("glossary") or {}) if not err else 0.0,
                latency_ms=latency,
                error=err,
            ))
        n = len(results)
        failures = sum(1 for r in results if r.error)
        lat = sorted(r.latency_ms for r in results)
        p50 = lat[n // 2] if n else 0.0
        p95 = lat[min(n - 1, int(n * 0.95))] if n else 0.0
        bleu_avg = sum(r.bleu for r in results) / max(1, n)
        failure_rate = failures / max(1, n)
        num_avg = sum(r.number_preservation for r in results) / max(1, n)
        gate_details = {
            "bleu_ok": bleu_avg >= gates["min_bleu"],
            "failure_ok": failure_rate <= gates["max_failure_rate"],
            "numbers_ok": num_avg >= gates["min_number_preservation"],
            "latency_ok": p95 <= gates["max_p95_latency_ms"],
        }
        reports.append(PairReport(
            pair=f"{src}->{tgt}", domain=domain, n_cases=n,
            bleu_avg=round(bleu_avg, 2),
            cer_avg=round(sum(r.cer for r in results) / max(1, n), 4),
            number_preservation_avg=round(num_avg, 4),
            terminology_accuracy_avg=round(
                sum(r.terminology_accuracy for r in results) / max(1, n), 4),
            latency_p50_ms=round(p50, 1), latency_p95_ms=round(p95, 1),
            failure_rate=round(failure_rate, 4),
            passed_gates=all(gate_details.values()),
            gate_details=gate_details,
            cases=results,
        ))
    return reports


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="golden_hi_en")
    ap.add_argument("--provider", default="dev_echo")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from gt_ai.registry import create
    from gt_ai.types import Intent, TranslationRequest

    provider = create("mt", args.provider)

    async def translate_fn(text, src, tgt, domain, glossary):
        return await provider.translate(TranslationRequest(  # type: ignore[attr-defined]
            text=text, source_lang=src, target_lang=tgt, domain=domain,
            intent=Intent.QUALITY_OPTIMIZED, glossary=glossary))

    reports = asyncio.run(run_dataset(args.dataset, translate_fn))
    out = [r.to_dict() for r in reports]
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
