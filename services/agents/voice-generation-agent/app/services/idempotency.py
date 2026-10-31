"""Idempotency cache for Agent 06 Text-to-Speech synthesis."""
from __future__ import annotations

import collections
import hashlib
import time
from typing import Any, Dict, Optional, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)


class IdempotencyManager:
    """Caches synthesized audio results to prevent redundant processing."""

    def __init__(self, max_size: int = 500, ttl_seconds: float = 300.0) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        # key -> (result, timestamp)
        self._cache: collections.OrderedDict[str, Tuple[Any, float]] = collections.OrderedDict()

    def _make_key(
        self,
        tenant_id: str,
        conversation_id: str,
        segment_id: str,
        translation_id: str,
        target_language: str,
        text: str,
    ) -> str:
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return f"{tenant_id}:{conversation_id}:{segment_id}:{translation_id}:{target_language}:{text_hash}"

    def get(
        self,
        tenant_id: str,
        conversation_id: str,
        segment_id: str,
        translation_id: str,
        target_language: str,
        text: str,
    ) -> Optional[Any]:
        """Lookup cached result."""
        key = self._make_key(
            tenant_id, conversation_id, segment_id, translation_id, target_language, text
        )
        if key in self._cache:
            res, ts = self._cache[key]
            if time.time() - ts < self.ttl_seconds:
                self._cache.move_to_end(key)
                logger.debug("Idempotency cache hit", extra={"key": key})
                return res
            else:
                del self._cache[key]
        return None

    def put(
        self,
        tenant_id: str,
        conversation_id: str,
        segment_id: str,
        translation_id: str,
        target_language: str,
        text: str,
        result: Any,
    ) -> None:
        """Store result in cache."""
        key = self._make_key(
            tenant_id, conversation_id, segment_id, translation_id, target_language, text
        )
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (result, time.time())

