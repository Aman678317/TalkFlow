"""HTTP MT adapter — talk to any self-hosted OpenAI-compatible / OpenNMT /
TGI / vLLM translation service. Keeps the app provider-neutral: the actual
engine runs behind an internal URL with secrets server-side only.
"""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranslationRequest, TranslationResult
from gt_ai.translation.text_ops import (
    apply_glossary_to_output,
    normalize_unicode,
    quality_checks,
)

log = logging.getLogger("gt_ai.mt.http")


@register("mt", "mt_http")
class HttpMtProvider(BaseProvider):
    name = "mt_http"
    task = "mt"
    private = True   # points at tenant-internal service by default
    quality_tier = 70
    cost_tier = 30
    latency_class = "fast"

    def __init__(self, url: str = "", api_key: str = "", timeout_s: float = 30.0,
                 style: str = "opennmt") -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.style = style  # opennmt | chat

    async def healthcheck(self) -> bool:
        if not self.url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self.url}/health")
                return r.status_code < 500
        except Exception:
            return False

    def _build_payload(self, req: TranslationRequest) -> tuple[str, dict, dict]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        text = normalize_unicode(req.text)
        glossary_hint = ""
        if req.glossary:
            pairs = "; ".join(f"{k} => {v}" for k, v in list(req.glossary.items())[:20])
            glossary_hint = f"\nTerminology constraints (must follow): {pairs}"
        style_hint = ""
        if req.style:
            style_hint = (
                f"\nStyle: tone={req.style.get('tone', 'neutral')} "
                f"formality={req.style.get('formality', 'neutral')} "
                f"domain={req.style.get('domain', 'general')}"
            )
        if self.style == "chat":
            payload = {
                "model": req.target_lang,
                "messages": [
                    {"role": "system", "content":
                        f"You are a professional {req.source_lang}->{req.target_lang} "
                        f"translator for the {req.domain} domain. Translate exactly, "
                        f"preserving numbers, names, URLs.{style_hint}{glossary_hint}"},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
                "max_tokens": min(2048, max(64, len(text) + 128)),
            }
            return f"{self.url}/v1/chat/completions", payload, headers
        payload = {
            "src": text,
            "src_lang": req.source_lang if req.source_lang != "auto" else None,
            "tgt_lang": req.target_lang,
        }
        return f"{self.url}/translator/translate", payload, headers

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        if not self.url:
            raise ProviderUnavailable("MT_HTTP_URL not configured")
        url, payload, headers = self._build_payload(req)
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"mt_http request failed: {e}") from e
        if self.style == "chat":
            raw = data["choices"][0]["message"]["content"]
        else:
            raw = data.get("tgt") or data.get("translation") or data.get("text", "")
        flags: list[str] = []
        raw, gflags = apply_glossary_to_output(raw, req.text, req.glossary or {})
        flags.extend(gflags)
        flags.extend(quality_checks(req.text, raw))
        return TranslationResult(
            text=raw.strip(),
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model=f"mt_http({self.style})",
            provider=self.name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            quality_flags=flags,
        )

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        result = await self.translate(req)
        yield result.text
