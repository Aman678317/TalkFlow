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
    ("en", "hi"): {
        "hello": "नमस्ते",
        "hello!": "नमस्ते!",
        "hello world": "नमस्ते दुनिया",
        "hello world!": "नमस्ते दुनिया!",
        "hello world! welcome to globaltalk ai.": "नमस्ते दुनिया! GlobalTalk AI में आपका स्वागत है।",
        "good morning": "शुभ प्रभात",
        "good morning!": "शुभ प्रभात!",
        "how are you": "आप कैसे हैं?",
        "how are you?": "आप कैसे हैं?",
        "welcome": "स्वागत है",
        "welcome to globaltalk ai": "GlobalTalk AI में आपका स्वागत है",
        "thank you": "धन्यवाद",
        "thank you very much": "बहुत बहुत धन्यवाद",
        "this is a test meeting": "यह एक परीक्षण बैठक है",
        "this is a draft sentence.": "यह एक मसौदा वाक्य है।",
        "can we reschedule the meeting for tomorrow afternoon?": "क्या हम बैठक को कल दोपहर के लिए पुनर्निर्धारित कर सकते हैं?",
        "we need to talk about this asap.": "हमें इस बारे में जल्द से जल्द बात करने की आवश्यकता है।",
        "high quality translation": "उच्च गुणवत्ता वाला अनुवाद",
    },
    ("hi", "en"): {
        "नमस्ते": "Hello",
        "नमस्ते!": "Hello!",
        "नमस्ते दुनिया": "Hello world",
        "नमस्ते दुनिया!": "Hello world!",
        "शुभ प्रभात": "Good morning",
        "शुभ प्रभात!": "Good morning!",
        "आप कैसे हैं?": "How are you?",
        "आप कैसे हैं": "How are you?",
        "धन्यवाद": "Thank you",
        "बहुत बहुत धन्यवाद": "Thank you very much",
        "स्वागत है": "Welcome",
        "यह एक परीक्षण बैठक है": "This is a test meeting",
        "globaltalk ai में आपका स्वागत है": "Welcome to GlobalTalk AI",
    },
    ("de", "en"): {
        "hallo welt": "Hello world",
        "hallo welt!": "Hello world!",
        "guten morgen": "Good morning",
        "willkommen": "Welcome",
        "wie geht es ihnen?": "How are you?",
    },
    ("fr", "en"): {
        "bonjour le monde": "Hello world",
        "bonjour le monde !": "Hello world!",
        "bonjour": "Good morning",
        "bienvenue": "Welcome",
        "comment allez-vous ?": "How are you?",
    },
    ("es", "en"): {
        "hola mundo": "Hello world",
        "hola mundo!": "Hello world!",
        "buenos días": "Good morning",
        "bienvenido": "Welcome",
        "¿cómo estás?": "How are you?",
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
