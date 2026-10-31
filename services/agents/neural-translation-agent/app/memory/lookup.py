"""Hashing and fuzzy similarity matching for Translation Memory."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Set, Tuple

_WORD_RX = re.compile(r"[\w']+", re.UNICODE)


def normalize_text_for_hash(text: str) -> str:
    """NFC normalization, lowercased, and whitespace collapsed."""
    t = unicodedata.normalize("NFC", text).strip().lower()
    return re.sub(r"\s+", " ", t)


def compute_normalized_hash(text: str) -> str:
    """Returns SHA-256 hash of normalized text for O(1) exact lookups."""
    norm = normalize_text_for_hash(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:64]


def calculate_lexical_similarity(text_a: str, text_b: str) -> float:
    """Computes Sørensen-Dice coefficient over word bigrams for script-agnostic fuzzy matching."""
    def extract_bigrams(s: str) -> Set[Tuple[str, ...]]:
        words = _WORD_RX.findall(normalize_text_for_hash(s))
        if not words:
            return set()
        if len(words) == 1:
            return {(words[0],)}
        return {tuple(words[i:i + 2]) for i in range(len(words) - 1)}

    bigrams_a = extract_bigrams(text_a)
    bigrams_b = extract_bigrams(text_b)

    if not bigrams_a or not bigrams_b:
        return 0.0

    intersection = len(bigrams_a & bigrams_b)
    return 2.0 * intersection / (len(bigrams_a) + len(bigrams_b))

