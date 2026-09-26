"""Development echo translation provider.

NON-PRODUCTION adapter. It does not pretend to translate: output is the
source text marked with a deterministic, clearly-flagged transformation so
the whole pipeline (routing, glossary, TM, QA, persistence, WS fan-out,
UI) can be exercised end-to-end without model weights.

Every result carries quality_flags=["dev_provider"] and model="dev-echo-v1"
so downstream systems, analytics and users can always tell it apart from a
real model translation. Production deployments configure madlad400 /
nllb_ct2 / argos / mt_http instead.
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import TranslationRequest, TranslationResult
from gt_ai.translation.text_ops import (
    apply_glossary_to_output,
    normalize_unicode,
    quality_checks,
)


@register("mt", "dev_echo")
class DevEchoTranslationProvider(BaseProvider):
    name = "dev_echo"
    task = "mt"
    private = True
    quality_tier = 1
    cost_tier = 0
    latency_class = "realtime"
    requires_gpu = False

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        t0 = time.perf_counter()
        text = normalize_unicode(req.text)
        # deterministic marker: keeps pipeline observable without inventing
        # fake "translated" natural language.
        out = f"[{req.target_lang}] {text}"
        flags = ["dev_provider"]
        out, glossary_flags = apply_glossary_to_output(out, text, req.glossary or {})
        flags.extend(glossary_flags)
        flags.extend(quality_checks(text, out))
        return TranslationResult(
            text=out,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model="dev-echo-v1",
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            quality_flags=flags,
            confidence=0.0,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        words = result.text.split(" ")
        for i in range(0, len(words), 3):
            yield " ".join(words[i : i + 3]) + (" " if i + 3 < len(words) else "")
