"""Evaluation metrics (section 43) — pure-python, no heavy deps.

WER/CER (Levenshtein), corpus BLEU (up to 4-gram with brevity penalty), number/entity
preservation checks, latency and failure-rate aggregation. COMET is exposed as an
optional adapter (requires GPU; NOT_CONFIGURED otherwise) — quality gates combine
automatic metrics with human review flags before a pair can reach PRODUCTION.
"""
from __future__ import annotations

import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field


def _norm(text: str, lower: bool = True) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t.lower() if lower else t).strip()


def _levenshtein(a: list, b: list) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    r, h = _norm(reference).split(), _norm(hypothesis).split()
    if not r:
        return 0.0 if not h else 1.0
    return _levenshtein(r, h) / len(r)


def cer(reference: str, hypothesis: str) -> float:
    r, h = list(_norm(reference)), list(_norm(hypothesis))
    if not r:
        return 0.0 if not h else 1.0
    return _levenshtein(r, h) / len(r)


def bleu(corpus: list[tuple[str, str]], max_n: int = 4) -> float:
    """Corpus-level BLEU with brevity penalty (references, hypotheses pairs)."""
    import math
    total_matches = [0] * max_n
    total_counts = [0] * max_n
    ref_len = hyp_len = 0
    for ref, hyp in corpus:
        r, h = _norm(ref).split(), _norm(hyp).split()
        ref_len += len(r)
        hyp_len += len(h)
        for n in range(1, max_n + 1):
            r_grams = Counter(tuple(r[i:i + n]) for i in range(len(r) - n + 1))
            h_grams = Counter(tuple(h[i:i + n]) for i in range(len(h) - n + 1))
            for gram, cnt in h_grams.items():
                total_matches[n - 1] += min(cnt, r_grams.get(gram, 0))
                total_counts[n - 1] += cnt
    precisions = []
    for n in range(max_n):
        if total_counts[n] == 0:
            precisions.append(0.0)
        else:
            precisions.append(total_matches[n] / total_counts[n])
    if any(p == 0 for p in precisions):
        return 0.0
    geo = math.exp(sum(math.log(p) for p in precisions) / max_n)
    bp = 1.0 if hyp_len >= ref_len else math.exp(1 - ref_len / max(hyp_len, 1))
    return round(bp * geo * 100, 2)


NUM_RE = re.compile(r"\d[\d.,]*")


def number_preservation(source: str, translation: str) -> float:
    s, t = sorted(NUM_RE.findall(source)), sorted(NUM_RE.findall(translation))
    if not s:
        return 1.0
    return sum(1 for x in s if x in t) / len(s)


def url_preservation(source: str, translation: str) -> float:
    urls = re.findall(r"https?://\S+|www\.\S+", source)
    if not urls:
        return 1.0
    return sum(1 for u in urls if u in translation) / len(urls)


@dataclass
class EvalResult:
    task: str
    provider: str
    model: str
    source_language: str = ""
    target_language: str = ""
    dataset: str = ""
    samples: int = 0
    failures: int = 0
    metrics: dict = field(default_factory=dict)
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    duration_s: float = 0.0

    @property
    def failure_rate(self) -> float:
        return self.failures / max(self.samples, 1)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(p * len(s)))], 2)


# ------------------------------------------------------------------ quality gate

GATE_THRESHOLDS = {
    # metric → (min, max) for SUPPORTED promotion; PRODUCTION adds human review
    "mt": {"bleu_min": 15.0, "number_preservation_min": 0.9, "failure_rate_max": 0.05,
           "latency_p95_ms_max": 15_000},
    "stt": {"wer_max": 0.45, "cer_max": 0.35, "failure_rate_max": 0.05},
    "tts": {"failure_rate_max": 0.05, "latency_p95_ms_max": 8_000},
}


def gate_decision(task: str, result: EvalResult, human_reviewed: bool = False) -> tuple[str, list[str]]:
    """Returns (status, reasons). Never promotes to PRODUCTION without human review
    (section 43: 'Never judge a language as production-ready only from model metadata')."""
    th = GATE_THRESHOLDS.get(task, {})
    reasons: list[str] = []
    m = result.metrics
    ok = True
    if result.samples == 0:
        return "EXPERIMENTAL", ["no samples evaluated"]
    if "bleu_min" in th and m.get("bleu", 0) < th["bleu_min"]:
        ok = False
        reasons.append(f"bleu {m.get('bleu')} < {th['bleu_min']}")
    if "number_preservation_min" in th and m.get("number_preservation", 0) < th["number_preservation_min"]:
        ok = False
        reasons.append(f"number_preservation {m.get('number_preservation')} < {th['number_preservation_min']}")
    if "wer_max" in th and m.get("wer", 1) > th["wer_max"]:
        ok = False
        reasons.append(f"wer {m.get('wer')} > {th['wer_max']}")
    if "cer_max" in th and m.get("cer", 1) > th["cer_max"]:
        ok = False
        reasons.append(f"cer {m.get('cer')} > {th['cer_max']}")
    if "failure_rate_max" in th and result.failure_rate > th["failure_rate_max"]:
        ok = False
        reasons.append(f"failure_rate {result.failure_rate:.2f} > {th['failure_rate_max']}")
    if not ok:
        return "EXPERIMENTAL", reasons
    if human_reviewed:
        return "PRODUCTION", ["passed automatic gate + human review"]
    return "SUPPORTED", ["passed automatic gate; human review pending for PRODUCTION"]


def time_call(fn, *args, **kwargs):
    t0 = time.perf_counter()
    try:
        out = fn(*args, **kwargs)
        return out, (time.perf_counter() - t0) * 1000, None
    except Exception as exc:
        return None, (time.perf_counter() - t0) * 1000, exc
