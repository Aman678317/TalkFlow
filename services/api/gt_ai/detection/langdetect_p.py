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


# High-frequency function words and markers for Latin-script languages
LATIN_LANG_WORDS: dict[str, set[str]] = {
    "en": {
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for", "not",
        "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from",
        "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would",
        "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which",
        "go", "me", "when", "make", "can", "like", "time", "no", "just", "him", "know",
        "take", "people", "into", "year", "your", "good", "some", "could", "them", "see",
        "other", "than", "then", "now", "look", "only", "come", "its", "over", "think",
        "also", "back", "after", "use", "two", "how", "our", "work", "first", "well", "way",
        "even", "new", "want", "because", "any", "these", "give", "day", "most", "us", "is",
        "am", "are", "was", "were", "been", "has", "had", "name", "hello", "welcome", "please",
    },
    "es": {
        "el", "la", "de", "que", "y", "en", "un", "ser", "se", "no", "haber", "por", "con",
        "su", "para", "como", "estar", "tener", "le", "lo", "todo", "pero", "mas", "hacer",
        "o", "poder", "decir", "este", "ir", "otro", "ese", "si", "me", "ya", "ver",
        "porque", "dar", "cuando", "muy", "sin", "vez", "mucho", "saber", "sobre", "mi",
        "nombre", "es", "hola", "gracias", "buenos", "dias",
    },
    "de": {
        "der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich", "des", "auf",
        "für", "ist", "im", "dem", "nicht", "ein", "eine", "als", "auch", "es", "an",
        "werden", "aus", "er", "hat", "dass", "sie", "nach", "wird", "bei", "einer", "um",
        "am", "sind", "noch", "wie", "einem", "über", "einen", "so", "zum", "war", "haben",
        "nur", "oder", "aber", "vor", "zur", "bis", "mein", "meine", "name", "heisse",
        "hallo", "guten", "morgen", "danke",
    },
    "fr": {
        "de", "la", "le", "et", "les", "des", "en", "un", "du", "une", "que", "est", "pour",
        "qui", "dans", "a", "par", "plus", "pas", "au", "sur", "ne", "ce", "avec", "se",
        "sont", "ou", "comme", "mais", "nous", "sa", "vous", "tout", "faire", "son", "il",
        "elle", "je", "mon", "ma", "mes", "nom", "appelle", "bonjour", "merci", "salut",
    },
    "it": {
        "di", "e", "il", "la", "che", "in", "un", "per", "una", "non", "del", "dei", "a",
        "al", "si", "da", "della", "con", "ha", "ed", "delle", "sono", "gli", "nel", "le",
        "mio", "mia", "nome", "chiamo", "ciao", "grazie",
    },
    "pt": {
        "de", "a", "o", "que", "e", "do", "da", "em", "um", "para", "com", "não", "uma",
        "os", "no", "se", "na", "por", "mais", "as", "dos", "como", "mas", "foi", "ao",
        "ele", "das", "tem", "à", "seu", "sua", "ou", "quando", "muito", "meu", "minha",
        "nome", "ola", "obrigado",
    },
}


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

        # 1) script heuristics first — deterministic and reliable for non-Latin scripts
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

        # 2) Latin-script function word heuristic (high precision for short texts with proper names)
        tokens = [w.lower() for w in re.findall(r"\b[a-zA-Záéíóúüñßäöüàâçèêëîïôûùÿæœ']+\b", text)]
        if tokens:
            scores: dict[str, int] = {}
            for lang, word_set in LATIN_LANG_WORDS.items():
                count = sum(1 for t in tokens if t in word_set)
                if count > 0:
                    scores[lang] = count

            if scores:
                best_lang, best_count = max(scores.items(), key=lambda kv: kv[1])
                # If at least 2 function words match, or >= half the words in short input
                if best_count >= 2 or (len(tokens) <= 3 and best_count >= 1):
                    confidence = min(0.99, 0.70 + (best_count / max(len(tokens), 1)) * 0.3)
                    alts = [(l, round(c / len(tokens), 3)) for l, c in sorted(scores.items(), key=lambda x: -x[1]) if l != best_lang]
                    return DetectionResult(best_lang, round(confidence, 4), self.name, alternatives=alts)

        # 3) Statistical detection fallback via langdetect library
        try:
            from langdetect import detect_langs, DetectorFactory
            DetectorFactory.seed = 0
            cleaned = re.sub(r"\s+", " ", text)[:1500]
            results = detect_langs(cleaned)
            top = results[0]
            alts = [(r.lang, round(r.prob, 4)) for r in results[1:3]]

            # Guard against common short text misclassifications (tl, so, af when mostly ASCII words)
            if top.lang in ("tl", "so", "af", "id", "ms") and len(tokens) <= 8:
                # If there are common English tokens like 'is', 'my', 'the', 'and', 'it', 'to'
                if any(t in LATIN_LANG_WORDS["en"] for t in tokens):
                    return DetectionResult("en", 0.85, self.name, alternatives=[(top.lang, top.prob)])

            return DetectionResult(top.lang, round(top.prob, 4), self.name, alternatives=alts)
        except Exception:
            return DetectionResult("en", 0.3, self.name)

    async def detect(self, text: str) -> DetectionResult:
        return await asyncio.to_thread(self._detect_sync, text)
