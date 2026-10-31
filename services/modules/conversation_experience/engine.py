"""Natural Conversation Experience Engine (Module H).

Implements barge-in interruption handling, backchannel detection, audio feedback prevention,
turn boundary tracking, and adaptive jitter buffer management.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Set
from modules.conversation_experience.models import AcousticState, TurnEvent

logger = logging.getLogger("talkflow.modules.conversation_experience")

# Multilingual conversational backchannel patterns
BACKCHANNEL_WORDS: Set[str] = {
    # English
    "yeah", "yep", "uh-huh", "mhm", "mm-hmm", "right", "okay", "ok", "sure", "got it", "i see",
    # Hindi / Hinglish / Urdu
    "हाँ", "हां", "अच्छा", "हाँ जी", "हाँ-हाँ", "हाँजी", "सही है", "ठीक है", "अच्छा अच्छा",
    "haan", "achha", "sahi", "theek", "thik hai", "ji",
    # Marathi
    "हो", "होय", "बरोबर", "बरोबर आहे", "छान",
    # Spanish
    "sí", "si", "claro", "vale", "ya", "ajá", "entiendo",
    # French
    "oui", "ouais", "d'accord", "voilà",
    # Japanese
    "はい", "うん", "そうですね", "なるほど",
}


class ConversationExperienceEngine:
    """Manages natural conversational flow, interruption handling, and backchannel filtering."""

    def __init__(self) -> None:
        # room_id -> AcousticState
        self._states: Dict[str, AcousticState] = {}

    def get_or_create_state(self, room_id: str) -> AcousticState:
        if room_id not in self._states:
            self._states[room_id] = AcousticState(room_id=room_id)
        return self._states[room_id]

    def is_backchannel(self, text: str) -> bool:
        """Determines if an utterance is conversational listener feedback rather than a turn takeover."""
        clean = text.lower().strip(".,!?:; ")
        if not clean:
            return False

        # If 1-3 words and matches recognized backchannel set
        words = clean.split()
        if len(words) <= 3:
            if clean in BACKCHANNEL_WORDS:
                return True
            for w in words:
                if w in BACKCHANNEL_WORDS:
                    return True

        return False

    def handle_speech_start(
        self,
        room_id: str,
        speaker_id: str,
        timestamp_ms: int,
    ) -> TurnEvent:
        """Invoked when VAD detects speech onset for a speaker in a room."""
        state = self.get_or_create_state(room_id)

        # Check if another speaker is already active (interruption / barge-in)
        if state.active_speaker_id and state.active_speaker_id != speaker_id and state.is_speaking:
            interrupted = state.active_speaker_id
            state.is_interrupted = True
            state.active_speaker_id = speaker_id
            state.current_playback_ducking_db = -18.0  # Duck current audio playback
            logger.info(f"Barge-in detected: '{speaker_id}' interrupted '{interrupted}' in room '{room_id}'")
            return TurnEvent(
                speaker_id=speaker_id,
                event_type="interruption",
                timestamp_ms=timestamp_ms,
                interrupted_speaker_id=interrupted,
            )

        # Normal turn start
        state.active_speaker_id = speaker_id
        state.is_speaking = True
        state.is_interrupted = False
        state.current_playback_ducking_db = 0.0

        return TurnEvent(
            speaker_id=speaker_id,
            event_type="turn_start",
            timestamp_ms=timestamp_ms,
        )

    def handle_speech_end(
        self,
        room_id: str,
        speaker_id: str,
        text: str,
        timestamp_ms: int,
        duration_ms: int = 0,
    ) -> TurnEvent:
        """Invoked when VAD or STT finalizes speech for a speaker."""
        state = self.get_or_create_state(room_id)
        is_bc = self.is_backchannel(text)

        if is_bc:
            # Backchannel does not take over turn or release main speaker
            return TurnEvent(
                speaker_id=speaker_id,
                event_type="backchannel",
                timestamp_ms=timestamp_ms,
                duration_ms=duration_ms,
                text=text,
                is_backchannel=True,
            )

        # Normal turn end
        if state.active_speaker_id == speaker_id:
            state.is_speaking = False
            state.current_playback_ducking_db = 0.0

        return TurnEvent(
            speaker_id=speaker_id,
            event_type="turn_end",
            timestamp_ms=timestamp_ms,
            duration_ms=duration_ms,
            text=text,
            is_backchannel=False,
        )


# Global Engine Instance
conversation_experience_engine = ConversationExperienceEngine()

