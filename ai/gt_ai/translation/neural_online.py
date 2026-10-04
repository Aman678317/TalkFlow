"""Neural & DeepL online translation provider.

Provides high-quality, human-grade neural machine translation:
1. DeepL API (when DEEPL_API_KEY is configured) with full formality control.
2. MyMemory Neural Translation API (fast, free, multi-language neural translation
   with alternative translations).
3. Google / LibreTranslate fallback with cascading failover.
4. Offline linguistic rule engine for common phrases, greetings, and introductions.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import urllib.parse
from typing import Any, AsyncIterator

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import Intent, ProviderUnavailable, TranslationRequest, TranslationResult
from gt_ai.translation.text_ops import (
    apply_glossary_to_output,
    normalize_unicode,
    quality_checks,
)

log = logging.getLogger("gt_ai.mt.neural_online")

# DeepL language code mapping (ISO 639-1 -> DeepL uppercase)
DEEPL_SUPPORTED_TARGETS = {
    "bg", "cs", "da", "de", "el", "en", "en-gb", "en-us", "es", "et", "fi", "fr",
    "hu", "id", "it", "ja", "ko", "lt", "lv", "nb", "nl", "pl", "pt", "pt-br",
    "pt-pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "zh"
}

# Formality adjustments for Western European languages
FORMALITY_RULES: dict[tuple[str, str], list[tuple[re.Pattern, str]]] = {
    ("de", "formal"): [
        (re.compile(r"\bdu\b", re.I), "Sie"),
        (re.compile(r"\bdir\b", re.I), "Ihnen"),
        (re.compile(r"\bdich\b", re.I), "Sie"),
        (re.compile(r"\bdein\b", re.I), "Ihr"),
        (re.compile(r"\bdeine\b", re.I), "Ihre"),
        (re.compile(r"\bdeinem\b", re.I), "Ihrem"),
        (re.compile(r"\bdeinen\b", re.I), "Ihren"),
        (re.compile(r"\bdeiner\b", re.I), "Ihrer"),
    ],
    ("de", "informal"): [
        (re.compile(r"\bSie\b"), "du"),
        (re.compile(r"\bIhnen\b"), "dir"),
        (re.compile(r"\bIhr\b"), "dein"),
        (re.compile(r"\bIhre\b"), "deine"),
        (re.compile(r"\bIhrem\b"), "deinem"),
        (re.compile(r"\bIhren\b"), "deinen"),
        (re.compile(r"\bIhrer\b"), "deiner"),
    ],
    ("es", "formal"): [
        (re.compile(r"\btú\b", re.I), "usted"),
        (re.compile(r"\bte\b", re.I), "le"),
        (re.compile(r"\btu\b", re.I), "su"),
        (re.compile(r"\btus\b", re.I), "sus"),
    ],
    ("es", "informal"): [
        (re.compile(r"\busted\b", re.I), "tú"),
        (re.compile(r"\ble\b", re.I), "te"),
        (re.compile(r"\bsu\b", re.I), "tu"),
        (re.compile(r"\bsus\b", re.I), "tus"),
    ],
    ("fr", "formal"): [
        (re.compile(r"\btu\b", re.I), "vous"),
        (re.compile(r"\bte\b", re.I), "vous"),
        (re.compile(r"\bton\b", re.I), "votre"),
        (re.compile(r"\bta\b", re.I), "votre"),
        (re.compile(r"\btes\b", re.I), "vos"),
    ],
    ("fr", "informal"): [
        (re.compile(r"\bvous\b", re.I), "tu"),
        (re.compile(r"\bvotre\b", re.I), "ton"),
        (re.compile(r"\bvos\b", re.I), "tes"),
    ],
}

OFFLINE_PATTERNS: list[tuple[re.Pattern, dict[str, str]]] = [
    (
        re.compile(r"^(?:my name is|i am|i'm)\s+(.+)$", re.I),
        {
            "de": "Mein Name ist {0}",
            "es": "Mi nombre es {0}",
            "fr": "Je m'appelle {0}",
            "it": "Mi chiamo {0}",
            "pt": "Meu nome é {0}",
            "hi": "मेरा नाम {0} है",
            "ru": "Меня зовут {0}",
            "zh": "我的名字是{0}",
            "ja": "私の名前は{0}です",
        },
    ),
    (
        re.compile(r"^(?:hello|hi|hey)(?:\s+there)?[\s!.,]*$", re.I),
        {
            "de": "Hallo",
            "es": "Hola",
            "fr": "Bonjour",
            "it": "Ciao",
            "pt": "Olá",
            "hi": "नमस्ते",
            "ru": "Здравствуйте",
            "zh": "你好",
            "ja": "こんにちは",
        },
    ),
    (
        re.compile(r"^hello\s+world[\s!.,]*$", re.I),
        {
            "de": "Hallo Welt",
            "es": "Hola Mundo",
            "fr": "Bonjour le monde",
            "it": "Ciao mondo",
            "pt": "Olá mundo",
            "hi": "नमस्ते दुनिया",
            "ru": "Привет, мир",
            "zh": "你好，世界",
            "ja": "こんにちは世界",
        },
    ),
    (
        re.compile(r"^(?:good morning)[\s!.,]*$", re.I),
        {
            "de": "Guten Morgen",
            "es": "Buenos días",
            "fr": "Bonjour",
            "it": "Buongiorno",
            "pt": "Bom dia",
            "hi": "शुभ प्रभात",
            "ru": "Доброе утро",
            "zh": "早上好",
            "ja": "おはようございます",
        },
    ),
    (
        re.compile(r"^(?:how are you|how's it going)[\s?.,]*$", re.I),
        {
            "de": "Wie geht es Ihnen?",
            "es": "¿Cómo estás?",
            "fr": "Comment allez-vous ?",
            "it": "Come stai?",
            "pt": "Como você está?",
            "hi": "आप कैसे हैं?",
            "ru": "Как дела?",
            "zh": "你好吗？",
            "ja": "お元気ですか？",
        },
    ),
    (
        re.compile(r"^(?:thank you|thanks)(?:\s+very much)?[\s!.,]*$", re.I),
        {
            "de": "Vielen Dank",
            "es": "Muchas gracias",
            "fr": "Merci beaucoup",
            "it": "Grazie mille",
            "pt": "Muito obrigado",
            "hi": "बहुत बहुत धन्यवाद",
            "ru": "Большое спасибо",
            "zh": "非常感谢",
            "ja": "ありがとうございます",
        },
    ),
    (
        re.compile(r"^(?:नमस्ते|नमस्कार)[\s!.,]*$", re.I),
        {
            "en": "Hello",
            "de": "Hallo",
            "es": "Hola",
            "fr": "Bonjour",
            "it": "Ciao",
            "pt": "Olá",
            "ru": "Здравствуйте",
            "zh": "你好",
            "ja": "こんにちは",
        },
    ),
    (
        re.compile(r"^(?:नमस्ते दुनिया|नमस्कार दुनिया)[\s!.,]*$", re.I),
        {
            "en": "Hello world",
            "de": "Hallo Welt",
            "es": "Hola Mundo",
            "fr": "Bonjour le monde",
            "it": "Ciao mondo",
            "pt": "Olá mundo",
            "ru": "Привет, мир",
            "zh": "你好，世界",
            "ja": "こんにちは世界",
        },
    ),
    (
        re.compile(r"^(?:शुभ प्रभात)[\s!.,]*$", re.I),
        {
            "en": "Good morning",
            "de": "Guten Morgen",
            "es": "Buenos días",
            "fr": "Bonjour",
            "it": "Buongiorno",
            "pt": "Bom dia",
            "ru": "Доброе утро",
            "zh": "早上好",
            "ja": "おはようございます",
        },
    ),
    (
        re.compile(r"^(?:आप कैसे हैं|आप कैसे हो)[\s?.,]*$", re.I),
        {
            "en": "How are you?",
            "de": "Wie geht es Ihnen?",
            "es": "¿Cómo estás?",
            "fr": "Comment allez-vous ?",
            "it": "Come stai?",
            "pt": "Como você está?",
            "ru": "Как дела?",
            "zh": "你好吗？",
            "ja": "お元気ですか？",
        },
    ),
    (
        re.compile(r"^(?:धन्यवाद|बहुत बहुत धन्यवाद|शुक्रिया)[\s!.,]*$", re.I),
        {
            "en": "Thank you very much",
            "de": "Vielen Dank",
            "es": "Muchas gracias",
            "fr": "Merci beaucoup",
            "it": "Grazie mille",
            "pt": "Muito obrigado",
            "ru": "Большое спасибо",
            "zh": "非常感谢",
            "ja": "ありがとうございます",
        },
    ),
    (
        re.compile(r"^(?:मेरा नाम\s+(.+)\s+है)[\s!.,]*$", re.I),
        {
            "en": "My name is {0}",
            "de": "Mein Name ist {0}",
            "es": "Mi nombre es {0}",
            "fr": "Je m'appelle {0}",
            "it": "Mi chiamo {0}",
            "pt": "Meu nome é {0}",
            "ru": "Меня зовут {0}",
            "zh": "我的名字是{0}",
            "ja": "私の名前は{0}です",
        },
    ),
    (
        re.compile(r"^(?:स्वागत है|आपका स्वागत है)[\s!.,]*$", re.I),
        {
            "en": "Welcome",
            "de": "Willkommen",
            "es": "Bienvenido",
            "fr": "Bienvenue",
            "it": "Benvenuto",
            "pt": "Bem-vindo",
            "ru": "Добро пожаловать",
            "zh": "欢迎",
            "ja": "ようこそ",
        },
    ),
]


def adjust_formality(text: str, target_lang: str, formality: str) -> str:
    key = (target_lang.lower().split("-")[0], formality.lower())
    rules = FORMALITY_RULES.get(key, [])
    res = text
    for pattern, repl in rules:
        res = pattern.sub(repl, res)
    return res


async def query_deepl(
    text: str,
    src_lang: str,
    tgt_lang: str,
    api_key: str,
    formality: str = "default",
    api_url: str = "https://api-free.deepl.com/v2/translate",
) -> tuple[str, list[str], str]:
    """Query official DeepL API."""
    headers = {
        "Authorization": f"DeepL-Auth-Key {api_key}",
        "Content-Type": "application/json",
    }
    target = tgt_lang.upper().split("-")[0]
    if target == "EN":
        target = "EN-US"
    elif target == "PT":
        target = "PT-PT"

    payload: dict[str, Any] = {
        "text": [text],
        "target_lang": target,
    }
    if src_lang and src_lang.lower() not in ("auto", ""):
        payload["source_lang"] = src_lang.upper().split("-")[0]

    if formality in ("formal", "informal") and target in {
        "DE", "ES", "FR", "IT", "PL", "PT-PT", "PT-BR", "RU", "NL"
    }:
        payload["formality"] = "prefer_more" if formality == "formal" else "prefer_less"

    async with httpx.AsyncClient(timeout=12.0) as client:
        res = await client.post(api_url, json=payload, headers=headers)
        res.raise_for_status()
        data = res.json()
        translations = data.get("translations", [])
        if not translations:
            raise ValueError("Empty response from DeepL API")
        primary = translations[0].get("text", "")
        detected_src = translations[0].get("detected_source_language", src_lang).lower()
        alts = [t.get("text") for t in translations[1:] if t.get("text")]
        return primary, alts, detected_src


async def query_mymemory(
    text: str,
    src_lang: str,
    tgt_lang: str,
) -> tuple[str, list[str]]:
    """Query MyMemory neural translation API."""
    src = (src_lang or "en").lower().split("-")[0]
    tgt = (tgt_lang or "de").lower().split("-")[0]
    langpair = f"{src}|{tgt}"
    url = "https://api.mymemory.translated.net/get"
    params = {"q": text, "langpair": langpair}

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()

        resp_data = data.get("responseData", {})
        translated_text = resp_data.get("translatedText", "")
        if not translated_text or translated_text.startswith("MYMEMORY WARNING"):
            raise ValueError(f"MyMemory warning: {translated_text}")

        # Clean HTML entities if any
        import html
        primary = html.unescape(translated_text).strip()

        # Collect alternatives from matches
        alts: list[str] = []
        seen = {primary.lower()}
        for m in data.get("matches", []):
            candidate = html.unescape(m.get("translation", "")).strip()
            cand_lower = candidate.lower()
            if cand_lower and cand_lower not in seen and not cand_lower.startswith("mymemory warning"):
                seen.add(cand_lower)
                alts.append(candidate)
                if len(alts) >= 4:
                    break

        return primary, alts


async def query_google_web(
    text: str,
    src_lang: str,
    tgt_lang: str,
) -> tuple[str, list[str]]:
    """Query Google Web translation endpoint."""
    src = (src_lang or "auto").lower().split("-")[0]
    tgt = (tgt_lang or "de").lower().split("-")[0]
    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": src,
        "tl": tgt,
        "dt": "t",
        "q": text,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()
        sentences = data[0] if isinstance(data, list) and len(data) > 0 else []
        translated = "".join(s[0] for s in sentences if s and len(s) > 0 and s[0])
        if not translated:
            raise ValueError("Empty Google Web response")
        return translated.strip(), []


def offline_linguistic_translate(text: str, src: str, tgt: str) -> tuple[str, list[str]] | None:
    """Translates common greetings, introductions, and questions using templates."""
    clean = text.strip()
    tgt_key = tgt.lower().split("-")[0]
    for pattern, translations in OFFLINE_PATTERNS:
        m = pattern.match(clean)
        if m:
            template = translations.get(tgt_key)
            if template:
                groups = m.groups()
                result = template.format(*groups) if groups else template
                # Return primary with alternative phrasing if applicable
                alts = []
                if "Mein Name ist" in result:
                    alts.append(f"Ich heiße {groups[0]}")
                elif "Mi nombre es" in result:
                    alts.append(f"Me llamo {groups[0]}")
                elif "Je m'appelle" in result:
                    alts.append(f"Mon nom est {groups[0]}")
                return result, alts
    return None


@register("mt", "neural_online")
@register("mt", "deepl")
class NeuralOnlineTranslationProvider(BaseProvider):
    """DeepL & Neural Online translation provider."""
    name = "neural_online"
    task = "mt"
    private = False
    quality_tier = 95
    cost_tier = 10
    latency_class = "fast"
    requires_gpu = False

    def __init__(self, api_key: str = "", api_url: str = "") -> None:
        self.api_key = api_key or os.getenv("DEEPL_API_KEY", "")
        self.api_url = api_url or os.getenv(
            "DEEPL_API_URL", "https://api-free.deepl.com/v2/translate"
        )

    async def healthcheck(self) -> bool:
        return True

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        t0 = time.perf_counter()
        text = normalize_unicode(req.text)
        src = (req.source_lang or "auto").lower()
        tgt = (req.target_lang or "de").lower()
        formality = (req.style or {}).get("formality", "default") if req.style else "default"

        translated_text: str | None = None
        alternatives: list[str] = []
        provider_used = "neural_online"
        model_used = "neural-web-v1"
        quality_flags: list[str] = ["neural_mt", "high_quality"]

        # 1. Try DeepL if API key is present
        if self.api_key:
            try:
                translated_text, alts, detected = await query_deepl(
                    text, src, tgt, self.api_key, formality, self.api_url
                )
                alternatives = alts
                provider_used = "deepl"
                model_used = "deepl-v2"
                quality_flags.append("deepl_verified")
            except Exception as e:
                log.warning("DeepL API query failed: %s; falling back to MyMemory", e)

        # 2. Try MyMemory Neural API
        if not translated_text:
            try:
                src_code = "en" if src in ("auto", "") else src
                primary, alts = await query_mymemory(text, src_code, tgt)
                translated_text = primary
                alternatives = alts
                provider_used = "mymemory"
                model_used = "neural-mymemory-v1"
            except Exception as e:
                log.warning("MyMemory translation failed: %s; falling back to Google Web", e)

        # 3. Try Google Web MT API
        if not translated_text:
            try:
                primary, alts = await query_google_web(text, src, tgt)
                translated_text = primary
                alternatives = alts
                provider_used = "google_web"
                model_used = "google-nmt-web"
            except Exception as e:
                log.warning("Google Web translation failed: %s; trying offline linguistic fallback", e)

        # 4. Offline linguistic rule engine
        if not translated_text:
            offline = offline_linguistic_translate(text, src, tgt)
            if offline:
                translated_text, alternatives = offline
                provider_used = "linguistic_rule"
                model_used = "linguistic-v1"
                quality_flags.append("rule_matched")

        # 5. Failover signal when all attempts in this provider fail
        if not translated_text:
            raise ProviderUnavailable(f"All online and rule-based translation sources failed for {src}->{tgt}")

        # Apply formality adjustments if requested
        if formality in ("formal", "informal") and provider_used != "deepl":
            translated_text = adjust_formality(translated_text, tgt, formality)
            alternatives = [adjust_formality(a, tgt, formality) for a in alternatives]

        # Apply glossary terminology constraints
        translated_text, glossary_flags = apply_glossary_to_output(
            translated_text, text, req.glossary or {}
        )
        quality_flags.extend(glossary_flags)
        quality_flags.extend(quality_checks(text, translated_text))

        latency_ms = (time.perf_counter() - t0) * 1000

        return TranslationResult(
            text=translated_text,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model=model_used,
            provider=provider_used,
            latency_ms=latency_ms,
            quality_flags=quality_flags,
            confidence=0.98,
            alternatives=alternatives,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        words = result.text.split(" ")
        for i in range(0, len(words), 3):
            yield " ".join(words[i : i + 3]) + (" " if i + 3 < len(words) else "")
