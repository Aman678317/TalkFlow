"""Per-speaker stateful language tracking with hysteresis and sliding window history."""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("sessions.speaker_context")


class UtteranceHistoryEntry:
    """Historical record of an utterance and its language detection."""

    def __init__(self, utterance_id: str, language: str, confidence: float, is_multilingual: bool, timestamp: float):
        self.utterance_id = utterance_id
        self.language = language
        self.confidence = confidence
        self.is_multilingual = is_multilingual
        self.timestamp = timestamp


class SpeakerLanguageContext:
    """Stateful context for a single speaker tracking dominant language and hysteresis."""

    def __init__(
        self,
        speaker_id: str,
        window_size: int = 10,
        hysteresis_margin: float = 0.15,
        switch_threshold_count: int = 2,
    ):
        self.speaker_id = speaker_id
        self.window_size = window_size
        self.hysteresis_margin = hysteresis_margin
        self.switch_threshold_count = switch_threshold_count

        self.history: Deque[UtteranceHistoryEntry] = deque(maxlen=window_size)
        self.dominant_language: str = "und"
        self.consecutive_switches: int = 0
        self.candidate_switch_language: Optional[str] = None
        self.last_active_time: float = time.time()

    def record_utterance(
        self,
        utterance_id: str,
        detected_language: str,
        confidence: float,
        is_multilingual: bool = False,
    ) -> str:
        """Records an utterance and updates speaker's dominant language using hysteresis."""
        self.last_active_time = time.time()

        if detected_language == "und" or confidence < 0.40:
            return self.dominant_language

        entry = UtteranceHistoryEntry(
            utterance_id=utterance_id,
            language=detected_language,
            confidence=confidence,
            is_multilingual=is_multilingual,
            timestamp=self.last_active_time,
        )
        self.history.append(entry)

        # Initial cold start
        if self.dominant_language == "und":
            self.dominant_language = detected_language
            log.info(f"Speaker '{self.speaker_id}' initialized dominant language to '{detected_language}' ({confidence:.2f})")
            return self.dominant_language

        # If detected language matches dominant language, reset pending switches
        if detected_language == self.dominant_language:
            self.consecutive_switches = 0
            self.candidate_switch_language = None
            return self.dominant_language

        # Hysteresis check: Language changed
        # Avoid switching on isolated loanword unless consecutive utterances confirm switch
        if detected_language == self.candidate_switch_language:
            self.consecutive_switches += 1
        else:
            self.candidate_switch_language = detected_language
            self.consecutive_switches = 1

        # Check if consecutive utterances reached switch threshold
        if self.consecutive_switches >= self.switch_threshold_count and confidence >= 0.65:
            old_lang = self.dominant_language
            self.dominant_language = detected_language
            self.consecutive_switches = 0
            self.candidate_switch_language = None
            log.info(f"Speaker '{self.speaker_id}' switched dominant language: {old_lang} -> {detected_language}")

        return self.dominant_language

    def get_language_frequencies(self) -> Dict[str, float]:
        """Calculates proportion of languages spoken by this speaker in recent history."""
        if not self.history:
            return {}
        counts: Dict[str, int] = {}
        for h in self.history:
            counts[h.language] = counts.get(h.language, 0) + 1
        total = len(self.history)
        return {l: round(c / total, 3) for l, c in sorted(counts.items(), key=lambda x: x[1], reverse=True)}

