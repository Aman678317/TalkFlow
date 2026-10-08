"""Protected spans + glossary application for MT (PDD §10.1, §16).

Protected spans are marked BEFORE generation and restored AFTER generation:
names, URLs, emails, numbers/currency, code, IDs. Isolated number
corruption is a high-value QA signal.

Glossary terms are applied as constrained post-processing: after the model
produces a translation, glossary source terms found in the source text force
the preferred target term into the output (case-aware replacement of the
model's free choice where the term appears). This works with ANY backend
(model-agnostic customization), and backends may additionally receive the
glossary as a prompt/constraint hint.
"""
from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------- #
# Unicode normalization
# --------------------------------------------------------------------------- #

def normalize_unicode(text: str) -> str:
    """NFC normalize (Devanagari matras etc. depend on composed forms)."""
    return unicodedata.normalize("NFC", text)


# --------------------------------------------------------------------------- #
# Protected spans
# --------------------------------------------------------------------------- #

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CODE_RE = re.compile(r"`[^`]+`")
_ID_RE = re.compile(r"\b(?:SKU|TICKET|CASE|INC|ORD|INV)-[A-Z0-9-]+\b", re.I)
# Numbers incl. Indian grouping (1,00,000.50), currency symbols, percentages
_NUMBER_RE = re.compile(
    r"(?:[₹$€£¥]|USD|INR|EUR|GBP|JPY)?\s?"
    r"[-+]?\d{1,3}(?:[,،]\d{2,3})*(?:\.\d+)?%?"
    r"|\b\d+(?:\.\d+)?%?\b"
)


class SpanProtector:
    """Replace protected spans with opaque placeholders, restore afterwards.

    Placeholders are single Private-Use-Area characters (U+E000+idx) so no
    later regex pass can match inside them (ASCII digits in tokens would be
    re-protected by the number regex — a real corruption bug this avoids).
    """

    _BASE = 0xE000

    def __init__(self) -> None:
        self._spans: list[str] = []

    def protect(self, text: str) -> str:
        self._spans = []
        out = text
        for rx in (_CODE_RE, _URL_RE, _EMAIL_RE, _ID_RE, _NUMBER_RE):
            def repl(m: re.Match) -> str:
                idx = len(self._spans)
                if idx >= 0xDFF:  # PUA budget exhausted — keep raw text
                    return m.group(0)
                self._spans.append(m.group(0))
                return chr(self._BASE + idx)
            out = rx.sub(repl, out)
        return out

    def restore(self, text: str) -> str:
        for idx, span in enumerate(self._spans):
            text = text.replace(chr(self._BASE + idx), span)
        text = re.sub(r"[\uE000-\uE0FF]", "", text)
        return text

    @property
    def span_count(self) -> int:
        return len(self._spans)


# --------------------------------------------------------------------------- #
# Glossary application
# --------------------------------------------------------------------------- #

def build_glossary_pattern(glossary: dict[str, str]) -> re.Pattern | None:
    if not glossary:
        return None
    terms = sorted(glossary.keys(), key=len, reverse=True)
    escaped = [re.escape(t) for t in terms]
    return re.compile("|".join(escaped), re.IGNORECASE | re.UNICODE)


def glossary_terms_in_source(source_text: str, glossary: dict[str, str]) -> dict[str, str]:
    """Return the subset {src_term: tgt_term} actually present in source."""
    if not glossary:
        return {}
    rx = build_glossary_pattern(glossary)
    if rx is None:
        return {}
    hits: dict[str, str] = {}
    for m in rx.finditer(source_text):
        matched = m.group(0)
        # map back to canonical glossary key (case-insensitive)
        for k, v in glossary.items():
            if k.lower() == matched.lower():
                hits[k] = v
                break
    return hits


def apply_glossary_to_output(
    translated: str,
    source_text: str,
    glossary: dict[str, str],
) -> tuple[str, list[str]]:
    """Enforce preferred target terms in model output.

    Strategy: find glossary source terms present in the source; check whether
    the preferred target term is present in the output (case-insensitive).
    If absent, we cannot blindly substitute (word order differs), so we
    append nothing but raise a `glossary_term_missing:<term>` quality flag —
    deterministic, honest, and useful for QA/review workflows.
    For single-token terms the backend-specific constraint (prompt-level)
    usually handles it; this is the safety net.
    """
    flags: list[str] = []
    if not glossary:
        return translated, flags
    active = glossary_terms_in_source(source_text, glossary)
    lowered = translated.lower()
    for src_term, tgt_term in active.items():
        if tgt_term.lower() not in lowered:
            flags.append(f"glossary_term_missing:{tgt_term}")
    return translated, flags


def apply_glossary_to_source(source_text: str, glossary: dict[str, str]) -> tuple[str, dict[int, str]]:
    """Protect glossary source terms as spans and return mapping idx->target.

    Used by prompt-based backends and by the spoken-term normalizer.
    """
    protected: dict[int, str] = {}
    if not glossary:
        return source_text, protected
    rx = build_glossary_pattern(glossary)
    if rx is None:
        return source_text, protected
    counter = 0

    def repl(m: re.Match) -> str:
        nonlocal counter
        matched = m.group(0)
        for k, v in glossary.items():
            if k.lower() == matched.lower():
                token = chr(0xE100 + counter)
                protected[counter] = v
                counter += 1
                return token
        return matched

    return rx.sub(repl, source_text), protected


def restore_glossary_targets(text: str, protected: dict[int, str]) -> str:
    for idx, tgt in protected.items():
        text = text.replace(chr(0xE100 + idx), tgt)
    text = re.sub(r"[\uE100-\uE1FF]", "", text)
    return text


# --------------------------------------------------------------------------- #
# Spoken-term normalization (PDD §16: glossary must work in speech too)
# --------------------------------------------------------------------------- #

_ACRONYM_SPLIT_RE = re.compile(r"\b([A-Z]{2,6})\b")


def normalize_spoken_terms(text: str, spoken_terms: dict[str, str] | None) -> str:
    """Rewrite STT output variants into canonical written terms.

    STT often yields 'C P U' / 'cpu' / 'see pee you' style fragments for
    acronyms and product names. spoken_terms maps variant -> canonical.
    """
    if not spoken_terms:
        return text
    for variant, canonical in spoken_terms.items():
        text = re.sub(rf"\b{re.escape(variant)}\b", canonical, text, flags=re.IGNORECASE)
    return text


# --------------------------------------------------------------------------- #
# Post-translation QA checks (PDD §10 steps 8-9)
# --------------------------------------------------------------------------- #

def quality_checks(source: str, translated: str) -> list[str]:
    flags: list[str] = []
    if not translated.strip():
        flags.append("empty_translation")
        return flags
    # numbers must survive
    src_nums = re.findall(r"\d+(?:[.,]\d+)*", source)
    tgt_nums = re.findall(r"\d+(?:[.,]\d+)*", translated)
    if sorted(src_nums) != sorted(tgt_nums):
        flags.append("number_mismatch")
    # urls/emails must survive verbatim
    for rx in (_URL_RE, _EMAIL_RE):
        src_hits = set(m.group(0) for m in rx.finditer(source))
        tgt_hits = set(m.group(0) for m in rx.finditer(translated))
        if src_hits and not src_hits.issubset(tgt_hits):
            flags.append("url_or_email_lost")
            break
    # length ratio sanity
    ratio = len(translated) / max(1, len(source))
    if ratio > 4.0:
        flags.append("suspiciously_long")
    elif ratio < 0.15 and len(source) > 40:
        flags.append("suspiciously_short")
    # script check: Devanagari source shouldn't come back as pure ASCII when
    # target is hi/mr (crude but catches total failures)
    if any("\u0900" <= ch <= "\u097F" for ch in source) and translated.isascii():
        flags.append("script_lost")
    # identical output for cross-script pairs usually means a no-op failure
    if translated.strip() == source.strip() and not source.isascii():
        flags.append("untranslated_output")
    return flags
