"""Outbound event dispatcher for forwarding Agent 02 transcripts to Agent 03 (Language Intelligence)."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional
import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import TranscribeResponse

log = get_logger("agent03_publisher")

# Default Agent 03 URL
AGENT03_URL = settings.integration.language_agent_url


class Agent03Publisher:
    """Dispatches finalized transcript events to Agent 03 (Language Intelligence Agent)."""

    def __init__(self, target_url: str = AGENT03_URL):
        self.target_url = target_url.rstrip("/")

    async def forward_transcript_to_agent03(
        self,
        transcribe_resp: TranscribeResponse,
    ) -> Optional[Dict[str, Any]]:
        """Sends transcript.final event to Agent 03 for language intelligence analysis."""
        if not transcribe_resp.is_final or not transcribe_resp.text.strip():
            return None

        endpoint = f"{self.target_url}/api/v1/language/transcript"

        payload = {
            "version": 1,
            "type": "transcript.final",
            "session_id": getattr(transcribe_resp, "session_id", "session_default"),
            "conversation_id": getattr(transcribe_resp, "conversation_id", "conv_default"),
            "speaker_id": getattr(transcribe_resp, "speaker_id", "speaker_default"),
            "utterance_id": getattr(transcribe_resp, "utterance_id", f"utt_{int(time.time()*1000)}"),
            "segment_id": getattr(transcribe_resp, "segment_id", f"seg_{int(time.time()*1000)}"),
            "seq": getattr(transcribe_resp, "seq", 1),
            "text": transcribe_resp.text,
            "language_hint": transcribe_resp.language_hint,
            "language_probability": transcribe_resp.language_probability,
            "confidence": transcribe_resp.confidence,
            "is_final": True,
            "provider": transcribe_resp.provider,
            "model": transcribe_resp.model,
            "target_languages": ["en", "mr", "ja", "bn"],
            "words": [w.model_dump() for w in transcribe_resp.words],
            "timestamp": time.time(),
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    p_lang = data.get("primary_language", "und")
                    conf = data.get("confidence", 0.0)
                    spans = len(data.get("language_spans", []))
                    log.info(
                        f"[Agent 02 -> Agent 03] Language analyzed: {p_lang.upper()} ({conf*100:.1f}%), "
                        f"Spans: {spans}, Latency: {data.get('analysis_latency_ms')}ms"
                    )
                    return data
                else:
                    log.warning(f"[Agent 02 -> Agent 03] Agent 03 returned {resp.status_code}: {resp.text}")
        except Exception as exc:
            log.warning(f"[Agent 02 -> Agent 03] Could not forward transcript to Agent 03 at {endpoint}: {exc}")
        return None


publisher_to_agent03 = Agent03Publisher()
