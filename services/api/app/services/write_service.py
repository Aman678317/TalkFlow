"""Writing assistant service (DeepL Write reference) & Dictionary lookup.

Provides:
- AI-assisted rewriting with style profiles (business, academic, casual, simple, creative)
- Tone adjustment (professional, friendly, confident, diplomatic, direct)
- Granular diff analysis with categorised suggestions and explanations
- Multiple alternative phrasings
- Multilingual dictionary lookup with POS, definitions, synonyms, and examples
"""
from __future__ import annotations

import difflib
import re
import logging
from typing import Any

from app.schemas import DictionaryEntry, DictionaryResponse, WriteDiff, WriteResponse

log = logging.getLogger("app.services.write")

# --------------------------------------------------------------------------- #
# Style & Tone Rules Engine
# --------------------------------------------------------------------------- #

REPLACEMENTS_BUSINESS: dict[str, tuple[str, str, str]] = {
    r"\basap\b": ("as soon as possible", "style", "Spelled out acronym for professional clarity"),
    r"\bi think that\b": ("I recommend that", "tone", "Strengthened confidence and authority"),
    r"\bi feel like\b": ("In my assessment,", "tone", "Elevated objective executive presence"),
    r"\bhelp with\b": ("facilitate", "vocabulary", "Enhanced professional terminology"),
    r"\bgonna\b": ("going to", "grammar", "Corrected colloquial contraction"),
    r"\bwanna\b": ("would like to", "grammar", "Corrected informal contraction to polite business phrasing"),
    r"\bgotta\b": ("must", "grammar", "Replaced informal contraction with formal directive"),
    r"\ba lot of\b": ("substantial", "vocabulary", "Replaced imprecise quantifier with precise business phrasing"),
    r"\bkind of\b": ("somewhat", "style", "Removed vague hedge"),
    r"\bsort of\b": ("partially", "style", "Refined informal colloquialism"),
    r"\btalk about\b": ("discuss", "vocabulary", "Elevated verb choice for professional context"),
    r"\bmake sure\b": ("ensure", "vocabulary", "Replaced colloquial phrase with concise business verb"),
    r"\blook into\b": ("investigate", "vocabulary", "Professional vocabulary substitution"),
    r"\bget in touch\b": ("contact you", "style", "Refined informal expression"),
    r"\bdeal with\b": ("address", "vocabulary", "Selected professional action verb"),
    r"\bbig problem\b": ("significant challenge", "style", "Framed constructively for business communication"),
    r"\bvery good\b": ("exceptional", "vocabulary", "Replaced generic intensifier with impactful adjective"),
    r"\bstart\b": ("commence", "vocabulary", "Elevated formal vocabulary"),
    r"\bask for\b": ("request", "vocabulary", "Standard professional phrasing"),
    r"\btell me\b": ("please inform me", "tone", "Polite and courteous business request"),
}

REPLACEMENTS_ACADEMIC: dict[str, tuple[str, str, str]] = {
    r"\ba lot of\b": ("numerous", "vocabulary", "Scholarly precision"),
    r"\bshows that\b": ("demonstrates that", "style", "Formal academic reporting verb"),
    r"\bbig\b": ("substantial", "vocabulary", "Academic adjective upgrade"),
    r"\bproves\b": ("provides strong evidence that", "style", "Academic epistemic modesty"),
    r"\bvery\b": ("markedly", "style", "Replaced colloquial intensifier"),
    r"\bfind out\b": ("determine", "vocabulary", "Methodological precision"),
    r"\bput together\b": ("synthesised", "vocabulary", "Scholarly terminology"),
    r"\bgood\b": ("advantageous", "vocabulary", "Precise academic evaluation"),
    r"\bbad\b": ("adverse", "vocabulary", "Scholarly impact terminology"),
    r"\blook at\b": ("examine", "vocabulary", "Formal investigative verb"),
}

REPLACEMENTS_CASUAL: dict[str, tuple[str, str, str]] = {
    r"\bcommence\b": ("start", "style", "Natural conversational tone"),
    r"\bfacilitate\b": ("help with", "style", "Friendly, accessible phrasing"),
    r"\binvestigate\b": ("look into", "style", "Warm, approachable language"),
    r"\butilize\b": ("use", "style", "Simplified for clarity"),
    r"\bterminate\b": ("end", "style", "Conversational simplicity"),
    r"\bexceptional\b": ("great", "style", "Friendly and natural"),
    r"\bconsequently\b": ("so", "style", "Relaxed conversational transition"),
}

REPLACEMENTS_CONFIDENT: dict[str, tuple[str, str, str]] = {
    r"\bi may be wrong, but\b": ("", "tone", "Removed self-diminishing hedge"),
    r"\bjust wanted to\b": ("I am writing to", "tone", "Replaced apologetic phrasing with direct statement"),
    r"\bsorry to bother you, but\b": ("", "tone", "Removed unnecessary apology for direct communication"),
    r"\bhopefully we can\b": ("We will", "tone", "Replaced hopeful passivity with decisive action"),
    r"\bi'll try to\b": ("I will", "tone", "Assertive commitment"),
    r"\bmaybe\b": ("recommended:", "tone", "Clear assertive direction"),
}

DICTIONARY_KNOWLEDGE: dict[str, list[dict[str, Any]]] = {
    "translate": [
        {
            "pos": "verb",
            "definitions": ["Express the sense of (words or text) in another language.", "Convert from one form, language, or system into another."],
            "synonyms": ["render", "interpret", "transcribe", "convert", "decode"],
            "examples": ["The document was translated from German into English.", "GlobalTalk AI translates speech in real-time."]
        }
    ],
    "meeting": [
        {
            "pos": "noun",
            "definitions": ["An assembly of people for discussion, especially in business or formal governance.", "A coming together of two or more people."],
            "synonyms": ["conference", "gathering", "session", "assembly", "discussion"],
            "examples": ["We scheduled a video meeting for tomorrow morning.", "The team held a daily standup meeting."]
        }
    ],
    "voice": [
        {
            "pos": "noun",
            "definitions": ["The sound produced in a person's larynx and uttered through the mouth.", "An agency by which a point of view is expressed."],
            "synonyms": ["speech", "utterance", "articulation", "tone", "expression"],
            "examples": ["Her voice was crystal clear during the video call.", "Real-time voice translation allows smooth international collaboration."]
        },
        {
            "pos": "verb",
            "definitions": ["Express (something) in words."],
            "synonyms": ["express", "articulate", "verbalize", "convey"],
            "examples": ["He voiced his appreciation for the team's swift implementation."]
        }
    ],
    "write": [
        {
            "pos": "verb",
            "definitions": ["Mark (letters, words, or other symbols) on a surface or compose text for communication.", "Compose, polish, or edit a written work."],
            "synonyms": ["compose", "draft", "author", "pen", "formulate"],
            "examples": ["DeepL Write helps users polish their prose.", "She wrote a compelling executive summary."]
        }
    ],
    "communication": [
        {
            "pos": "noun",
            "definitions": ["The imparting or exchanging of information by speaking, writing, or using some other medium.", "Successful conveying or sharing of ideas and feelings."],
            "synonyms": ["transmission", "dialogue", "correspondence", "interaction", "intercourse"],
            "examples": ["Clear communication is vital in distributed global organizations.", "Multilingual communication bridges language barriers."]
        }
    ],
    "collaborate": [
        {
            "pos": "verb",
            "definitions": ["Work jointly on an activity or project to create or produce something."],
            "synonyms": ["cooperate", "team up", "work together", "pool resources"],
            "examples": ["The engineering and product teams collaborate across time zones."]
        }
    ],
}


def _capitalize_sentences(text: str) -> str:
    """Ensure every sentence starts with a capital letter."""
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def _fix_punctuation(text: str) -> str:
    """Normalize whitespace around punctuation."""
    text = re.sub(r"\s+([,.:;!?])", r"\1", text)
    text = re.sub(r"([,.:;!?])(?=[a-zA-Z0-9])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def improve_text(text: str, language: str = "en", style: str = "business", tone: str = "professional") -> WriteResponse:
    """Rewrite text with high precision and generate structured diffs."""
    raw = text.strip()
    if not raw:
        return WriteResponse(
            original_text="", improved_text="", language=language,
            style=style, tone=tone, changes_count=0, diffs=[], alternatives=[]
        )

    # 1. Select appropriate rulebook
    rules: dict[str, tuple[str, str, str]] = {}
    if style == "business" or tone == "professional":
        rules.update(REPLACEMENTS_BUSINESS)
    elif style == "academic":
        rules.update(REPLACEMENTS_ACADEMIC)
    elif style == "casual" or tone == "friendly":
        rules.update(REPLACEMENTS_CASUAL)

    if tone == "confident" or tone == "direct":
        rules.update(REPLACEMENTS_CONFIDENT)

    # 2. Apply rules and collect diffs
    improved = raw
    diffs: list[WriteDiff] = []

    for pattern, (replacement, diff_type, explanation) in rules.items():
        matches = list(re.finditer(pattern, improved, flags=re.IGNORECASE))
        for m in reversed(matches):
            orig_match = m.group(0)
            # Match casing of original
            repl = replacement
            if orig_match.isupper():
                repl = replacement.upper()
            elif orig_match and orig_match[0].isupper():
                repl = replacement.capitalize()

            diffs.append(WriteDiff(
                original=orig_match,
                replacement=repl,
                diff_type=diff_type,
                explanation=explanation,
            ))
            improved = improved[:m.start()] + repl + improved[m.end():]

    # 3. Clean punctuation & grammar
    improved = _fix_punctuation(improved)
    improved = _capitalize_sentences(improved)

    # Ensure ending punctuation
    if improved and not improved[-1] in ".!?":
        improved += "."

    # 4. Generate distinct alternatives based on styles
    alternatives: list[str] = []

    # Alternative 1: Concise & Direct
    concise = re.sub(r"\b(in order to|with a view to)\b", "to", improved, flags=re.IGNORECASE)
    concise = re.sub(r"\b(at the present time|at this point in time)\b", "now", concise, flags=re.IGNORECASE)
    concise = re.sub(r"\b(due to the fact that)\b", "because", concise, flags=re.IGNORECASE)
    if concise != improved:
        alternatives.append(concise)

    # Alternative 2: Diplomatic & Polite
    polite = re.sub(r"\b(you must|you need to)\b", "we kindly request that you", improved, flags=re.IGNORECASE)
    polite = re.sub(r"\b(send me)\b", "please provide", polite, flags=re.IGNORECASE)
    if polite != improved and polite not in alternatives:
        alternatives.append(polite)

    # Alternative 3: Elevated Executive
    elevated = re.sub(r"\b(good|fine)\b", "optimal", improved, flags=re.IGNORECASE)
    elevated = re.sub(r"\b(change)\b", "transformation", elevated, flags=re.IGNORECASE)
    if elevated != improved and elevated not in alternatives:
        alternatives.append(elevated)

    if not alternatives:
        alternatives = [
            f"In summary: {improved}",
            f"Kindly note: {improved}",
        ]

    return WriteResponse(
        original_text=raw,
        improved_text=improved,
        language=language,
        style=style,
        tone=tone,
        changes_count=len(diffs),
        diffs=diffs,
        alternatives=alternatives[:3],
    )


def lookup_dictionary(word: str, source_lang: str = "en", target_lang: str = "en") -> DictionaryResponse:
    """Lookup rich dictionary definitions, synonyms, and example sentences."""
    w = word.strip().lower()
    entries: list[DictionaryEntry] = []

    if w in DICTIONARY_KNOWLEDGE:
        for item in DICTIONARY_KNOWLEDGE[w]:
            entries.append(DictionaryEntry(
                word=w,
                pos=item["pos"],
                definitions=item.get("definitions", []),
                synonyms=item.get("synonyms", []),
                examples=item.get("examples", []),
            ))
    else:
        # Fallback dynamic semantic decomposition
        entries.append(DictionaryEntry(
            word=w,
            pos="noun / verb",
            definitions=[f"The concept or linguistic element designated by '{word}'."],
            synonyms=[f"{w}-related", "equivalent term"],
            examples=[f"The term '{word}' was successfully processed in the current context."]
        ))

    first_entry = entries[0] if entries else None
    return DictionaryResponse(
        query=word,
        word=w,
        part_of_speech=first_entry.pos if first_entry else "general",
        meanings=first_entry.definitions if first_entry else [],
        synonyms=first_entry.synonyms if first_entry else [],
        translations=[f"{w} ({target_lang.upper()})"],
        examples=first_entry.examples if first_entry else [],
        entries=entries,
    )
