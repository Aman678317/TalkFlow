"""MADLAD-400 translation adapter (Google, 3B-MT, Apache 2.0)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import BaseProvider, TranslationRequest, TranslationResult
from app.providers.madlad400.loader import MadladModelLoader
from app.quality.integrity_checks import check_translation_integrity

log = logging.getLogger("agent04.providers.madlad400")


class Madlad400Provider(BaseProvider):
    """Google MADLAD-400 3B-MT multilingual model."""

    name = "madlad400"
    task = "mt"
    private = True
    quality_tier = 88
    cost_tier = 60
    latency_class = "fast"
    requires_gpu = True

    def __init__(self, model_id: str = "google/madlad400-3b-mt", cache_dir: Optional[str] = None) -> None:
        self.model_id = model_id
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

        # MADLAD-400 uses prepended target language token: <2xx>
        prefixed_text = f"<2{tgt}> {req.text}"

        async with self._lock:
            def _infer():
                tokenizer, model = MadladModelLoader.load(self.model_id, self.cache_dir)
                import torch
                inputs = tokenizer(prefixed_text, return_tensors="pt").to(model.device)
                with torch.no_grad():
                    outputs = model.generate(**inputs, max_length=512)
                return tokenizer.decode(outputs[0], skip_special_tokens=True)

            try:
                translated_text = await asyncio.to_thread(_infer)
            except Exception as e:
                raise ProviderUnavailableError(f"MADLAD inference failed: {e}") from e

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        qflags = check_translation_integrity(req.text, translated_text, src, tgt)

        return TranslationResult(
            text=translated_text,
            source_lang=src,
            target_lang=tgt,
            model=self.model_id,
            provider=self.name,
            latency_ms=latency_ms,
            quality_flags=qflags,
            pivoted=False,
        )

