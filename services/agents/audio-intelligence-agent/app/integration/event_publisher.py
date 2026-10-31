"""Outbound event dispatcher for downstream agents (e.g., Agent 02: STT)."""
from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Callable, Dict, List, Optional
import httpx
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("event_publisher")


class EventPublisher:
    """Dispatches processed speech events and clean audio segments to downstream subscribers and Agent 02 (STT)."""

    def __init__(self):
        self._subscribers: List[Callable[[Dict[str, Any], Optional[bytes]], Any]] = []
        self._downstream_url = settings.integration.talkflow_api_url

    def subscribe(self, callback: Callable[[Dict[str, Any], Optional[bytes]], Any]) -> None:
        """Registers an in-process callback listener."""
        self._subscribers.append(callback)

    async def publish_event(self, event: Dict[str, Any], pcm_bytes: Optional[bytes] = None) -> None:
        """Broadcasts event and optional audio payload to all subscribers and downstream webhook."""
        # 1. In-process dispatch
        for sub in self._subscribers:
            try:
                res = sub(event, pcm_bytes)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as e:
                log.error(f"Subscriber delivery failed: {e}")

        # 2. HTTP Webhook dispatch to Agent 02 (STT) for finalized segments
        evt_name = event.get("event") or event.get("event_type") or event.get("type")
        if self._downstream_url and evt_name == "audio.segment.final":
            asyncio.create_task(self.forward_to_agent02_stt(event, pcm_bytes))

    async def forward_to_agent02_stt(
        self,
        event: Dict[str, Any],
        pcm_bytes: Optional[bytes] = None,
    ) -> Optional[Dict[str, Any]]:
        """Forwards finalized speech segment to Agent 02 (Speech Recognition Agent) and returns STT response."""
        target = f"{self._downstream_url.rstrip('/')}/api/v1/stt/segment"
        seg_id = event.get("segment_id", "seg_0")
        seq = event.get("sequence", 1)
        dur_s = float(event.get("duration_ms", 0)) / 1000.0

        inbound_event = {
            "version": 1,
            "type": "audio.segment.final",
            "session_id": event.get("session_id", "sess_0"),
            "conversation_id": event.get("conversation_id", "conv_0"),
            "speaker_id": event.get("speaker_id", "user_001"),
            "utterance_id": f"utt_{seg_id}",
            "segment_id": seg_id,
            "seq": seq,
            "timestamp": time.time(),
            "payload": {
                "segment_id": seg_id,
                "sequence_number": seq,
                "start_timestamp": float(event.get("start_ms", 0)) / 1000.0,
                "end_timestamp": float(event.get("end_ms", 0)) / 1000.0,
                "duration_seconds": dur_s,
                "sample_rate": event.get("sample_rate", 16000),
                "channels": event.get("channels", 1),
                "encoding": event.get("encoding", "pcm16"),
                "audio_data_base64": base64.b64encode(pcm_bytes).decode("ascii") if pcm_bytes else None,
                "is_final": True,
                "quality_metrics": event.get("quality"),
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {"Authorization": f"Bearer {settings.integration.talkflow_shared_secret}"}
                resp = await client.post(target, json=inbound_event, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    transcript = data.get("text", "")
                    lang = data.get("language_hint", "auto")
                    latency = data.get("recognition_latency_ms", 0)
                    log.info(
                        f"[Agent 01 -> Agent 02] STT transcribed segment {seg_id} in {latency}ms: "
                        f"'{transcript}' (Lang: {lang})"
                    )
                    return data
                else:
                    log.warning(f"[Agent 01 -> Agent 02] STT returned status {resp.status_code}: {resp.text}")
        except Exception as exc:
            log.warning(f"[Agent 01 -> Agent 02] Could not forward to STT at {target}: {exc}")
        return None


publisher = EventPublisher()
