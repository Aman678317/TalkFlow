"""MADLAD-400 translation adapter (transformers, self-hosted, GPU recommended).

Lazy-loads the model on first use / warmup(). Model id is configurable via
TRANSLATION_MODEL (default google/madlad-400-3b-mt). Supports 400+
languages; per-pair validation lives in the capability registry, not here.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranslationRequest, TranslationResult
from gt_ai.translation.text_ops import (
    apply_glossary_to_output,
    normalize_unicode,
    quality_checks,
)

log = logging.getLogger("gt_ai.mt.madlad400")


@register("mt", "madlad400")
class Madlad400Provider(BaseProvider):
    name = "madlad400"
    task = "mt"
    private = True
    quality_tier = 85
    cost_tier = 70
    latency_class = "fast"
    requires_gpu = False  # runs on CPU (slow); router prefers GPU when available

    def __init__(self, model_id: str = "google/madlad-400-3b-mt", device: str = "auto",
                 cache_dir: str | None = None) -> None:
        self.model_id = model_id
        self.device = device
        self.cache_dir = cache_dir
        self._model: Any = None
        self._tokenizer: Any = None
        self._lock = asyncio.Lock()

    def _resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return
            def _load():
                try:
                    import torch
                    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                except ImportError as e:
                    raise ProviderUnavailable(
                        "madlad400 requires `pip install gt-ai[mt]` (transformers+torch)"
                    ) from e
                device = self._resolve_device()
                tok = AutoTokenizer.from_pretrained(self.model_id, cache_dir=self.cache_dir)
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    self.model_id, cache_dir=self.cache_dir,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                ).to(device)
                model.eval()
                return tok, model, device
            self._tokenizer, self._model, self._device = await asyncio.to_thread(_load)
            log.info("madlad400 loaded model=%s device=%s", self.model_id, self._device)

    async def warmup(self) -> None:
        await self._ensure_loaded()

    async def healthcheck(self) -> bool:
        try:
            await self._ensure_loaded()
            return True
        except Exception:
            return False

    def _generate_sync(self, req: TranslationRequest) -> str:
        import torch
        text = normalize_unicode(req.text)
        prefix = f"<2{req.target_lang}> "
        inputs = self._tokenizer(prefix + text, return_tensors="pt").to(self._device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=min(1024, max(32, len(text) // 2 + 64)),
                num_beams=1 if req.intent.value == "latency_optimized" else 4,
            )
        return self._tokenizer.decode(out[0], skip_special_tokens=True)

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        await self._ensure_loaded()
        t0 = time.perf_counter()
        raw = await asyncio.to_thread(self._generate_sync, req)
        flags: list[str] = []
        raw, gflags = apply_glossary_to_output(raw, req.text, req.glossary or {})
        flags.extend(gflags)
        flags.extend(quality_checks(req.text, raw))
        return TranslationResult(
            text=raw,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model=self.model_id,
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            quality_flags=flags,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        # sentence-level incremental streaming: translate clause by clause so
        # the listener gets output before the full utterance is done.
        import re
        result_full = await self.translate(req)
        parts = re.split(r"(?<=[.!?।。؟])\s+", result_full.text)
        buf = ""
        for p in parts:
            buf += p + " "
            yield p + " "
        if not buf.strip():
            yield result_full.text
