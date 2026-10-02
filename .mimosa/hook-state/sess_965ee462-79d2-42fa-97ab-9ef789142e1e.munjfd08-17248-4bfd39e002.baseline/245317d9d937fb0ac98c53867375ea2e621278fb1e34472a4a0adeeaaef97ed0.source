"""Development tone TTS provider (NON-PRODUCTION).

Generates REAL PCM audio (formant-ish tone sequences derived from the text)
so the entire audio pipeline — chunking, WS delivery, playback, LiveKit
publishing, buffering, stale-drop — can be exercised without model weights.

It never claims to be speech: output AudioChunk.is_dev=True,
model="dev-tone-v1". Production deployments configure kokoro / piper /
tts_http. The meeting UI renders a "synthetic dev audio" badge when
is_dev is set, so users are never deceived.
"""
from __future__ import annotations

import io
import math
import struct
import time
import wave
from typing import AsyncIterator

import numpy as np

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk

SAMPLE_RATE = 24000


def _text_to_tone_wav(text: str) -> bytes:
    """Deterministic text -> audible tone pattern (placeholder speech)."""
    if not text.strip():
        text = " "
    chunks = []
    base = 160.0
    for i, ch in enumerate(text[:400]):
        if ch == " ":
            chunks.append(np.zeros(int(SAMPLE_RATE * 0.04), dtype=np.float32))
            continue
        dur = 0.055
        n = int(SAMPLE_RATE * dur)
        t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
        f = base + (ord(ch) % 40) * 8
        env = np.hanning(n).astype(np.float32)
        tone = (0.5 * np.sin(2 * math.pi * f * t)
                + 0.25 * np.sin(2 * math.pi * f * 2.02 * t)
                + 0.12 * np.sin(2 * math.pi * f * 3.01 * t)) * env
        chunks.append(tone.astype(np.float32))
    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    pcm = (np.clip(audio, -1, 1) * 30000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


@register("tts", "dev_tone")
class DevToneProvider(BaseProvider):
    name = "dev_tone"
    task = "tts"
    private = True
    quality_tier = 0
    cost_tier = 0
    latency_class = "realtime"

    async def synthesize(self, text: str, lang: str, voice: str | None = None) -> AudioChunk:
        wav = await _to_thread(_text_to_tone_wav, text)
        return AudioChunk(
            data=wav, sample_rate=SAMPLE_RATE, encoding="pcm_s16le", format="wav",
            provider=self.name, model="dev-tone-v1",
            duration_ms=(len(wav) - 44) / (SAMPLE_RATE * 2) * 1000,
            is_dev=True,
        )

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None) -> AsyncIterator[AudioChunk]:
        import re
        sentences = [s for s in re.split(r"(?<=[.!?।。])\s+", text.strip()) if s] or [text]
        for s in sentences:
            yield await self.synthesize(s, lang, voice)


async def _to_thread(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)
