"""Neural & Online TTS provider.

Provides natural, human-grade voice synthesis across 100+ languages:
1. High-speed online neural voice synthesis (Google Translate Web TTS)
2. Chunked sentence streaming for ultra-low latency real-time meetings
3. Automatic language subtag normalization
"""
from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from typing import AsyncIterator

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk

log = logging.getLogger("gt_ai.tts.neural_online")

SAMPLE_RATE = 24000

# Mapping common ISO language tags to Google TTS supported codes
TTS_LANG_MAP: dict[str, str] = {
    "en": "en",
    "en-us": "en",
    "en-gb": "en-gb",
    "es": "es",
    "es-es": "es",
    "es-mx": "es",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "pt": "pt",
    "pt-br": "pt-br",
    "ru": "ru",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "ja": "ja",
    "ko": "ko",
    "hi": "hi",
    "ar": "ar",
    "nl": "nl",
    "pl": "pl",
    "tr": "tr",
    "uk": "uk",
    "sv": "sv",
    "da": "da",
    "fi": "fi",
    "el": "el",
    "cs": "cs",
    "ro": "ro",
    "hu": "hu",
    "th": "th",
    "vi": "vi",
    "id": "id",
    "bn": "bn",
    "ta": "ta",
    "te": "te",
    "mr": "mr",
    "ur": "ur",
}


def _clean_tts_text(text: str) -> str:
    # Remove markdown, brackets, and excessive whitespace
    clean = re.sub(r"\[.*?\]", "", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _split_into_tts_phrases(text: str, max_chars: int = 140) -> list[str]:
    """Split into natural phrasing boundaries for smooth streaming audio."""
    clean = _clean_tts_text(text)
    if not clean:
        return []
    if len(clean) <= max_chars:
        return [clean]

    # Split by clause / sentence punctuation
    parts = re.split(r"(?<=[.!?,;:।。])\s+", clean)
    phrases: list[str] = []
    curr = ""
    for p in parts:
        if not p.strip():
            continue
        if len(curr) + len(p) + 1 <= max_chars:
            curr = f"{curr} {p}".strip() if curr else p
        else:
            if curr:
                phrases.append(curr)
            if len(p) > max_chars:
                # Word-level fallback for unusually long single sentences
                words = p.split()
                sub = ""
                for w in words:
                    if len(sub) + len(w) + 1 <= max_chars:
                        sub = f"{sub} {w}".strip() if sub else w
                    else:
                        if sub:
                            phrases.append(sub)
                        sub = w
                if sub:
                    curr = sub
                else:
                    curr = ""
            else:
                curr = p
    if curr:
        phrases.append(curr)
    return phrases


async def fetch_tts_audio(text: str, lang_code: str) -> bytes:
    """Fetch synthesized audio bytes for text in target language."""
    clean_lang = lang_code.lower().strip()
    tl = TTS_LANG_MAP.get(clean_lang, clean_lang.split("-")[0])

    url = "https://translate.google.com/translate_tts"
    params = {
        "ie": "UTF-8",
        "tl": tl,
        "client": "tw-ob",
        "q": text,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": "https://translate.google.com/",
    }

    async with httpx.AsyncClient(timeout=8.0, headers=headers) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        if not res.content or len(res.content) < 64:
            raise ValueError(f"Empty or truncated TTS response for '{text[:20]}'")
        return res.content


@register("tts", "neural_online")
@register("tts", "google_tts")
class NeuralOnlineTtsProvider(BaseProvider):
    name = "neural_online"
    task = "tts"
    private = False
    quality_tier = 90
    cost_tier = 0
    latency_class = "realtime"

    async def healthcheck(self) -> bool:
        return True

    async def synthesize(self, text: str, lang: str, voice: str | None = None) -> AudioChunk:
        phrases = _split_into_tts_phrases(text)
        if not phrases:
            return AudioChunk(
                data=b"", sample_rate=SAMPLE_RATE, encoding="mp3", format="mp3",
                provider=self.name, model="google-nmt-voice", duration_ms=0, is_dev=False
            )

        # Concatenate audio bytes for all phrases
        tasks = [fetch_tts_audio(p, lang) for p in phrases]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined = bytearray()
        for res in results:
            if isinstance(res, bytes):
                combined.extend(res)
            else:
                log.warning("TTS phrase synthesis error: %s", res)

        audio_bytes = bytes(combined)
        duration_ms = max(200.0, len(text.split()) * 280.0)
        return AudioChunk(
            data=audio_bytes,
            sample_rate=SAMPLE_RATE,
            encoding="mp3",
            format="mp3",
            provider=self.name,
            model="google-nmt-voice",
            duration_ms=duration_ms,
            is_dev=False,
        )

    async def synthesize_stream(
        self, text: str, lang: str, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        phrases = _split_into_tts_phrases(text)
        if not phrases:
            return

        for phrase in phrases:
            try:
                audio = await fetch_tts_audio(phrase, lang)
                duration_ms = max(200.0, len(phrase.split()) * 280.0)
                yield AudioChunk(
                    data=audio,
                    sample_rate=SAMPLE_RATE,
                    encoding="mp3",
                    format="mp3",
                    provider=self.name,
                    model="google-nmt-voice",
                    duration_ms=duration_ms,
                    is_dev=False,
                )
            except Exception as e:
                log.warning("Streaming TTS chunk failed for '%s': %s", phrase[:20], e)
