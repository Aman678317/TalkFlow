#!/usr/bin/env python3
"""Evaluation runner (sections 43/90): measures installed providers on built-in datasets,
records QualityEvaluation rows, and (with --promote) upgrades language-pair validation
status when the automatic gate passes.

Usage:
  python scripts/run_evaluation.py                 # evaluate all feasible tasks
  python scripts/run_evaluation.py --task mt --pair en-hi
  python scripts/run_evaluation.py --promote       # write pair validations on gate pass
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps" / "api"))
sys.path.insert(0, str(REPO))

from ai.evaluation.datasets import DATASETS  # noqa: E402
from ai.evaluation.metrics import (EvalResult, bleu, gate_decision, number_preservation,  # noqa: E402
                                   percentile, time_call, url_preservation)


def eval_mt(provider, dataset: list[tuple[str, str, str]], src: str, tgt: str,
            dataset_name: str) -> EvalResult:
    result = EvalResult(task="mt", provider=getattr(provider, "name", "?"),
                        model=f"{getattr(provider, 'name', '?')}-{src}-{tgt}",
                        source_language=src, target_language=tgt, dataset=dataset_name,
                        samples=len(dataset))
    latencies: list[float] = []
    corpus = []
    num_scores, url_scores = [], []
    for source, reference, _cat in dataset:
        out, ms, err = time_call(provider.translate, source, src, tgt)
        latencies.append(ms)
        if err is not None or out is None or "untranslated_fallback" in (out.quality_flags or []):
            result.failures += 1
            continue
        corpus.append((reference, out.text))
        num_scores.append(number_preservation(source, out.text))
        url_scores.append(url_preservation(source, out.text))
    if corpus:
        result.metrics = {
            "bleu": bleu(corpus),
            "number_preservation": round(sum(num_scores) / len(num_scores), 3),
            "url_preservation": round(sum(url_scores) / len(url_scores), 3),
        }
    result.latency_p50_ms = percentile(latencies, 0.5)
    result.latency_p95_ms = percentile(latencies, 0.95)
    return result


def eval_stt(provider, audio_dir: Path) -> list[EvalResult]:
    from ai.evaluation.datasets import STT_AUDIO_MANIFEST
    from ai.evaluation.metrics import cer, wer
    results = []
    for name, meta in STT_AUDIO_MANIFEST.items():
        path = audio_dir / meta["file"]
        if not path.exists():
            continue
        import wave
        with wave.open(str(path)) as w:
            pcm = w.readframes(w.getnframes())
            sr = w.getframerate()
        out, ms, err = time_call(provider.transcribe, pcm, sr, language=meta["language"])
        r = EvalResult(task="stt", provider=getattr(provider, "name", "?"),
                       model=name, source_language=meta["language"], dataset=name, samples=1)
        if err is not None or out is None:
            r.failures = 1
        elif meta["reference"]:
            r.metrics = {"wer": round(wer(meta["reference"], out.text), 3),
                         "cer": round(cer(meta["reference"], out.text), 3),
                         "hypothesis": out.text[:200]}
        r.latency_p50_ms = r.latency_p95_ms = round(ms, 1)
        results.append(r)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="all")
    ap.add_argument("--pair", default="")
    ap.add_argument("--promote", action="store_true",
                    help="persist pair validation status when the gate passes")
    ap.add_argument("--audio-dir", default=os.environ.get("EVAL_AUDIO_PATH", ""))
    args = ap.parse_args()

    from ai.providers.translation.argos import ArgosTranslation
    from globaltalk.core.db import SessionLocal, init_db
    from globaltalk.models import LanguagePairValidation, QualityEvaluation

    init_db()
    db = SessionLocal()
    all_results: list[EvalResult] = []

    if args.task in ("all", "mt"):
        argos = ArgosTranslation()
        pairs_installed = argos.supported_pairs()
        for (task, src, tgt), dataset in DATASETS.items():
            if not task.startswith("mt"):
                continue
            if args.pair and f"{src}-{tgt}" != args.pair:
                continue
            if task == "mt" and (src, tgt) not in pairs_installed:
                print(f"-- skip mt {src}->{tgt}: pair not installed (honest NOT_CONFIGURED)")
                continue
            r = eval_mt(argos, dataset, src, tgt, f"builtin-{task}-{src}-{tgt}")
            all_results.append(r)

    if args.task in ("all", "stt") and args.audio_dir:
        from ai.providers.stt.faster_whisper import FasterWhisperSTT
        from globaltalk.core.config import settings
        stt = FasterWhisperSTT(settings.stt_model.split("/")[-1].replace("faster-whisper-", ""),
                               settings.stt_device, settings.stt_compute_type)
        if stt.available():
            all_results.extend(eval_stt(stt, Path(args.audio_dir)))

    # ---- report + persist
    for r in all_results:
        status, reasons = gate_decision(r.task, r)
        print(f"[{r.task}] {r.source_language}->{r.target_language or r.model} "
              f"dataset={r.dataset} samples={r.samples} failures={r.failures} "
              f"metrics={r.metrics} p50={r.latency_p50_ms}ms p95={r.latency_p95_ms}ms "
              f"=> {status} ({'; '.join(reasons)})")
        db.add(QualityEvaluation(task=r.task, dataset=r.dataset, source_language=r.source_language,
                                 target_language=r.target_language, provider=r.provider,
                                 model=r.model, metrics={**r.metrics,
                                                         "latency_p50_ms": r.latency_p50_ms,
                                                         "latency_p95_ms": r.latency_p95_ms,
                                                         "failure_rate": round(r.failure_rate, 3)},
                                 samples=r.samples, passed_gate=(status != "EXPERIMENTAL"),
                                 notes="; ".join(reasons)))
        if args.promote and r.task == "mt" and status != "EXPERIMENTAL" \
                and r.dataset.startswith("builtin-mt-"):
            # only the primary dataset promotes a pair; robustness datasets
            # (code-switching, noise) inform but don't overwrite the pair gate
            row = (db.query(LanguagePairValidation)
                   .filter(LanguagePairValidation.source == r.source_language,
                           LanguagePairValidation.target == r.target_language,
                           LanguagePairValidation.task == "mt").first())
            if not row:
                row = LanguagePairValidation(source=r.source_language, target=r.target_language,
                                             task="mt")
                db.add(row)
            row.status = status  # SUPPORTED now; PRODUCTION only after human review flag
            row.provider = r.provider
            row.metric_scores = r.metrics
            row.evaluated_at = datetime.now(timezone.utc)
    db.commit()
    db.close()
    print(f"\n{len(all_results)} evaluation(s) recorded"
          + (" (pair validations promoted)" if args.promote else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
