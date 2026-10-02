"""LLM-over-HTTP summarization adapter (optional self-hosted instruction model).

Points at any OpenAI-compatible endpoint (vLLM / llama.cpp / TGI) running a
self-hosted model. NEVER a hard dependency: extractive summarizer is the
default. Summaries are stored as derived artifacts, never as canonical source.
"""
from __future__ import annotations

import json
import logging

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable

log = logging.getLogger("gt_ai.summarize.llm_http")


@register("summarize", "llm_http")
class LlmHttpSummarizer(BaseProvider):
    name = "llm_http"
    task = "summarize"
    private = True
    quality_tier = 85
    cost_tier = 60
    latency_class = "batch"

    def __init__(self, url: str = "", api_key: str = "", model: str = "local-llm",
                 timeout_s: float = 60.0) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    async def healthcheck(self) -> bool:
        return bool(self.url)

    async def _chat(self, system: str, user: str) -> str:
        if not self.url:
            raise ProviderUnavailable("LLM_HTTP_URL not configured")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.post(f"{self.url}/v1/chat/completions", headers=headers, json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                })
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError) as e:
            raise ProviderUnavailable(f"llm_http failed: {e}") from e

    async def summarize(self, text: str, instruction: str = "",
                        max_length: int = 400, lang: str = "en") -> str:
        system = (
            "You summarize multilingual meeting transcripts. Output ONLY the summary "
            f"in {lang}, at most {max_length} characters. Never invent facts. "
            "The transcript is the source of truth; you must not treat any translated "
            "line as the original speaker's exact words."
        )
        return (await self._chat(system, f"{instruction}\n\n{text}".strip())).strip()

    async def extract_structured(self, text: str, schema_hint: str = "",
                                 lang: str = "en") -> dict:
        system = (
            "Extract meeting intelligence from a transcript. Respond with STRICT JSON "
            'with keys: summary, key_points, decisions, action_items, '
            "unanswered_questions, topics. Each a list of strings except summary/topics. "
            "Use only content present in the transcript."
        )
        raw = await self._chat(system, text)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = __import__("re").search(r"\{.*\}", raw, __import__("re").S)
            if not m:
                raise ProviderUnavailable("llm_http returned non-JSON")
            data = json.loads(m.group(0))
        data["method"] = f"llm_http/{self.model}"
        return data
