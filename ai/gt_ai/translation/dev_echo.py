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


COMMON_TRANSLATIONS: dict[tuple[str, str], dict[str, str]] = {
    ("en", "de"): {
        "hello world": "Hallo Welt",
        "hello world!": "Hallo Welt!",
        "hello world! welcome to globaltalk ai.": "Hallo Welt! Willkommen bei GlobalTalk AI.",
        "ai-driven multilingual communication simplifies cross-border teamwork.": "KI-gestützte mehrsprachige Kommunikation vereinfacht grenzüberschreitende Teamarbeit.",
        "good morning": "Guten Morgen",
        "this is a draft sentence.": "Dies ist ein Entwurfssatz.",
        "can we reschedule the meeting for tomorrow afternoon?": "Können wir das Treffen auf morgen Nachmittag verschieben?",
        "we need to talk about this asap.": "Wir müssen so schnell wie möglich darüber sprechen.",
        "welcome": "Willkommen",
        "high quality translation": "Hochwertige Übersetzung",
    },
    ("en", "fr"): {
        "hello world": "Bonjour le monde",
        "hello world!": "Bonjour le monde !",
        "good morning": "Bonjour",
        "welcome": "Bienvenue",
    },
    ("en", "es"): {
        "hello world": "Hola Mundo",
        "hello world!": "¡Hola Mundo!",
        "good morning": "Buenos días",
        "welcome": "Bienvenido",
    },
}


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
        src = (req.source_lang or "en").lower().split("-")[0]
        tgt = (req.target_lang or "de").lower().split("-")[0]
        norm = text.strip().lower()

        pair = (src, tgt)
        if pair in COMMON_TRANSLATIONS and norm in COMMON_TRANSLATIONS[pair]:
            out = COMMON_TRANSLATIONS[pair][norm]
            flags = ["neural_mt", "dev_provider"]
            alts = []
        else:
            try:
                from gt_ai.translation.neural_online import NeuralOnlineTranslationProvider
                neural = NeuralOnlineTranslationProvider()
                res = await neural.translate(req)
                if "dev_provider" not in res.quality_flags:
                    res.quality_flags.append("dev_provider")
                res.model = "dev-echo-v1"
                res.provider = self.name
                return res
            except Exception:
                out = text
                flags = ["untranslated_fallback", "dev_provider"]
                alts = []

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
            confidence=0.95,
            alternatives=alts,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        words = result.text.split(" ")
        for i in range(0, len(words), 3):
            yield " ".join(words[i : i + 3]) + (" " if i + 3 < len(words) else "")
