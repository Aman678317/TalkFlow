"""Human review queue and feedback storage."""
from __future__ import annotations

import collections
from typing import Dict, List, Optional
from app.models.schemas import HumanReviewItem, HumanReviewSubmissionSchema, QualityDecision


class HumanReviewQueue:
    """Thread-safe human review queue for questionable or experimental translations."""

    def __init__(self, max_items: int = 500) -> None:
        self.max_items = max_items
        self._items: collections.OrderedDict[str, HumanReviewItem] = collections.OrderedDict()

    def enqueue(self, item: HumanReviewItem) -> None:
        self._items[item.evaluation_id] = item
        if len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def get(self, evaluation_id: str) -> Optional[HumanReviewItem]:
        return self._items.get(evaluation_id)

    def list_pending(self, limit: int = 50) -> List[HumanReviewItem]:
        pending = [item for item in self._items.values() if not item.reviewed]
        return pending[:limit]

    def submit_review(self, submission: HumanReviewSubmissionSchema) -> Optional[HumanReviewItem]:
        item = self._items.get(submission.evaluation_id)
        if not item:
            return None
        item.reviewed = True
        item.review_result = submission
        return item

    @property
    def pending_count(self) -> int:
        return sum(1 for item in self._items.values() if not item.reviewed)


review_queue = HumanReviewQueue()

