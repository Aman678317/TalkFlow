"""Optional Azure Translator REST adapter."""
from __future__ import annotations

import time
from typing import AsyncIterator

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranslationRequest, TranslationResult
from gt_ai.translation.text_ops import apply_glossary_to_output, normalize_unicode, quality_checks


_AZURE_LANGUAGE_CODES = {"zh": "zh-Hans", "zh-cn": "zh-Hans", "zh-tw": "zh-Hant"}


def _lang(value: str) -> str:
    normalized = value.strip().replace("_", "-")
    return _AZURE_LANGUAGE_CODES.get(normalized.lower(), normalized)


@register("mt", "azure_translator")
@register("mt", "azure_mt")
@register("mt", "azure")
class AzureTranslatorProvider(BaseProvider):
    name = "azure_translator"
    task = "mt"
    private = False
    quality_tier = 90
    cost_tier = 75
    latency_class = "fast"

    def __init__(self, key: str = "", region: str = "", endpoint: str = "",
                 api_version: str = "3.0", timeout_s: float = 30.0,
                 subscription_key: str | None = None, api_key: str | None = None) -> None:
        supplied_key = subscription_key if subscription_key is not None else api_key
        self.key = (supplied_key if supplied_key is not None else key).strip()
        self.region = region.strip()
        self.endpoint = (endpoint.strip() or "https://api.cognitive.microsofttranslator.com").rstrip("/")
        self.api_version = api_version.strip() or "3.0"
        self.timeout_s = timeout_s

    def _unavailable(self) -> ProviderUnavailable | None:
        if not self.key:
            return ProviderUnavailable("AZURE_TRANSLATOR_KEY or AZURE_SPEECH_KEY not configured")
        if not self.region:
            return ProviderUnavailable("AZURE_TRANSLATOR_REGION or AZURE_SPEECH_REGION not configured")
        return None

    async def healthcheck(self) -> bool:
        return self._unavailable() is None

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        unavailable = self._unavailable()
        if unavailable is not None:
            raise unavailable
        text = normalize_unicode(req.text)
        if not text.strip():
            raise ProviderUnavailable("Azure Translator received empty text")
        params = {"api-version": self.api_version, "to": _lang(req.target_lang)}
        if req.source_lang and req.source_lang.lower() != "auto":
            params["from"] = _lang(req.source_lang)
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Ocp-Apim-Subscription-Region": self.region,
            "Content-Type": "application/json",
        }
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(f"{self.endpoint}/translate", params=params,
                                              headers=headers, json=[{"text": text}])
                response.raise_for_status()
                first = response.json()[0]
                raw = first["translations"][0]["text"]
                detected_source = (first.get("detectedLanguage") or {}).get("language")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderUnavailable(f"Azure Translator failed: {exc}") from exc
        raw, glossary_flags = apply_glossary_to_output(raw, req.text, req.glossary or {})
        raw = raw.strip()
        if not raw:
            raise ProviderUnavailable("Azure Translator returned empty text")
        return TranslationResult(text=raw, source_lang=detected_source or req.source_lang,
                                 target_lang=req.target_lang,
                                 model=f"azure-translator-{self.api_version}", provider=self.name,
                                 latency_ms=(time.perf_counter() - t0) * 1000,
                                 quality_flags=glossary_flags + quality_checks(req.text, raw))

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        yield result.text
