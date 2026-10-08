"""Extractive summarization provider (self-hosted, deterministic).

TF-IDF sentence scoring — a real, well-understood algorithm that runs
anywhere with zero model downloads. It only ever OUTPUTS sentences that
exist in the input, which makes it safe for the canonical-source rule:
a summary never invents semantic content.

Action-item / decision / question extraction uses multilingual cue phrases.
"""
from __future__ import annotations

import asyncio
import math
import re
from collections import Counter

from gt_ai.base import BaseProvider
from gt_ai.registry import register

_SENT_SPLIT = re.compile(r"(?<=[.!?।。؟])\s+|\n+")
_WORD = re.compile(r"[\w']+", re.UNICODE)

_STOPWORDS = set("""the a an and or but if then else of to in on for with without at by from as is are was were be been being do does did done have has had having i you he she it we they me him her us them my your his its our their this that these those there here what which who whom when where why how not no yes all any some more most other another such only own same so than too very can will just should now about into over after before during up down out off again once""".split())

# Multilingual cue phrases for structured extraction
ACTION_CUES = [
    "will", "shall", "need to", "have to", "must", "should", "action item",
    "follow up", "todo", "to-do", "task", "responsible", "owner", "by friday",
    "deadline", "assign",
    "करेंगे", "करना है", "ज़िम्मेदारी", "करेगा", "करेगी",          # hi
    "करू", "करतो", "करते", "जबाबदारी",                              # mr
    "します", "する予定", "担当", "タスク",                          # ja
    "hará", "debe", "tarea", "responsable",                          # es
    "fera", "doit", "tâche", "responsable",                          # fr
]
DECISION_CUES = [
    "decided", "decision", "agreed", "approved", "final", "we will go with",
    "concluded", "resolved",
    "तय हुआ", "निर्णय", "सहमत",                                    # hi
    "ठरले", "निर्णय", "सहमत",                                       # mr
    "決定", "合意", "承認",                                          # ja
    "decidido", "acordado", "aprobado",                              # es
    "décidé", "accord", "approuvé",                                  # fr
]
QUESTION_MARKS = ("?", "؟", "？")


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]
    merged: list[str] = []
    for p in parts:
        merged.append(p)
    return merged


def _word_freq(text: str) -> Counter:
    words = [w.lower() for w in _WORD.findall(text)]
    return Counter(w for w in words if w not in _STOPWORDS and len(w) > 1)


def _tfidf_scores(sentences: list[str]) -> list[float]:
    if not sentences:
        return []
    docs = [set(_WORD.findall(s.lower())) - _STOPWORDS for s in sentences]
    n = len(docs)
    df: Counter = Counter()
    for d in docs:
        for w in d:
            df[w] += 1
    scores = []
    for d in docs:
        if not d:
            scores.append(0.0)
            continue
        score = sum((1 + math.log(max(1, len(d)))) * math.log(n / (1 + df[w])) for w in d)
        scores.append(score / max(1, len(d)))
    return scores


@register("summarize", "extractive")
class ExtractiveSummarizer(BaseProvider):
    name = "extractive"
    task = "summarize"
    private = True
    quality_tier = 55
    cost_tier = 0
    latency_class = "realtime"

    def _summarize_sync(self, text: str, max_length: int) -> str:
        sents = _sentences(text)
        if len(sents) <= 3:
            return text.strip()
        scores = _tfidf_scores(sents)
        # position bias: earlier sentences in meetings carry context
        pos_bonus = [max(0.0, 1.0 - i / max(1, len(sents))) * 0.15 for i in range(len(sents))]
        ranked = sorted(range(len(sents)),
                        key=lambda i: scores[i] + pos_bonus[i], reverse=True)
        budget = max(2, min(len(sents), max_length // 80))
        chosen = sorted(ranked[:budget])
        return " ".join(sents[i] for i in chosen)

    async def summarize(self, text: str, instruction: str = "",
                        max_length: int = 400, lang: str = "en") -> str:
        return await asyncio.to_thread(self._summarize_sync, text, max_length)

    async def extract_structured(self, text: str, schema_hint: str = "",
                                 lang: str = "en") -> dict:
        def _do() -> dict:
            sents = _sentences(text)
            lowered = [s.lower() for s in sents]
            action_items, decisions, questions = [], [], []
            for s, low in zip(sents, lowered):
                if s.rstrip().endswith(QUESTION_MARKS):
                    questions.append(s)
                if any(cue in low for cue in ACTION_CUES) and not s.rstrip().endswith(QUESTION_MARKS):
                    action_items.append(s)
                if any(cue in low for cue in DECISION_CUES):
                    decisions.append(s)
            summary = self._summarize_sync(text, 600)
            # key terms = top tf-IDF words across the text
            freq = _word_freq(text)
            key_terms = [w for w, _ in freq.most_common(10)]
            topics = key_terms[:5]
            return {
                "summary": summary,
                "key_points": sents[:5] if len(sents) > 5 else sents,
                "decisions": decisions[:10],
                "action_items": action_items[:15],
                "unanswered_questions": questions[:10],
                "topics": topics,
                "key_terms": key_terms,
                "method": "extractive-tfidf-v1",
            }
        return await asyncio.to_thread(_do)
