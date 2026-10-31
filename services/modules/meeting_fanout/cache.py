"""Translation & Audio Artifact Cache Service (Service F).

Implements Section 5 & 6 idempotency and deduplication key caching for TalkFlow Fan-Out.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict, Optional, Tuple
from modules.meeting_fanout.models import TranslationArtifact, TTSArtifact

logger = logging.getLogger("talkflow.modules.meeting_fanout.cache")


class TranslationArtifactCache:
    """High-throughput in-memory and durable cache for translation and TTS artifacts."""

    def __init__(self, max_entries: int = 50000) -> None:
        self.max_entries = max_entries
        # idempotency_key -> TranslationArtifact
        self._translation_cache: Dict[str, TranslationArtifact] = {}
        # tts_generation_key -> TTSArtifact
        self._tts_cache: Dict[str, TTSArtifact] = {}
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    @staticmethod
    def build_translation_idempotency_key(
        room_id: str,
        source_track_id: str,
        utterance_id: str,
        source_language: str,
        target_language: str,
        translation_model_version: str = "1.0",
        glossary_version: str = "1.0",
    ) -> str:
        """Constructs canonical idempotency key as defined in Section 5."""
        raw = f"{room_id}:{source_track_id}:{utterance_id}:{source_language.lower().strip()}:{target_language.lower().strip()}:{translation_model_version}:{glossary_version}"
        return raw

    @staticmethod
    def build_tts_generation_key(
        utterance_id: str,
        target_language: str,
        source_speaker_id: str,
        voice_profile_id: str = "default",
        tts_model_version: str = "edge_tts_1.0",
        speech_style: str = "natural",
    ) -> str:
        """Constructs canonical TTS generation key as defined in Section 6."""
        raw = f"{utterance_id}:{target_language.lower().strip()}:{source_speaker_id}:{voice_profile_id}:{tts_model_version}:{speech_style}"
        return raw

    def get_translation(self, idempotency_key: str) -> Optional[TranslationArtifact]:
        """Lookup translation artifact by idempotency key."""
        artifact = self._translation_cache.get(idempotency_key)
        if artifact:
            self.cache_hits += 1
            logger.debug(f"[CACHE HIT] Translation for key '{idempotency_key}'")
            return artifact
        self.cache_misses += 1
        return None

    def store_translation(self, artifact: TranslationArtifact) -> None:
        """Store translation artifact in cache."""
        if len(self._translation_cache) >= self.max_entries:
            # Simple eviction of oldest item
            first_key = next(iter(self._translation_cache))
            del self._translation_cache[first_key]
        self._translation_cache[artifact.idempotency_key] = artifact

    def get_tts(self, tts_generation_key: str) -> Optional[TTSArtifact]:
        """Lookup TTS audio artifact by generation key."""
        artifact = self._tts_cache.get(tts_generation_key)
        if artifact:
            self.cache_hits += 1
            logger.debug(f"[CACHE HIT] TTS for key '{tts_generation_key}'")
            return artifact
        self.cache_misses += 1
        return None

    def store_tts(self, artifact: TTSArtifact) -> None:
        """Store TTS audio artifact in cache."""
        if len(self._tts_cache) >= self.max_entries:
            first_key = next(iter(self._tts_cache))
            del self._tts_cache[first_key]
        self._tts_cache[artifact.tts_generation_key] = artifact

    def get_stats(self) -> Dict[str, float]:
        """Cache hit rate and statistics."""
        total = self.cache_hits + self.cache_misses
        rate = (self.cache_hits / total) if total > 0 else 0.0
        return {
            "cached_translations": len(self._translation_cache),
            "cached_tts_artifacts": len(self._tts_cache),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": round(rate, 3),
        }

    def clear(self) -> None:
        """Flushes cache."""
        self._translation_cache.clear()
        self._tts_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0


# Global Cache Instance
fanout_cache = TranslationArtifactCache()

