"""Confidence evaluation and anti-hallucination filtering."""
from __future__ import annotations

import re
from typing import List, Tuple
from app.models.schemas import STTResult


class ConfidenceEvaluator:
    """Evaluates transcription confidence and detects Whisper acoustic hallucinations."""

    KNOWN_HALLUCINATIONS = {
        "thank you for watching",
        "please subscribe",
        "subscribe to my channel",
        "thanks for watching",
        "see you next time",
        "subtitles by",
        "subtitles created by",
    }

    def __init__(
        self,
        no_speech_threshold: float = 0.60,
        min_confidence: float = 0.25,
        max_repetition_count: int = 3,
        suppress_silence_loops: bool = True,
    ):
        self.no_speech_threshold = no_speech_threshold
        self.min_confidence = min_confidence
        self.max_repetition_count = max_repetition_count
        self.suppress_silence_loops = suppress_silence_loops

    def evaluate(self, result: STTResult) -> Tuple[str, List[str]]:
        """Filters hallucinations and returns (cleaned_text, quality_flags)."""
        flags: List[str] = []
        raw_text = result.text.strip()

        if not raw_text:
            return "", flags

        # 1. High No-Speech Probability Check (only suppress if no speech content was recognized)
        if result.no_speech_prob >= self.no_speech_threshold and (not raw_text or len(raw_text.split()) < 3 or result.confidence < 0.15):
            flags.append("high_no_speech_prob")
            if self.suppress_silence_loops:
                return "", flags

        # 2. Known Whisper Hallucination Phrases on Quiet / Noisy Audio
        lower_text = raw_text.lower().strip(".,!?:; ")
        for phrase in self.KNOWN_HALLUCINATIONS:
            if phrase in lower_text:
                flags.append("known_hallucination_pattern")
                if result.no_speech_prob > 0.35 or result.confidence < 0.5:
                    return "", flags

        # 3. Repetition Loop Detection (e.g., "word word word word")
        words = raw_text.split()
        if len(words) >= 4:
            # Check for identical consecutive words
            max_consecutive = 1
            cur_consecutive = 1
            for i in range(1, len(words)):
                if words[i].lower() == words[i - 1].lower():
                    cur_consecutive += 1
                    max_consecutive = max(max_consecutive, cur_consecutive)
                else:
                    cur_consecutive = 1

            if max_consecutive >= self.max_repetition_count:
                flags.append("repetition_loop_detected")
                # Collapse excessive consecutive repetitions
                collapsed = []
                last_w = None
                rep_c = 0
                for w in words:
                    if w.lower() == last_w:
                        rep_c += 1
                        if rep_c < self.max_repetition_count:
                            collapsed.append(w)
                    else:
                        last_w = w.lower()
                        rep_c = 1
                        collapsed.append(w)
                raw_text = " ".join(collapsed)

        # 4. Low Confidence Warning
        if result.confidence < self.min_confidence:
            flags.append("low_confidence")

        return raw_text, flags

