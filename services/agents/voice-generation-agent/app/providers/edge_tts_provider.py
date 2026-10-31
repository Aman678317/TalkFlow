"""TalkFlow Edge TTS and Google TTS Provider for Agent 06.

Provides high-fidelity, natural human neural voice synthesis across
Indian regional languages (Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati, etc.)
and international languages (English, Japanese, Spanish, German, French, etc.)
with zero GPU or ONNX weight prerequisites and automatic fallback.
"""
from __future__ import annotations

import asyncio
import io
import re
import time
import wave
from typing import AsyncIterator, Dict, List, Optional
import numpy as np
import soundfile as sf

from app.core.logging import get_logger
from app.providers.base import BaseTTSProvider, TTSChunk, TTSResult

logger = get_logger(__name__)

# Default voice mapping for high-fidelity Edge Neural voices
DEFAULT_EDGE_VOICES: Dict[str, str] = {
    # Indian Languages
    "hi": "hi-IN-MadhurNeural",
    "hi-in": "hi-IN-MadhurNeural",
    "mr": "mr-IN-AarohiNeural",
    "mr-in": "mr-IN-AarohiNeural",
    "bn": "bn-IN-TanishaaNeural",
    "bn-in": "bn-IN-TanishaaNeural",
    "bn-bd": "bn-BD-PradeepNeural",
    "ta": "ta-IN-PallaviNeural",
    "ta-in": "ta-IN-PallaviNeural",
    "te": "te-IN-MohanNeural",
    "te-in": "te-IN-MohanNeural",
    "gu": "gu-IN-NiranjanNeural",
    "gu-in": "gu-IN-NiranjanNeural",
    "kn": "kn-IN-GaganNeural",
    "kn-in": "kn-IN-GaganNeural",
    "ml": "ml-IN-SobhanaNeural",
    "ml-in": "ml-IN-SobhanaNeural",
    "pa": "pa-IN-OjasNeural",
    "pa-in": "pa-IN-OjasNeural",
    "ur": "ur-PK-AsadNeural",
    "ur-pk": "ur-PK-AsadNeural",
    # Global Languages
    "en": "en-US-JennyNeural",
    "en-us": "en-US-JennyNeural",
    "en-in": "en-IN-NeerjaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ja-jp": "ja-JP-NanamiNeural",
    "es": "es-ES-ElviraNeural",
    "es-es": "es-ES-ElviraNeural",
    "es-mx": "es-MX-DaliaNeural",
    "fr": "fr-FR-DeniseNeural",
    "fr-fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "de-de": "de-DE-KatjaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "zh-cn": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-HamedNeural",
    "ar-sa": "ar-SA-HamedNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ko": "ko-KR-SunHiNeural",
    "it": "it-IT-ElsaNeural",
}


def _decode_mp3_to_pcm(mp3_bytes: bytes, target_sr: int = 24000) -> tuple[bytes, bytes, float]:
    """Decodes MP3 byte stream into 16-bit mono PCM and standard WAV envelope."""
    data, src_sr = sf.read(io.BytesIO(mp3_bytes), dtype="float32")

    # Mono mixdown if stereo
    if data.ndim == 2:
        data = data.mean(axis=1)

    # Resample if sample rates differ
    if src_sr != target_sr:
        from scipy import signal
        num_samples = int(len(data) * float(target_sr) / src_sr)
        data = signal.resample(data, num_samples)

    # Convert float32 [-1.0, 1.0] to int16 PCM
    pcm_16 = np.clip(data * 32767.0, -32768, 32767).astype(np.int16)
    pcm_bytes = pcm_16.tobytes()

    # Wrap into WAV header
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(target_sr)
        wf.writeframes(pcm_bytes)
    wav_bytes = wav_buf.getvalue()

    duration_ms = (len(pcm_16) / target_sr) * 1000.0
    return wav_bytes, pcm_bytes, duration_ms


_SYNTH_SEMAPHORE = asyncio.Semaphore(2)


async def _synthesize_edge_tts(text: str, voice_name: str, target_sr: int = 24000) -> tuple[bytes, bytes, float]:
    """Synthesizes speech using edge-tts async streaming API with concurrency limiting and retry."""
    import edge_tts

    async with _SYNTH_SEMAPHORE:
        for attempt in range(2):
            try:
                communicate = edge_tts.Communicate(text, voice_name)
                mp3_buf = bytearray()
                async for chunk in communicate.stream():
                    if chunk.get("type") == "audio":
                        mp3_buf.extend(chunk.get("data", b""))

                if mp3_buf:
                    return _decode_mp3_to_pcm(bytes(mp3_buf), target_sr)
            except Exception as ex:
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise ex

        raise RuntimeError(f"Edge TTS produced 0 audio bytes for voice '{voice_name}'.")


def _synthesize_gtts_worker(text: str, lang_code: str, target_sr: int = 24000) -> tuple[bytes, bytes, float]:
    """Fallback neural synthesis via Google TTS."""
    import gtts

    clean_lang = lang_code.lower().split("-")[0].split("_")[0]
    tts = gtts.gTTS(text=text, lang=clean_lang)
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    mp3_bytes = buf.getvalue()

    if not mp3_bytes:
        raise RuntimeError(f"gTTS produced 0 bytes for language '{lang_code}'.")

    return _decode_mp3_to_pcm(mp3_bytes, target_sr)


class EdgeTTSProvider(BaseTTSProvider):
    """High-quality Neural TTS provider powered by Edge Neural Speech with gTTS fallback."""

    name = "edge_tts"
    is_local = False
    supported_languages: List[str] = list(DEFAULT_EDGE_VOICES.keys())

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    def resolve_voice(self, voice_id: str, language: str) -> str:
        """Resolves the most appropriate Edge Neural voice for requested ID and language."""
        if voice_id and "Neural" in voice_id:
            return voice_id

        lang_key = language.lower().strip()
        if lang_key in DEFAULT_EDGE_VOICES:
            return DEFAULT_EDGE_VOICES[lang_key]

        lang_base = lang_key.split("-")[0].split("_")[0]
        if lang_base in DEFAULT_EDGE_VOICES:
            return DEFAULT_EDGE_VOICES[lang_base]

        return DEFAULT_EDGE_VOICES.get("en", "en-US-JennyNeural")

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> TTSResult:
        """Synthesize text into natural human speech with automated failover."""
        t0 = time.perf_counter()
        chosen_voice = self.resolve_voice(voice_id, language)
        clean_text = text.strip() or " "

        # Attempt 1: Edge TTS Neural Voice
        try:
            wav_bytes, pcm_bytes, duration_ms = await _synthesize_edge_tts(
                text=clean_text,
                voice_name=chosen_voice,
                target_sr=sample_rate,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "Edge TTS synthesized speech successfully",
                extra={"voice": chosen_voice, "lang": language, "duration_ms": duration_ms, "latency_ms": latency_ms},
            )
            return TTSResult(
                audio_data=wav_bytes,
                pcm_data=pcm_bytes,
                sample_rate=sample_rate,
                encoding="pcm_s16le",
                format="wav",
                duration_ms=duration_ms,
                provider="edge_tts",
                model="neural-v2",
                voice=chosen_voice,
                latency_ms=latency_ms,
                is_dev=False,
                synthetic=True,
            )
        except Exception as edge_err:
            logger.warning(
                "Edge TTS failed, attempting gTTS fallback",
                extra={"voice": chosen_voice, "error": str(edge_err)},
            )

        # Attempt 2: gTTS Neural fallback
        try:
            wav_bytes, pcm_bytes, duration_ms = await asyncio.to_thread(
                _synthesize_gtts_worker, clean_text, language, sample_rate
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "gTTS fallback synthesized speech successfully",
                extra={"lang": language, "duration_ms": duration_ms, "latency_ms": latency_ms},
            )
            return TTSResult(
                audio_data=wav_bytes,
                pcm_data=pcm_bytes,
                sample_rate=sample_rate,
                encoding="pcm_s16le",
                format="wav",
                duration_ms=duration_ms,
                provider="gtts",
                model="neural-cloud",
                voice=f"gtts-{language}",
                latency_ms=latency_ms,
                is_dev=False,
                synthetic=True,
            )
        except Exception as gtts_err:
            logger.error(
                "Both Edge TTS and gTTS failed",
                extra={"edge_err": str(edge_err), "gtts_err": str(gtts_err)},
            )
            raise RuntimeError(f"Multilingual Neural TTS failed: {edge_err} | {gtts_err}")

    async def synthesize_stream(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> AsyncIterator[TTSChunk]:
        """Synthesize text by sentence streaming."""
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?।。\n])\s+", text.strip())
            if s.strip()
        ]
        if not sentences:
            sentences = [text.strip() or " "]

        total = len(sentences)
        for idx, sentence in enumerate(sentences):
            res = await self.synthesize(
                text=sentence,
                voice_id=voice_id,
                language=language,
                sample_rate=sample_rate,
                **kwargs,
            )
            yield TTSChunk(
                data=res.pcm_data,
                sample_rate=sample_rate,
                encoding="pcm_s16le",
                format="pcm",
                duration_ms=res.duration_ms,
                provider=res.provider,
                model=res.model,
                voice=res.voice,
                is_dev=False,
                synthetic=True,
                chunk_index=idx,
                is_last=(idx == total - 1),
            )

    async def is_healthy(self) -> bool:
        """Edge TTS provider is always considered available."""
        return True

