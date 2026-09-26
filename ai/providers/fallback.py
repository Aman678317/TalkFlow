"""Honest degradation providers — the FINAL fallback in every chain.

Per the failure rules (sections 37/89): when no real model is available the platform must
degrade, not fabricate. The passthrough translator returns the SOURCE text flagged
`untranslated_fallback` so UI shows "translation unavailable, original shown"; captions and
original audio keep the meeting usable. This is NOT a fake translation: it never invents
target-language text and is always visible via quality_flags + component health.
"""
from __future__ import annotations

from ai.interfaces import DetectionResult, TranslationResult


class PassthroughTranslation:
    """Final fallback: original-language output, explicitly flagged."""
    name = "passthrough"

    def healthy(self) -> bool:
        return True

    def supported_pairs(self) -> set[tuple[str, str]]:
        return set()  # claims nothing; router only uses it as last resort

    def translate(self, text: str, source_language: str, target_language: str, *,
                  glossary=None, domain: str = "general", style_hint: str = "") -> TranslationResult:
        return TranslationResult(
            text=text, source_language=source_language, target_language=target_language,
            provider=self.name, model="none", confidence=0.0,
            quality_flags=["untranslated_fallback", "ai_unavailable"])


class ScriptHeuristicLangID:
    """Deterministic Unicode-script language ID (real algorithm, zero models).

    Scripts are unambiguous for most platform languages (Devanagari→hi/mr, Bengali→bn,
    Tamil→ta, Telugu→te, Gujarati→gu, Kannada→kn, Malayalam→ml, Gurmukhi→pa, Arabic/Urdu,
    CJK). Latin text defers to the ML provider (whisper/langid)."""
    name = "script-heuristic"

    SCRIPT_MAP = [
        ((0x0900, 0x097F), ["hi", "mr"]),       # Devanagari
        ((0x0980, 0x09FF), ["bn"]),             # Bengali
        ((0x0A80, 0x0AFF), ["gu"]),             # Gujarati
        ((0x0A00, 0x0A7F), ["pa"]),             # Gurmukhi
        ((0x0B80, 0x0BFF), ["ta"]),             # Tamil
        ((0x0C00, 0x0C7F), ["te"]),             # Telugu
        ((0x0C80, 0x0CFF), ["kn"]),             # Kannada
        ((0x0D00, 0x0D7F), ["ml"]),             # Malayalam
        ((0x0600, 0x06FF), ["ur", "ar"]),       # Arabic script (ur default on this platform)
        ((0x3040, 0x30FF), ["ja"]),             # Kana → Japanese
        ((0x4E00, 0x9FFF), ["zh", "ja"]),       # Han
        ((0xAC00, 0xD7AF), ["ko"]),             # Hangul
    ]

    def healthy(self) -> bool:
        return True

    def detect(self, text: str) -> DetectionResult:
        counts: dict[str, int] = {}
        for ch in text:
            cp = ord(ch)
            for (lo, hi), langs in self.SCRIPT_MAP:
                if lo <= cp <= hi:
                    counts[langs[0]] = counts.get(langs[0], 0) + 1
                    break
        if counts:
            best = max(counts.items(), key=lambda kv: kv[1])
            total = sum(counts.values())
            return DetectionResult(language=best[0], confidence=min(0.99, best[1] / max(total, 1)),
                                   provider=self.name,
                                   alternatives=[(l, c / total) for l, c in
                                                 sorted(counts.items(), key=lambda kv: -kv[1])])
        return DetectionResult(language="", confidence=0.0, provider=self.name)
