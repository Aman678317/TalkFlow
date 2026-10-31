"""Idempotency cache and in-flight deduplication for QA assessments."""
from __future__ import annotations

import collections
from typing import Dict, Optional
from app.models.quality_report import QualityReport


class IdempotencyCache:
    """Thread-safe LRU cache storing recent QualityReport evaluations by candidate hash."""

    def __init__(self, capacity: int = 1000) -> None:
        self.capacity = capacity
        self._cache: collections.OrderedDict[str, QualityReport] = collections.OrderedDict()

    def get(self, candidate_hash: str) -> Optional[QualityReport]:
        if candidate_hash in self._cache:
            self._cache.move_to_end(candidate_hash)
            return self._cache[candidate_hash]
        return None

    def put(self, candidate_hash: str, report: QualityReport) -> None:
        self._cache[candidate_hash] = report
        self._cache.move_to_end(candidate_hash)
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)


idempotency_cache = IdempotencyCache()

