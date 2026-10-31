"""Experimental local translation provider using Ollama and Qwen."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
import httpx
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import BaseProvider, TranslationRequest, TranslationResult
from app.quality.integrity_checks import check_translation_integrity

log = logging.getLogger("agent04.providers.qwen")


class QwenTranslationProvider(BaseProvider):
    """Local LLM-based translation adapter using Ollama."""

    name = "local_qwen"
    task = "mt"
    private = True
    quality_tier = 82
    cost_tier = 25
    latency_class = "batch"
    requires_gpu = False

    def __init__(self, base_url: str = "http://localhost:11434/v1", model: str = "qwen3.5:4b") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def runtime_ready(self) -> bool:
        return True

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        start_time = time.perf_counter()
        src = req.source_lang.lower()
        tgt = req.target_lang.lower()

        system_prompt = (
            f"You are a professional real-time multilingual speech and text translation engine. "
            f"Translate the provided text from {src} to {tgt}. "
            f"If the text is code-switched or Hinglish (Hindi written in Roman script mixed with English), "
            f"accurately translate the full meaning into clear, natural, and fluent {tgt}. "
            f"Return ONLY the direct translation. Do not provide explanations, notes, quotes, or markdown."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.text},
            ],
            "temperature": 0.1,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                translated_text = data["choices"][0]["message"]["content"].strip()
                if not translated_text:
                    raise ProviderUnavailableError("Ollama Qwen returned empty translation")
        except Exception as e:
            raise ProviderUnavailableError(f"Ollama Qwen translation failed: {e}") from e

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        qflags = check_translation_integrity(req.text, translated_text, src, tgt)

        return TranslationResult(
            text=translated_text,
            source_lang=src,
            target_lang=tgt,
            model=self.model,
            provider=self.name,
            latency_ms=latency_ms,
            quality_flags=qflags,
            pivoted=False,
        )

