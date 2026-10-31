"""Language capability registry, lexical markers, and Hinglish token profiles."""
from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

# Supported Indian languages
INDIC_LANGUAGES: Set[str] = {
    "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur", "as", "or", "sa", "ne"
}

# Devanagari Disambiguation Lexical Markers (Marathi vs. Hindi)
# Use lookarounds instead of \b because Devanagari matras are not \w
_EDGE_L = r"(?<!\S)"
_EDGE_R = r"(?=[\s,.\?!;:।؟'\"()\[\]]|$)"

MARATHI_MARKERS_REGEX = re.compile(
    _EDGE_L + r"(आहे|आहेत|आहात|आहोत|तुम्ही|तू|मी|काय|आणि|नाही|म्हणजे|करतो|करते|कसे|कसा|कशी|पाहिजे|हवे|आमचा|आमची|तुमचा|छान|खूप|झाले|झाला|केले|होते)" + _EDGE_R
)

HINDI_MARKERS_REGEX = re.compile(
    _EDGE_L + r"(है|हैं|हूँ|हुँ|आप|तुम|मैं|क्या|और|नहीं|मतलब|करता|करती|कैसे|कैसा|हमारा|हमारी|तुम्हारा|चाहिए|बहुत|अच्छा|किया|था|थी|थे|रहा|रही|रहे)" + _EDGE_R
)

# Urdu vs Arabic Disambiguation
URDU_SPECIFIC_CHARS = re.compile(r"[ٹڈڑںہھیےپچژ]")

# Hinglish (Romanized Hindi) Common Function Words & Morphemes
HINGLISH_WORDS: Set[str] = {
    "aaj", "hum", "mein", "ke", "ki", "ka", "ko", "se", "par", "hai", "hain", "hoon", "hun",
    "kya", "kyun", "kyu", "kaise", "kaisa", "kuch", "kuchh", "karenge", "karna", "karte", "karo", "kijiye",
    "baare", "saath", "liye", "bhi", "toh", "nahi", "nahin", "na", "haan", "accha", "achha",
    "bahut", "thoda", "ek", "teen", "chaar", "paanch", "yeh", "ye", "voh", "woh", "unka", "inka",
    "apna", "apne", "mera", "meri", "mere", "tera", "teri", "tere", "aap", "tum", "bhai", "yaar",
    "kal", "abhi", "hoga", "hogi", "honge", "tha", "thi", "the", "raha", "rahi", "rahe", "dekh",
    "samajh", "bolo", "boliye", "batao", "bataye", "chahiye", "sakte", "sakti", "sakta", "suno", "sun",
}

# English Function Words Dictionary for Precision Disambiguation
ENGLISH_WORDS: Set[str] = {
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
    "meeting", "discuss", "project", "start", "join", "team", "call", "audio", "video",
    "business", "service", "model", "product", "system", "client", "platform", "engineering",
}


class LanguageProfileRegistry:
    """Provides linguistic heuristics for script and dialect disambiguation."""

    @staticmethod
    def disambiguate_devanagari(text: str) -> Tuple[str, float]:
        """Disambiguates between Hindi and Marathi in Devanagari script using lexical markers."""
        mr_matches = len(MARATHI_MARKERS_REGEX.findall(text))
        hi_matches = len(HINDI_MARKERS_REGEX.findall(text))

        if mr_matches > hi_matches:
            conf = min(0.98, 0.75 + (mr_matches * 0.08))
            return "mr", round(conf, 3)
        if hi_matches > mr_matches:
            conf = min(0.98, 0.75 + (hi_matches * 0.08))
            return "hi", round(conf, 3)

        # Inconclusive lexical evidence - return Hindi as base with moderate confidence
        return "hi", 0.55

    @staticmethod
    def disambiguate_arabic_script(text: str) -> Tuple[str, float]:
        """Disambiguates between Urdu and Arabic in Arabic-derived script."""
        if URDU_SPECIFIC_CHARS.search(text):
            return "ur", 0.92
        return "ar", 0.75

    @staticmethod
    def score_hinglish(tokens: List[str]) -> Tuple[float, float]:
        """Calculates (hinglish_ratio, english_ratio) for Latin tokens."""
        if not tokens:
            return 0.0, 0.0

        hi_count = 0
        en_count = 0
        for t in tokens:
            t_low = t.lower()
            if t_low in HINGLISH_WORDS:
                hi_count += 1
            if t_low in ENGLISH_WORDS:
                en_count += 1

        total = len(tokens)
        return round(hi_count / total, 3), round(en_count / total, 3)
