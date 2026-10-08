"""Argos Translate adapter — fully offline open-source NMT (per-language packs).

Real self-hosted translation on CPU. Language packs are installed via
`argospm` (see docs/AI.md). This is the default real provider for local
development without a GPU.
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

log = logging.getLogger("gt_ai.mt.argos")


@register("mt", "argos")
class ArgosProvider(BaseProvider):
    name = "argos"
    task = "mt"
    private = True
    quality_tier = 60
    cost_tier = 20
    latency_class = "fast"
    requires_gpu = False

    def __init__(self) -> None:
        self._lang_codes: set[str] | None = None
        self._lock = asyncio.Lock()

    def _installed_codes_sync(self) -> set[str]:
        try:
            import argostranslate.package
            import argostranslate.translate
        except ImportError as e:
            raise ProviderUnavailable("argos requires `pip install gt-ai[argos]`") from e
        argostranslate.package.update_package_index()
        packages = argostranslate.package.get_installed_packages()
        codes: set[str] = set()
        for p in packages:
            codes.add(p.from_code)
            codes.add(p.to_code)
        return codes

    async def _ensure(self) -> None:
        if self._lang_codes is not None:
            return
        async with self._lock:
            if self._lang_codes is None:
                self._lang_codes = await asyncio.to_thread(self._installed_codes_sync)
                log.info("argos installed language codes: %s", sorted(self._lang_codes))

    async def warmup(self) -> None:
        await self._ensure()

    async def healthcheck(self) -> bool:
        try:
            await self._ensure()
            return bool(self._lang_codes)
        except Exception:
            return False

    @property
    def supported_languages(self) -> set[str]:
        return self._lang_codes or set()

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        await self._ensure()
        src = req.source_lang if req.source_lang != "auto" else "en"
        if src not in self._lang_codes or req.target_lang not in self._lang_codes:
            raise ProviderUnavailable(
                f"argos pack missing for {src}->{req.target_lang}; "
                f"install with argospm (docs/AI.md)"
            )

        def _do() -> str:
            import argostranslate.translate
            return argostranslate.translate.translate(
                normalize_unicode(req.text), src, req.target_lang
            )

        t0 = time.perf_counter()
        raw = await asyncio.to_thread(_do)
        flags: list[str] = []
        raw, gflags = apply_glossary_to_output(raw, req.text, req.glossary or {})
        flags.extend(gflags)
        flags.extend(quality_checks(req.text, raw))
        return TranslationResult(
            text=raw,
            source_lang=src,
            target_lang=req.target_lang,
            model=f"argos-{src}-{req.target_lang}",
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            quality_flags=flags,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        yield result.text
