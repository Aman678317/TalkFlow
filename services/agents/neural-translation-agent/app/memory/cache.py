"""In-memory bounded LRU cache for translated segments."""
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple
from app.models.schemas import TranslationResponseSchema


class SegmentTranslationCache:
    """Caches finalized translations for deduplication and rapid replay across listeners."""

    def __init__(self, capacity: int = 2000, ttl_seconds: float = 300.0) -> None:
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        # key: (segment_id, target_lang) -> (entry, timestamp)
        self._cache: Dict[Tuple[str, str], Tuple[TranslationResponseSchema, float]] = {}

    def get(self, segment_id: str, target_lang: str) -> Optional[TranslationResponseSchema]:
        key = (segment_id, target_lang)
        entry = self._cache.get(key)
        if entry is None:
            return None
        res, ts = entry
        if time.time() - ts > self.ttl_seconds:
            self._cache.pop(key, None)
            return None
        return res

    def put(self, segment_id: str, target_lang: str, result: TranslationResponseSchema) -> None:
        if len(self._cache) >= self.capacity:
            # Evict oldest entry
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            self._cache.pop(oldest_key, None)
        self._cache[(segment_id, target_lang)] = (result, time.time())

    def clear(self) -> None:
        self._cache.clear()


translation_cache = SegmentTranslationCache()

