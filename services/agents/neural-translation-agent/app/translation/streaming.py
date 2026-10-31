"""Sentence boundary detection and stable prefix splitting for streaming translation."""
from __future__ import annotations

from typing import Tuple

_SENTENCE_END = ".!?。！？…\n"
_CLOSERS = "\"'”’)]}"


def split_stable_prefix(text: str, min_prefix: int = 20) -> Tuple[str, str]:
    """Splits a live text stream into a stable completed prefix and still-changing tail.
    
    Returns (stable_prefix, tail).
    """
    body = text.rstrip()
    if len(body) < min_prefix:
        return "", body

    boundaries = []
    i = 0
    while i < len(body):
        if body[i] not in _SENTENCE_END:
            i += 1
            continue
        j = i + 1
        while j < len(body) and body[j] in _CLOSERS:
            j += 1
        # Require whitespace or end of string after punctuation so decimals (3.14) are not cut
        if j >= len(body) or body[j].isspace():
            boundaries.append(j)
        i = j

    if not boundaries:
        return "", body

    if boundaries[-1] < len(body):
        # Final sentence is incomplete: all preceding complete sentences are stable
        cut = boundaries[-1]
    else:
        # Final sentence has punctuation: if multiple sentences exist, leave last one for final pass
        if len(boundaries) < 2:
            return "", body
        cut = boundaries[-2]

    prefix = body[:cut].strip()
    tail = body[cut:].strip()
    if len(prefix) < min_prefix or not tail:
        return "", body

    return prefix, tail

