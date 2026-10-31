"""Bounded context window management for context-aware translation."""
from __future__ import annotations

from typing import List


class ContextManager:
    """Maintains bounded conversation history to aid MT disambiguation without history explosion."""

    def __init__(self, max_context_chars: int = 250) -> None:
        self.max_context_chars = max_context_chars

    def build_bounded_context(self, history: List[str]) -> List[str]:
        """Returns the most recent previous sentences capped to max_context_chars."""
        if not history:
            return []

        selected: List[str] = []
        total_len = 0

        # Traverse backwards from most recent
        for turn in reversed(history):
            cleaned = turn.strip()
            if not cleaned:
                continue
            if total_len + len(cleaned) > self.max_context_chars:
                remaining = self.max_context_chars - total_len
                if remaining > 20:
                    selected.insert(0, cleaned[-remaining:])
                break
            selected.insert(0, cleaned)
            total_len += len(cleaned)

        return selected


context_manager = ContextManager()

