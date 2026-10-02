"""NLLB via CTranslate2 adapter (quantized, CPU/GPU, self-hosted).

Efficient production path for many language pairs. Requires a CT2-converted
NLLB checkpoint (see docs/AI.md §conversion) — license note: NLLB has
non-commercial research terms; commercial deployments must review licensing
(PDD §9 license rule).
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

log = logging.getLogger("gt_ai.mt.nllb_ct2")

# ISO-639-1 -> NLLB BCP-47 codes (subset; extend as pairs are validated)
NLLB_CODES = {
    "en": "eng_Latn", "hi": "hin_Deva", "mr": "mar_Deva", "bn": "ben_Beng",
    "ta": "tam_Taml", "te": "tel_Telu", "gu": "guj_Gujr", "kn": "kan_Knda",
    "ml": "mal_Mlym", "pa": "pan_Guru", "ur": "urd_Arab", "ja": "jpn_Jpan",
    "zh": "zho_Hans", "es": "spa_Latn", "fr": "fra_Latn", "de": "deu_Latn",
    "pt": "por_Latn", "ru": "rus_Cyrl", "ar": "arb_Arab", "ko": "kor_Hang",
}


@register("mt", "nllb_ct2")
class NllbCt2Provider(BaseProvider):
    name = "nllb_ct2"
    task = "mt"
    private = True
    quality_tier = 78
    cost_tier = 40
    latency_class = "fast"
    requires_gpu = False

    def __init__(self, model_dir: str = "model_cache/nllb-200-600m-ct2-int8",
                 tokenizer_id: str = "facebook/nllb-200-distilled-600M",
                 compute_type: str = "int8", device: str = "auto",
                 cache_dir: str | None = None) -> None:
        self.model_dir = model_dir
        self.tokenizer_id = tokenizer_id
        self.compute_type = compute_type
        self.device = device
        self.cache_dir = cache_dir
        self._model: Any = None
        self._tokenizer: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return
            def _load():
                try:
                    import ctranslate2
                    from transformers import AutoTokenizer
                except ImportError as e:
                    raise ProviderUnavailable(
                        "nllb_ct2 requires `pip install gt-ai[ct2]`"
                    ) from e
                import os
                if not os.path.isdir(self.model_dir):
                    raise ProviderUnavailable(f"CT2 model dir not found: {self.model_dir}")
                device = self.device
                if device == "auto":
                    device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                model = ctranslate2.Translator(self.model_dir, device=device,
                                               compute_type=self.compute_type)
                tok = AutoTokenizer.from_pretrained(self.tokenizer_id,
                                                    cache_dir=self.cache_dir,
                                                    src_lang="eng_Latn")
                return model, tok, device
            self._model, self._tokenizer, self._device = await asyncio.to_thread(_load)
            log.info("nllb_ct2 loaded dir=%s device=%s", self.model_dir, self._device)

    async def warmup(self) -> None:
        await self._ensure_loaded()

    async def healthcheck(self) -> bool:
        try:
            await self._ensure_loaded()
            return True
        except Exception:
            return False

    def _translate_sync(self, req: TranslationRequest) -> str:
        src_code = NLLB_CODES.get(req.source_lang if req.source_lang != "auto" else "en", "eng_Latn")
        tgt_code = NLLB_CODES.get(req.target_lang)
        if tgt_code is None:
            raise ProviderUnavailable(f"no NLLB code mapping for {req.target_lang}")
        text = normalize_unicode(req.text)
        self._tokenizer.src_lang = src_code
        tokens = self._tokenizer.convert_ids_to_tokens(self._tokenizer.encode(text).input_ids)
        results = self._model.translate_batch(
            [tokens],
            source_lang=src_code,
            target_prefix=[tgt_code],
            max_decoding_length=min(1024, max(32, len(text) // 2 + 64)),
            beam_size=1 if req.intent.value == "latency_optimized" else 4,
        )
        out_tokens = results[0].hypotheses[0]
        return self._tokenizer.decode(self._tokenizer.convert_tokens_to_ids(out_tokens))

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        await self._ensure_loaded()
        t0 = time.perf_counter()
        raw = await asyncio.to_thread(self._translate_sync, req)
        flags: list[str] = []
        raw, gflags = apply_glossary_to_output(raw, req.text, req.glossary or {})
        flags.extend(gflags)
        flags.extend(quality_checks(req.text, raw))
        return TranslationResult(
            text=raw,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model=self.model_dir,
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            quality_flags=flags,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        yield result.text
