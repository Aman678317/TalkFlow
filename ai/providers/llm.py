"""LLM providers.

- VLLMProvider: OpenAI-compatible /v1/completions & /v1/chat/completions on a local vLLM
  server (prod path for summary/Q&A/action items). Never a hard dependency.
- ExtractiveAssistant: deterministic extractive summarizer (real algorithm: frequency-scored
  sentence extraction + pattern-based action-item detection). Honest fallback when no LLM is
  configured; outputs are labeled `method: extractive` so nobody mistakes them for generative.
"""
from __future__ import annotations

import re
import time
from collections import Counter

import httpx

from ai.interfaces import ProviderUnavailable


class VLLMProvider:
    name = "vllm"

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def healthy(self) -> bool:
        if not self.base_url:
            return False
        try:
            r = httpx.get(f"{self.base_url}/v1/models", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        if not self.healthy():
            raise ProviderUnavailable(self.name, "vLLM server unreachable")
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": ([{"role": "system", "content": system}] if system else [])
                        + [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": temperature,
        }
        r = httpx.post(f"{self.base_url}/v1/chat/completions", json=payload,
                       timeout=self.timeout)
        if r.status_code != 200:
            raise ProviderUnavailable(self.name, f"HTTP {r.status_code}")
        return r.json()["choices"][0]["message"]["content"]


_STOP = set("""the a an and or but if then else of to in on for with without from at by is are
was were be been being this that these those it its as not no yes you your we our they their he
she his her i me my do does did done have has had will would can could should may might must
about into over under again more most some such than too very just also""".split())


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।。])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


class ExtractiveAssistant:
    """Deterministic extractive summarization — the honest no-LLM path."""
    name = "extractive"

    def healthy(self) -> bool:
        return True

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        # Not a chat model: we only support the assistant task prompts built by
        # services/assistant.py, which embed the transcript after a marker.
        if "TRANSCRIPT_BEGIN" not in prompt:
            raise ProviderUnavailable(self.name, "prompt format unsupported")
        transcript = prompt.split("TRANSCRIPT_BEGIN", 1)[1]
        return self.summarize(transcript)

    def summarize(self, transcript: str, max_sentences: int = 6) -> str:
        sents = _sentences(transcript)
        if not sents:
            return ""
        freq = Counter()
        for s in sents:
            for w in re.findall(r"\w{3,}", s.lower()):
                if w not in _STOP:
                    freq[w] += 1
        if not freq:
            return " ".join(sents[:max_sentences])
        top = max(freq.values())
        scored = []
        for i, s in enumerate(sents):
            words = [w for w in re.findall(r"\w{3,}", s.lower()) if w not in _STOP]
            score = sum(freq[w] / top for w in words) / max(len(words), 1)
            score *= 1.0 + 0.15 * (1 if i == 0 else 0)  # slight lead bias
            scored.append((score, i, s))
        picked = sorted(scored, reverse=True)[:max_sentences]
        picked.sort(key=lambda t: t[1])  # keep original order
        return " ".join(p[2] for p in picked)

    def action_items(self, transcript: str) -> list[dict]:
        patterns = [
            r"(?:^|\s)((?:i |we |you |they |he |she )?(?:will|shall|am going to|'ll)\s+[^.!?।]+[.!?।]?)",
            r"(?:^|\s)((?:please\s+|kindly\s+)[^.!?।]+[.!?।]?)",
            r"(?:^|\s)((?:we need to|i need to|you need to|must|should)\s+[^.!?।]+[.!?।]?)",
            r"(?:^|\s)((?:let'?s|let us)\s+[^.!?।]+[.!?।]?)",
        ]
        items = []
        for s in _sentences(transcript):
            for pat in patterns:
                m = re.search(pat, s, re.IGNORECASE)
                if m:
                    items.append({"text": m.group(1).strip(), "evidence": s.strip()[:200],
                                  "method": "pattern"})
                    break
        return items

    def key_points(self, transcript: str, k: int = 5) -> list[str]:
        summary = self.summarize(transcript, max_sentences=k)
        return [s.strip() for s in _sentences(summary) if s.strip()][:k]
