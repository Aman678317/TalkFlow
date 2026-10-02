"""faster-whisper STT adapter (real streaming-capable self-hosted STT).

Model weights download on first use into MODEL_CACHE_PATH (configurable).
Supports int8 CPU and float16 GPU. VAD filter enabled for realtime segments.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranscriptChunk

log = logging.getLogger("gt_ai.stt.faster_whisper")


@register("stt", "faster_whisper")
class FasterWhisperProvider(BaseProvider):
    name = "faster_whisper"
    task = "stt"
    private = True
    quality_tier = 90
    cost_tier = 60
    latency_class = "realtime"
    requires_gpu = False

    def __init__(self, model_size: str = "small", device: str = "auto",
                 compute_type: str = "int8", cache_dir: str | None = None,
                 vad_filter: bool = True) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cache_dir = cache_dir
        self.vad_filter = vad_filter
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return
            def _load():
                try:
                    from faster_whisper import WhisperModel
                except ImportError as e:
                    raise ProviderUnavailable(
                        "faster_whisper requires `pip install gt-ai[whisper]`"
                    ) from e
                device = self.device
                compute = self.compute_type
                if device == "auto":
                    try:
                        import ctranslate2
                        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                    except ImportError:
                        device = "cpu"
                if device == "cpu" and compute == "float16":
                    compute = "int8"
                return WhisperModel(self.model_size, device=device,
                                    compute_type=compute, download_root=self.cache_dir)
            self._model = await asyncio.to_thread(_load)
            log.info("faster-whisper loaded size=%s", self.model_size)

    async def warmup(self) -> None:
        await self._ensure_loaded()
        await self.transcribe(b"", 16000)  # trigger decode path warmup

    async def healthcheck(self) -> bool:
        try:
            await self._ensure_loaded()
            return True
        except Exception:
            return False

    def _transcribe_sync(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None) -> TranscriptChunk:
        import io
        import numpy as np
        if not audio:
            return TranscriptChunk(text="", language=lang_hint, is_final=True,
                                   model=self.model_size, provider=self.name)
        pcm = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        if sample_rate != 16000:
            # simple linear resample to 16k (whisper requirement)
            n_out = int(len(pcm) * 16000 / sample_rate)
            x_old = np.linspace(0, 1, len(pcm))
            x_new = np.linspace(0, 1, n_out)
            pcm = np.interp(x_new, x_old, pcm).astype(np.float32)
        segments, info = self._model.transcribe(
            pcm,
            language=lang_hint if lang_hint and lang_hint != "auto" else None,
            vad_filter=self.vad_filter,
            beam_size=1,
        )
        texts, t_end = [], 0.0
        lang = lang_hint
        for seg in segments:
            texts.append(seg.text)
            t_end = max(t_end, seg.end or 0.0)
            if seg.language:
                lang = seg.language
        text = "".join(texts).strip()
        return TranscriptChunk(
            text=text,
            language=lang or (info.language if info else None),
            is_final=True,
            start_ms=0,
            end_ms=int(t_end * 1000),
            confidence=float(info.avg_logprob) if info and info.avg_logprob else None,
            model=self.model_size,
            provider=self.name,
        )

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None) -> TranscriptChunk:
        await self._ensure_loaded()
        t0 = time.perf_counter()
        chunk = await asyncio.to_thread(self._transcribe_sync, audio, sample_rate, lang_hint)
        log.debug("stt %d bytes -> %r in %.0fms", len(audio), chunk.text[:40],
                  (time.perf_counter() - t0) * 1000)
        return chunk

    async def transcribe_stream(self, audio_chunks: AsyncIterator[bytes], sample_rate: int,
                                lang_hint: str | None = None) -> AsyncIterator[TranscriptChunk]:
        """Chunked streaming: emit partials every ~1.2s of audio, final at end."""
        await self._ensure_loaded()
        buf = bytearray()
        bytes_per_sec = sample_rate * 2
        async for chunk in audio_chunks:
            buf.extend(chunk)
            if len(buf) >= bytes_per_sec * 1.2:
                partial = await self.transcribe(bytes(buf), sample_rate, lang_hint)
                partial.is_final = False
                yield partial
        if buf:
            final = await self.transcribe(bytes(buf), sample_rate, lang_hint)
            final.is_final = True
            yield final
