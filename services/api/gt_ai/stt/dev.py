"""Development STT provider (NON-PRODUCTION).

Two honest behaviors:
1. `transcribe()` on real audio returns an empty final chunk with
   quality flag — it never invents a transcript from noise.
2. The realtime session layer additionally accepts explicit
   `transcript.inject` client events ONLY when this provider is active
   (test/dev mode), enabling end-to-end protocol, fan-out and UI testing
   without a microphone or model weights.

Results are always marked model="dev-text-v1", provider="dev_text".
"""
from __future__ import annotations

import logging

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import TranscriptChunk

log = logging.getLogger("gt_ai.stt.dev")


@register("stt", "dev_text")
class DevTextSttProvider(BaseProvider):
    name = "dev_text"
    task = "stt"
    private = True
    quality_tier = 0
    cost_tier = 0
    latency_class = "realtime"

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None) -> TranscriptChunk:
        # Never fabricate text from audio. Real transcripts in dev come via
        # transcript.inject events handled by the realtime session layer.
        return TranscriptChunk(
            text="",
            language=lang_hint,
            is_final=True,
            confidence=None,
            model="dev-text-v1",
            provider=self.name,
        )
