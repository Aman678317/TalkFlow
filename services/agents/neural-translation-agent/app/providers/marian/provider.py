"""MarianMT provider adapter supporting direct Indian language pairs (en<->mr) and controlled pivots."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import BaseProvider, TranslationRequest, TranslationResult
from app.providers.marian.loader import MarianModelLoader
from app.quality.integrity_checks import check_translation_integrity

log = logging.getLogger("agent04.providers.marian")


class MarianProvider(BaseProvider):
    """Helsinki-NLP MarianMT translation provider."""

    name = "marian"
    task = "mt"
    private = True
    quality_tier = 75
    cost_tier = 30
    latency_class = "fast"
    requires_gpu = False

    DIRECT_PAIRS = {("en", "mr"), ("mr", "en"), ("en", "hi"), ("hi", "en"), ("en", "es"), ("es", "en")}
    PIVOT_PAIRS = {("hi", "mr"), ("mr", "hi")}

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir = cache_dir
        self._lock = asyncio.Lock()

    def runtime_ready(self) -> bool:
        try:
            import transformers
            import torch
            return True
        except ImportError:
            return False

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        start_time = time.perf_counter()
        src = req.source_lang.lower()
        tgt = req.target_lang.lower()
        pair = (src, tgt)

        if pair in self.DIRECT_PAIRS:
            translated_text = await self._run_inference(src, tgt, req.text)
            pivoted = False
        elif pair in self.PIVOT_PAIRS:
            # Explicit, documented intermediate pivot via English
            log.info(f"MarianMT pivoting {src}->en->{tgt} for request")
            intermediate_en = await self._run_inference(src, "en", req.text)
            translated_text = await self._run_inference("en", tgt, intermediate_en)
            pivoted = True
        else:
            raise ProviderUnavailableError(f"MarianMT does not support language pair {src}->{tgt}")

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        qflags = check_translation_integrity(req.text, translated_text, src, tgt)
        if pivoted:
            qflags.append("pivoted_via_intermediate")

        return TranslationResult(
            text=translated_text,
            source_lang=src,
            target_lang=tgt,
            model=f"opus-mt-{src}-{tgt}" if not pivoted else f"opus-mt-{src}-en-{tgt}",
            provider=self.name,
            latency_ms=latency_ms,
            quality_flags=qflags,
            pivoted=pivoted,
        )

    async def _run_inference(self, src: str, tgt: str, text: str) -> str:
        async with self._lock:
            def _infer():
                tokenizer, model = MarianModelLoader.load_model(src, tgt, cache_dir=self.cache_dir)
                batch = tokenizer([text], return_tensors="pt", padding=True, truncation=True)
                import torch
                with torch.no_grad():
                    gen = model.generate(**batch, max_length=512)
                return tokenizer.decode(gen[0], skip_special_tokens=True)

            return await asyncio.to_thread(_infer)

