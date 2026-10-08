"""Evaluation metrics: WER, CER, BLEU (PDD §43).

Pure-python implementations — deterministic, testable, no deps.
COMET-class semantic metrics are integrated via the `comet_score` adapter
hook (requires unbabel-comet installed separately; license-reviewed).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text.lower())
    text = re.sub(r"[.,!?;:\"'()\[\]{}।؟۔]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _edit_distance(a: list, b: list) -> int:
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
    """Word Error Rate. 0.0 = perfect; >1.0 possible with insertions."""
    ref = _normalize(reference).split()
    hyp = _normalize(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate — primary metric for morphologically rich
    Indic languages where word segmentation varies."""
    ref = list(_normalize(reference).replace(" ", ""))
    hyp = list(_normalize(hypothesis).replace(" ", ""))
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def bleu(reference: str, hypothesis: str, max_n: int = 4) -> float:
    """Sentence-level BLEU with brevity penalty (simplified, corpus-usable
    by averaging). For final decisions use sacrebleu in the eval harness."""
    ref = _normalize(reference).split()
    hyp = _normalize(hypothesis).split()
    if not hyp or not ref:
        return 0.0
    import math
    precisions = []
    for n in range(1, max_n + 1):
        ref_ngrams = Counter(tuple(ref[i : i + n]) for i in range(len(ref) - n + 1))
        hyp_ngrams = Counter(tuple(hyp[i : i + n]) for i in range(len(hyp) - n + 1))
        clipped = sum(min(count, ref_ngrams[ng]) for ng, count in hyp_ngrams.items())
        total = max(1, sum(hyp_ngrams.values()))
        precisions.append(clipped / total)
    if any(p == 0 for p in precisions):
        return 0.0
    geo = math.exp(sum(math.log(p) for p in precisions) / len(precisions))
    bp = 1.0 if len(hyp) >= len(ref) else math.exp(1 - len(ref) / len(hyp))
    return bp * geo


def number_preservation_score(source: str, translated: str) -> float:
    """PDD §10.1: isolated number corruption is a high-value QA signal."""
    src = re.findall(r"\d+(?:[.,]\d+)*", source)
    tgt = re.findall(r"\d+(?:[.,]\d+)*", translated)
    if not src:
        return 1.0
    return len(set(src) & set(tgt)) / len(set(src))


def terminology_accuracy(source: str, translated: str,
                         glossary: dict[str, str]) -> float:
    """Fraction of glossary terms present in source that appear (as their
    preferred target) in the translation."""
    if not glossary:
        return 1.0
    hits = total = 0
    low_src, low_tgt = source.lower(), translated.lower()
    for src_term, tgt_term in glossary.items():
        if src_term.lower() in low_src:
            total += 1
            if tgt_term.lower() in low_tgt:
                hits += 1
    return hits / total if total else 1.0
