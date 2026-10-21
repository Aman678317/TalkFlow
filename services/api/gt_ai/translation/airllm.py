"""Optional AirLLM translation provider.

AirLLM is deliberately isolated from the normal API image. The adapter imports
the package only when the operator selects ``TRANSLATION_PROVIDER=airllm`` in a
GPU worker, so CPU/Vercel/Render deployments keep the existing provider set.
Weights must already sit in the local HF cache (seeded by the operator workflow)
or the operator must opt in via ``GT_ALLOW_MODEL_DOWNLOAD`` — a user request
never starts a Llama download (issue #109 class 2, 2026-10-21). They are never
copied into this repository or a regular application image.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranslationRequest, TranslationResult
from gt_ai.translation import model_fetch
from gt_ai.translation.text_ops import apply_glossary_to_output, normalize_unicode, quality_checks

log = logging.getLogger("gt_ai.mt.airllm")


@register("mt", "airllm")
class AirLLMTranslationProvider(BaseProvider):
    """Translate with a Hugging Face causal LLM loaded through AirLLM."""

    name = "airllm"
    task = "mt"
    private = True
    quality_tier = 90
    cost_tier = 0
    latency_class = "batch"
    requires_gpu = True

    def __init__(
        self,
        model_id: str,
        hf_token: str = "",
        layer_shards_saving_path: str = "",
        max_input_tokens: int = 512,
        max_new_tokens: int = 128,
    ) -> None:
        self.model_id = model_id or "meta-llama/Llama-3.1-70B-Instruct"
        self.hf_token = hf_token
        self.layer_shards_saving_path = layer_shards_saving_path
        self.max_input_tokens = max(64, max_input_tokens)
        self.max_new_tokens = max(16, max_new_tokens)
        self._model: Any | None = None
        self._load_lock = asyncio.Lock()

    def runtime_ready(self) -> bool:
        """Serves only when the optional airllm package is installed AND the
        (default >100 GB) Llama weights are already in the local HF cache —
        unless the operator explicitly opted in to downloads. The import must
        never happen behind a user request (heavier native bootstrap than the
        request budget allows)."""
        import importlib.util

        if importlib.util.find_spec("airllm") is None:
            return False
        return model_fetch.downloads_allowed() or model_fetch.hf_artifact_cached(
            self.model_id, None, ("config.json",))

    async def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._load_lock:
            if self._model is not None:
                return self._model
            model_fetch.require_cached_or_raise(
                "airllm", self.model_id, None, ("config.json",))
            try:
                from airllm import AutoModel
                import torch
            except ImportError as exc:
                raise ProviderUnavailable(
                    "AirLLM is not installed. Build the optional GPU image "
                    "with services/api/requirements-gpu.txt."
                ) from exc
            if not torch.cuda.is_available():
                raise ProviderUnavailable(
                    "AirLLM GPU inference requires CUDA. Run it through the optional "
                    "Docker Compose gpu profile."
                )

            kwargs: dict[str, Any] = {}
            if self.hf_token:
                kwargs["hf_token"] = self.hf_token
            if self.layer_shards_saving_path:
                Path(self.layer_shards_saving_path).mkdir(parents=True, exist_ok=True)
                kwargs["layer_shards_saving_path"] = self.layer_shards_saving_path
            try:
                self._model = await asyncio.to_thread(
                    AutoModel.from_pretrained, self.model_id, **kwargs
                )
            except Exception as exc:
                log.exception("AirLLM model load failed for %s", self.model_id)
                raise ProviderUnavailable(
                    f"AirLLM could not load model '{self.model_id}'. "
                    "Check GPU access, disk space, and Hugging Face access."
                ) from exc
            return self._model

    @staticmethod
    def _prompt(req: TranslationRequest) -> str:
        source = req.source_lang or "auto"
        target = req.target_lang
        context = "\n".join(req.context[-2:]) if req.context else ""
        context_block = f"\nContext:\n{context}\n" if context else ""
        return (
            "You are a precise translation engine. Translate the text from "
            f"{source} to {target}. Preserve meaning, names, numbers, URLs, "
            "line breaks, and punctuation. Return only the translation, with "
            "no explanation or language label."
            f"{context_block}\nText:\n{req.text}\nTranslation:\n"
        )

    def _generate_sync(self, model: Any, prompt: str) -> str:
        import torch

        tokens = model.tokenizer(
            [prompt],
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=self.max_input_tokens,
            padding=False,
        )
        input_ids = tokens["input_ids"]
        if torch.cuda.is_available():
            input_ids = input_ids.cuda()
        output = model.generate(
            input_ids,
            max_new_tokens=self.max_new_tokens,
            use_cache=True,
            return_dict_in_generate=True,
        )
        generated = output.sequences[0][input_ids.shape[-1]:]
        return model.tokenizer.decode(generated, skip_special_tokens=True).strip()

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        text = normalize_unicode(req.text).strip()
        if not text:
            raise ProviderUnavailable("AirLLM received empty text.")
        started = time.perf_counter()
        model = await self._load_model()
        try:
            translated = await asyncio.to_thread(self._generate_sync, model, self._prompt(req))
        except ProviderUnavailable:
            raise
        except Exception as exc:
            log.exception("AirLLM generation failed")
            raise ProviderUnavailable("AirLLM generation failed; try another provider.") from exc
        if not translated:
            raise ProviderUnavailable("AirLLM returned an empty translation.")

        translated, glossary_flags = apply_glossary_to_output(
            translated, text, req.glossary or {}
        )
        flags = ["airllm", *glossary_flags, *quality_checks(text, translated)]
        return TranslationResult(
            text=translated,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model=self.model_id,
            provider=self.name,
            latency_ms=(time.perf_counter() - started) * 1000,
            quality_flags=flags,
            confidence=None,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        yield result.text
