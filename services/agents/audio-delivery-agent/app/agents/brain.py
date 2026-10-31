"""Diagnostic brain and domain reasoning engine for Agent 07 Audio Delivery."""
from __future__ import annotations

import httpx
import time
from typing import Any, Dict, Optional
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import BrainQueryResponse

logger = get_logger("agents.brain")


class AudioDeliveryBrain:
    """Intelligent diagnostic brain for Agent 07 with expert domain knowledge fallback."""

    def __init__(self):
        settings = get_settings()
        self.ollama_url = getattr(settings, "ollama_url", "http://127.0.0.1:11434")
        if self.ollama_url.endswith("/v1"):
            self.ollama_url = self.ollama_url[:-3].rstrip("/")
        self.model = getattr(settings.llm_agent, "model", "qwen2.5:1.5b")

    async def query(self, user_query: str, context: Optional[Dict[str, Any]] = None) -> BrainQueryResponse:
        """Process diagnostic or operational question."""
        ctx = context or {}

        # 1. Try Ollama LLM if configured and reachable
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": f"System: You are TalkFlow Audio Delivery Agent (Agent 07) Expert.\nQuestion: {user_query}",
                        "stream": False,
                        "keep_alive": "24h",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    ans = data.get("response", "").strip()
                    if ans:
                        return BrainQueryResponse(
                            answer=ans,
                            confidence=0.95,
                            source="ollama_llm",
                            diagnostics={"model": self.model, "ollama_url": self.ollama_url},
                        )
        except Exception:
            # Fall back seamlessly to built-in expert engine
            pass

        # 2. Expert Domain Reasoning Engine
        q_lower = user_query.lower()

        if any(w in q_lower for w in ["jitter", "reorder", "gap", "out of order"]):
            answer = (
                "Agent 07 implements an in-memory per-utterance Jitter Buffer. Chunks are keyed by sequence index. "
                "If chunk N arrives before N-1, it is held in the buffer. Once the missing chunk arrives, all contiguous "
                "in-order chunks are popped immediately. If a chunk is missing longer than reorder_wait_ms (default 60ms), "
                "the gap is skipped to maintain real-time conversational flow."
            )
        elif any(w in q_lower for w in ["stale", "latency", "drop", "deadline"]):
            answer = (
                "Agent 07 enforces conversational freshness using a Turn Timeline Tracker and Stale Detector. If an incoming "
                "chunk's start_wall_ms lags behind the active room conversation horizon by more than max_stale_delay_ms (1500ms), "
                "or if a newer sequence turn has already begun from that speaker, the late chunk is dropped with AudioDroppedEvent "
                "to avoid playing stale speech over newer active turns."
            )
        elif any(w in q_lower for w in ["feedback", "loop", "echo", "speaker"]):
            answer = (
                "Agent 07 strictly prevents audio feedback loops and microphone echo. When a participant speaks in a multi-user "
                "room, their participant_id is excluded from the eligible recipient list for that utterance's translated audio. "
                "Additionally, all synthesized audio carries synthetic=True and audio_origin='synthetic_tts', preventing re-ingestion "
                "into upstream STT."
            )
        elif any(w in q_lower for w in ["binary", "wire", "format", "0x54", "header"]):
            answer = (
                "TalkFlow binary audio frames use the 0x54 ('T') wire protocol:\n"
                "- Byte 0: 0x54 ('T')\n"
                "- Bytes 1..16: 16-byte fixed segment short ID (hex without dashes, padded with \x00)\n"
                "- Byte 17: uint8 language tag length L\n"
                "- Bytes 18..(18+L-1): UTF-8 target language string\n"
                "- Byte 18+L: 0x01 extension marker\n"
                "- Next 4 bytes: uint32 chunk_index in big-endian\n"
                "- Remaining bytes: raw PCM16/WAV payload."
            )
        elif any(w in q_lower for w in ["fanout", "fan-out", "routing", "recipients"]):
            answer = (
                "Agent 07 uses a 'Translate Once, Synthesize Once, Fan Out to Many' architecture. One synthesized audio "
                "stream for (room, segment, target_lang) is fanned out to all room participants who configured hear_lang == target_lang "
                "and playback_mode in ('translated', 'both'). Participants in 'original' mode are untouched."
            )
        elif any(w in q_lower for w in ["barge", "interrupt", "flush", "cancel"]):
            answer = (
                "When a speaker interrupts or starts talking, BargeInManager flushes all pending jitter buffers for that utterance "
                "and broadcasts a playback.flush JSON event. This signals listener web clients to immediately clear their Web Audio "
                "queues without audible latency."
            )
        elif any(w in q_lower for w in ["ducking", "gain", "volume", "both"]):
            answer = (
                "For participants configured in 'both' playback mode, DuckingMixer lowers original human audio by the configured "
                "ducking ratio (default 0.20 or -14 dB) while translated audio is playing, allowing both to be audible while ensuring "
                "the translation remains intelligible."
            )
        else:
            answer = (
                f"Agent 07 (Audio Synchronization & Delivery) manages jitter buffering, timeline synchronization, "
                f"stale chunk dropping, 1-to-N fan-out routing, and dual transport delivery (LiveKit RTC tracks and "
                f"TalkFlow 0x54 binary WebSocket frames) for multilingual meetings."
            )

        return BrainQueryResponse(
            answer=answer,
            confidence=1.0,
            source="expert_domain_engine",
            diagnostics={"context": ctx, "query": user_query},
        )


brain = AudioDeliveryBrain()

