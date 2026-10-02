"""langdetect adapter (pure-python, zero model files — bundled fallback).

Real statistical detection (Google's language-detection port). Lower
accuracy on very short strings than fastText/CLD3 but requires nothing.
Augmented with Unicode-script heuristics which are highly reliable for the
Indic/CJK/Arabic scripts this platform prioritizes.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import DetectionResult

# Script block -> likely language candidates (ordered)
SCRIPT_HINTS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"[\u0900-\u097F]"), ["hi", "mr"]),   # Devanagari: hi vs mr needs stats
    (re.compile(r"[\u0980-\u09FF]"), ["bn"]),
    (re.compile(r"[\u0B80-\u0BFF]"), ["ta"]),
    (re.compile(r"[\u0C00-\u0C7F]"), ["te"]),
    (re.compile(r"[\u0A80-\u0AFF]"), ["gu"]),
    (re.compile(r"[\u0C80-\u0CFF]"), ["kn"]),
    (re.compile(r"[\u0D00-\u0D7F]"), ["ml"]),
    (re.compile(r"[\u0A00-\u0A7F]"), ["pa"]),
    (re.compile(r"[\u0600-\u06FF]"), ["ur", "ar"]),
    (re.compile(r"[\u3040-\u30FF]"), ["ja"]),
    (re.compile(r"[\u4E00-\u9FFF]"), ["zh"]),
    (re.compile(r"[\uAC00-\uD7AF]"), ["ko"]),
    (re.compile(r"[\u0400-\u04FF]"), ["ru"]),
]

# Devanagari disambiguation: common Marathi-only markers vs Hindi-only markers.
# NOTE: \b cannot be used — Devanagari matras (Mn category) are not \w chars,
# so word boundaries would fall INSIDE words. Use explicit whitespace/punct
# lookarounds instead.
_EDGE_L = r"(?<!\S)"
_EDGE_R = r"(?=[\s,.\?!;:।؟'\"()\[\]]|$)"
_MR_MARKERS = re.compile(
    _EDGE_L + r"(आहे|आहेत|आहात|आहोत|तुम्ही|तू|मी|काय|आणि|नाही|म्हणजे|करतो|करते|कसे|कसा|कशी|पाहिजे|हवे|आमचा|आमची|तुमचा)" + _EDGE_R)
_HI_MARKERS = re.compile(
    _EDGE_L + r"(है|हैं|हूँ|हुँ|आप|तुम|मैं|क्या|और|नहीं|मतलब|करता|करती|कैसे|कैसा|हमारा|हमारी|तुम्हारा|चाहिए|बहुत)" + _EDGE_R)


@register("lang_detect", "langdetect")
class LangDetectProvider(BaseProvider):
    name = "langdetect"
    task = "lang_detect"
    private = True
    quality_tier = 62
    cost_tier = 0
    latency_class = "realtime"

    def _detect_sync(self, text: str) -> DetectionResult:
        text = text.strip()
        if not text:
            return DetectionResult("en", 0.0, self.name)

        # 1) script heuristics first — deterministic and reliable
        for rx, langs in SCRIPT_HINTS:
            if rx.search(text):
                if len(langs) == 1:
                    return DetectionResult(langs[0], 0.95, self.name,
                                           alternatives=[(langs[0], 0.95)])
                # Devanagari / Arabic: statistical tiebreak
                if langs == ["hi", "mr"]:
                    mr = len(_MR_MARKERS.findall(text))
                    hi = len(_HI_MARKERS.findall(text))
                    if mr > hi:
                        return DetectionResult("mr", 0.8, self.name,
                                               alternatives=[("hi", 0.6)])
                    if hi > mr:
                        return DetectionResult("hi", 0.8, self.name,
                                               alternatives=[("mr", 0.6)])
                elif langs == ["ur", "ar"]:
                    # Urdu uses extended Arabic chars like ے ں ٹ ڈ
                    if re.search(r"[ٹڈڑںہھیےپچ]", text):
                        return DetectionResult("ur", 0.85, self.name)
                    return DetectionResult("ar", 0.8, self.name)
                return DetectionResult(langs[0], 0.6, self.name)

        # 2) latin/greek/cyrillic-mixed: statistical detection
        try:
            from langdetect import detect_langs, DetectorFactory
            DetectorFactory.seed = 0
            cleaned = re.sub(r"\s+", " ", text)[:1500]
            results = detect_langs(cleaned)
            top = results[0]
            alts = [(r.lang, round(r.prob, 4)) for r in results[1:3]]
            return DetectionResult(top.lang, round(top.prob, 4), self.name, alternatives=alts)
        except Exception:
            return DetectionResult("en", 0.3, self.name)

    async def detect(self, text: str) -> DetectionResult:
        return await asyncio.to_thread(self._detect_sync, text)
