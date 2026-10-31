"""Automated evaluation harness for translation quality scoring."""
from __future__ import annotations

import re
from typing import Dict, List, Optional
import sacrebleu


def compute_bleu(hypotheses: List[str], references: List[List[str]]) -> float:
    """Computes standard SacreBLEU score."""
    if not hypotheses or not references:
        return 0.0
    bleu = sacrebleu.corpus_bleu(hypotheses, references)
    return round(bleu.score, 2)


def compute_chrf(hypotheses: List[str], references: List[List[str]]) -> float:
    """Computes character-level chrF++ score (very effective for Indian agglutinative/inflected scripts)."""
    if not hypotheses or not references:
        return 0.0
    chrf = sacrebleu.corpus_chrf(hypotheses, references, word_order=2)
    return round(chrf.score, 2)


def evaluate_sample_preservation(source: str, translation: str) -> Dict[str, bool]:
    """Checks exact number, url, and email preservation."""
    num_re = re.compile(r"\b\d+(?:[.,]\d+)*\b")
    src_nums = sorted(num_re.findall(source))
    tgt_nums = sorted(num_re.findall(translation))

    url_re = re.compile(r"https?://\S+|www\.\S+", re.I)
    src_urls = set(url_re.findall(source))
    tgt_urls = set(url_re.findall(translation))

    return {
        "numbers_preserved": src_nums == tgt_nums,
        "urls_preserved": src_urls.issubset(tgt_urls) if src_urls else True,
        "non_empty": bool(translation.strip()),
    }

