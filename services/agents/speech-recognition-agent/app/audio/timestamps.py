"""Timestamp conversion utilities between segment-relative and conversation timeline."""
from __future__ import annotations

from typing import Any, Dict, List
from app.models.schemas import SegmentTiming, WordTimestamp


class TimelineConverter:
    """Converts model-relative seconds to conversation-relative milliseconds."""

    @staticmethod
    def align_segment_timings(
        segments: List[SegmentTiming],
        base_start_ms: int,
    ) -> List[SegmentTiming]:
        """Offsets segment and word timings by the chunk base_start_ms."""
        aligned_segments: List[SegmentTiming] = []
        for seg in segments:
            aligned_words: List[WordTimestamp] = []
            for w in seg.words:
                aligned_words.append(
                    WordTimestamp(
                        word=w.word,
                        start=round((base_start_ms / 1000.0) + w.start, 3),
                        end=round((base_start_ms / 1000.0) + w.end, 3),
                        confidence=w.confidence,
                    )
                )

            aligned_segments.append(
                SegmentTiming(
                    start_ms=base_start_ms + seg.start_ms,
                    end_ms=base_start_ms + seg.end_ms,
                    text=seg.text,
                    words=aligned_words,
                )
            )
        return aligned_segments

