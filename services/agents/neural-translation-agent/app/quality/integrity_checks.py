"""Post-generation output integrity verification (Agent 04 Pre-Checks)."""
from __future__ import annotations

import re
from typing import List
from app.quality.quality_flags import QualityFlag

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*\b")


def check_translation_integrity(source: str, translated: str, source_lang: str = "", target_lang: str = "") -> List[str]:
    """Evaluates basic output integrity without attempting subjective semantic evaluation."""
    flags: List[str] = []

    if not translated or not translated.strip():
        flags.append(QualityFlag.EMPTY_TRANSLATION)
        return flags

    # 1. Number preservation check
    src_nums = sorted(_NUMBER_RE.findall(source))
    tgt_nums = sorted(_NUMBER_RE.findall(translated))
    if src_nums != tgt_nums:
        flags.append(QualityFlag.NUMBER_MISMATCH)

    # 2. URLs and Emails must survive verbatim
    for rx in (_URL_RE, _EMAIL_RE):
        src_hits = set(m.group(0) for m in rx.finditer(source))
        tgt_hits = set(m.group(0) for m in rx.finditer(translated))
        if src_hits and not src_hits.issubset(tgt_hits):
            flags.append(QualityFlag.URL_OR_EMAIL_LOST)
            break

    # 3. Length anomaly checks
    src_len = max(1, len(source))
    tgt_len = len(translated)
    ratio = tgt_len / src_len
    if ratio > 4.0:
        flags.append(QualityFlag.SUSPICIOUSLY_LONG)
    elif ratio < 0.15 and len(source) > 40:
        flags.append(QualityFlag.SUSPICIOUSLY_SHORT)

    # 4. Cross-script loss check
    # If source is Devanagari (Hindi/Marathi) and target is Devanagari, but output is purely ASCII:
    is_src_deva = any("\u0900" <= ch <= "\u097F" for ch in source)
    if is_src_deva and target_lang in ("hi", "mr") and translated.isascii():
        flags.append(QualityFlag.SCRIPT_LOST)

    # 5. Untranslated identical output check for cross-script pairs
    if translated.strip() == source.strip() and not source.isascii() and source_lang != target_lang:
        flags.append(QualityFlag.UNTRANSLATED_OUTPUT)

    return flags

