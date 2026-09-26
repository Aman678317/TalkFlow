"""AI facade — the ONLY place application code touches AI.

Application -> AIFacade -> ModelRouter -> provider adapter -> actual model

Responsibilities:
- build provider instances lazily from config + DB model registry
- route every task through the ModelRouter (intent, capability, health)
- provider failover: on ProviderUnavailable, re-route to next candidate
- health tracking + metrics + warm pools
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.errors import ProviderError
from app import metrics as met
from gt_ai.base import BaseProvider
from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.registry import create
from gt_ai.types import (
    AudioChunk, DetectionResult, Intent, ProviderHealth, ProviderUnavailable,
    RouteDecision, Task, TranslationRequest, TranslationResult, TranscriptChunk,
)

log = logging.getLogger("app.ai")

TASKS = (Task.STT, Task.MT, Task.TTS, Task.LANG_DETECT, Task.SUMMARIZE, Task.EMBED)


class AIFacade:
    def __init__(self) -> None:
        self.router: ModelRouter | None = None
        self._providers: dict[tuple[str, str], BaseProvider] = {}
        self._provider_args: dict[tuple[str, str], dict] = {}
        self._specs: dict[Task, list[ProviderSpec]] = {t: [] for t in TASKS}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Configuration
    # ------------------------------------------------------------------ #
    def _configured_name(self, task: Task) -> str:
        env_map = {
            Task.MT: settings.translation_provider,
            Task.STT: settings.stt_provider,
            Task.TTS: settings.tts_provider,
            Task.LANG_DETECT: settings.lang_detect_provider,
            Task.SUMMARIZE: settings.summarization_provider,
            Task.EMBED: settings.embedding_provider,
        }
        name = env_map.get(task, "auto") or "auto"
        if name != "auto":
            return name
        # auto: prefer real providers that can healthcheck; dev fallback last
        order = {
            Task.MT: ["madlad400", "nllb_ct2", "argos", "mt_http", "dev_echo"],
            Task.STT: ["faster_whisper", "stt_http", "dev_text"],
            Task.TTS: ["kokoro", "piper", "tts_http", "dev_tone"],
            Task.LANG_DETECT: ["fasttext", "langdetect"],
            Task.SUMMARIZE: ["llm_http", "extractive"],
            Task.EMBED: ["sentence_transformers", "hash_tfidf"],
        }[task]
        return order[0]  # lazily healthchecked; failover handles the rest

    def _provider_kwargs(self, task: Task, name: str) -> dict:
        key = (task.value, name)
        if key in self._provider_args:
            return self._provider_args[key]
        kwargs: dict[str, Any] = {}
        cache = settings.model_cache_path
        if task == Task.MT and name == "madlad400":
            kwargs = {"model_id": settings.translation_model or "google/madlad-400-3b-mt",
                      "cache_dir": cache}
        elif task == Task.MT and name == "mt_http":
            kwargs = {"url": settings.mt_http_url, "style": settings.mt_http_style}
        elif task == Task.STT and name == "faster_whisper":
            kwargs = {"model_size": settings.stt_model, "device": settings.stt_device,
                      "compute_type": settings.stt_compute_type, "cache_dir": cache}
        elif task == Task.STT and name == "stt_http":
            kwargs = {"url": settings.stt_http_url}
        elif task == Task.TTS and name == "kokoro":
            kwargs = {"model_path": f"{cache}/kokoro-v1.0.onnx",
                      "voices_path": f"{cache}/kokoro-voices.json"}
        elif task == Task.TTS and name == "piper":
            kwargs = {"model_dir": f"{cache}/piper"}
        elif task == Task.TTS and name == "tts_http":
            kwargs = {"url": settings.tts_http_url}
        elif task == Task.LANG_DETECT and name == "fasttext":
            kwargs = {"model_path": settings.fasttext_lid_model or f"{cache}/lid.176.ftz"}
        elif task == Task.SUMMARIZE and name == "llm_http":
            kwargs = {"url": settings.llm_http_url, "model": settings.llm_model}
        elif task == Task.EMBED and name == "sentence_transformers":
            kwargs = {"model_id": settings.embedding_model or "intfloat/multilingual-e5-small",
                      "cache_dir": cache}
        self._provider_args[key] = kwargs
        return kwargs

    def provider(self, task: Task, name: str) -> BaseProvider:
        key = (task.value, name)
        if key not in self._providers:
            self._providers[key] = create(task.value, name,
                                          **self._provider_kwargs(task, name))
        return self._providers[key]

    async def load_registry(self, db: AsyncSession) -> None:
        """Load provider specs from the DB model registry (source of truth),
        merged with static defaults for anything not yet registered."""
        res = await db.execute(select(M.ModelRegistry).where(M.ModelRegistry.status == "active"))
        rows = res.scalars().all()
        specs: dict[Task, list[ProviderSpec]] = {t: [] for t in TASKS}
        for r in rows:
            try:
                task = Task(r.task)
            except ValueError:
                continue
            langs = set(r.languages_json) if r.languages_json else None
            pairs = {(p[0], p[1]) for p in (r.validated_pairs_json or []) if len(p) == 2}
            specs[task].append(ProviderSpec(
                name=r.provider, model=r.config_json.get("model", r.name),
                task=task, quality_tier=r.quality_tier, cost_tier=r.cost_tier,
                latency_class=r.latency_class, private=r.private,
                requires_gpu=r.requires_gpu, languages=langs, validated_pairs=pairs,
                domains=set(r.domains_json or {"general"}), priority=r.priority,
            ))
        # ensure at least one spec per task (registry may be empty in tests)
        fallback_specs = {
            Task.MT: [ProviderSpec(name=self._configured_name(Task.MT), task=Task.MT)],
            Task.STT: [ProviderSpec(name=self._configured_name(Task.STT), task=Task.STT)],
            Task.TTS: [ProviderSpec(name=self._configured_name(Task.TTS), task=Task.TTS)],
            Task.LANG_DETECT: [ProviderSpec(name=self._configured_name(Task.LANG_DETECT),
                                            task=Task.LANG_DETECT)],
            Task.SUMMARIZE: [ProviderSpec(name=self._configured_name(Task.SUMMARIZE),
                                          task=Task.SUMMARIZE)],
            Task.EMBED: [ProviderSpec(name=self._configured_name(Task.EMBED), task=Task.EMBED)],
        }
        for t in TASKS:
            if not specs[t]:
                specs[t] = fallback_specs[t]
            else:
                # configured provider always joins the candidate list
                cfg = self._configured_name(t)
                if cfg != "auto" and not any(s.name == cfg for s in specs[t]):
                    specs[t].append(ProviderSpec(name=cfg, task=t))
            # explicit (non-auto) configuration is a strong operator preference:
            # boost its priority so routing tries it first, with the rest of the
            # registry as failover candidates.
            cfg = self._configured_name(t)
            if cfg != "auto":
                for s in specs[t]:
                    if s.name == cfg:
                        s.priority += 2000
        self._specs = specs
        health = self.router.health if self.router else {}
        self.router = ModelRouter(specs, gpu_available=settings.gpu_available, health=health)
        log.info("model registry loaded: %s",
                 {t.value: [s.name for s in specs[t]] for t in TASKS})

    # ------------------------------------------------------------------ #
    # Routed execution with failover
    # ------------------------------------------------------------------ #
    def _ordered_candidates(self, task: Task, route_kw: dict) -> list[RouteDecision]:
        """Ask the router for a decision, then re-rank excluding providers we
        already tried. Health is restored after routing so long-term state is
        not corrupted by a single request's failover."""
        assert self.router is not None
        order: list[RouteDecision] = []
        tried: set[str] = set()
        touched: list[tuple[Task, str, bool]] = []
        try:
            for _ in range(4):
                decision = self.router.route(task, **route_kw)
                if decision.provider in tried:
                    break
                tried.add(decision.provider)
                order.append(decision)
                touched.append((task, decision.provider,
                                self.router.health.get((task, decision.provider),
                                                       ProviderHealth()).available))
                self.router.mark_available(task, decision.provider, False)
        finally:
            for t, name, prev in touched:
                self.router.mark_available(t, name, prev)
                # mark_available reset counters only when flipping to unavailable;
                # ensure original state restored
                h = self.router.health.get((t, name))
                if h is not None:
                    h.available = prev
        return order

    async def _execute(self, task: Task, route_kw: dict, call):
        """call(provider) -> result; failover across providers."""
        last_err: Exception | None = None
        for decision in self._ordered_candidates(task, route_kw):
            provider = self.provider(task, decision.provider)
            t0 = time.perf_counter()
            try:
                result = await call(provider)
                latency = (time.perf_counter() - t0) * 1000
                self.router.record_outcome(task, decision.provider, latency, ok=True)
                return result, decision
            except ProviderUnavailable as e:
                latency = (time.perf_counter() - t0) * 1000
                self.router.record_outcome(task, decision.provider, latency, ok=False)
                last_err = e
                log.warning("provider %s/%s unavailable (%s); failing over",
                            task, decision.provider, e)
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                self.router.record_outcome(task, decision.provider, latency, ok=False)
                last_err = e
                log.exception("provider %s/%s failed", task, decision.provider)
        raise ProviderError(
            "AI capability temporarily unavailable. Original content is unaffected.",
            details={"task": task.value, "error": str(last_err)})

    # ------------------------------------------------------------------ #
    # Public API used by services / realtime pipeline
    # ------------------------------------------------------------------ #
    async def detect_language(self, text: str) -> DetectionResult:
        result, decision = await self._execute(
            Task.LANG_DETECT, {}, lambda p: p.detect(text))
        return result

    async def translate(self, req: TranslationRequest,
                        language_capability: Any = None) -> tuple[TranslationResult, RouteDecision]:
        route_kw: dict = dict(
            source_lang=req.source_lang, target_lang=req.target_lang,
            domain=req.domain, intent=req.intent,
            tenant_preference=req.tenant_private_only and "private_only" or None,
        )
        result, decision = await self._execute(Task.MT, route_kw, lambda p: p.translate(req))
        pair = (req.source_lang, req.target_lang)
        met.TRANSLATION_LATENCY.labels(src=pair[0], tgt=pair[1],
                                       provider=decision.provider).observe(result.latency_ms)
        return result, decision

    async def translate_stream(self, req: TranslationRequest):
        decision = self.router.route(Task.MT, source_lang=req.source_lang,
                                     target_lang=req.target_lang, domain=req.domain,
                                     intent=req.intent)
        provider = self.provider(Task.MT, decision.provider)
        return provider.translate_stream(req), decision  # type: ignore[attr-defined]

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None) -> tuple[TranscriptChunk, RouteDecision]:
        t0 = time.perf_counter()
        result, decision = await self._execute(
            Task.STT, {}, lambda p: p.transcribe(audio, sample_rate, lang_hint))
        met.STT_LATENCY.labels(provider=decision.provider).observe(
            (time.perf_counter() - t0) * 1000)
        return result, decision

    async def synthesize(self, text: str, lang: str,
                         voice: str | None = None) -> tuple[AudioChunk, RouteDecision]:
        result, decision = await self._execute(
            Task.TTS, {}, lambda p: p.synthesize(text, lang, voice))
        return result, decision

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        decision = self.router.route(Task.TTS)
        provider = self.provider(Task.TTS, decision.provider)
        return provider.synthesize_stream(text, lang, voice), decision  # type: ignore[attr-defined]

    async def summarize(self, text: str, instruction: str = "",
                        max_length: int = 400, lang: str = "en") -> str:
        result, _ = await self._execute(
            Task.SUMMARIZE, {},
            lambda p: p.summarize(text, instruction, max_length, lang))
        return result

    async def extract_structured(self, text: str, lang: str = "en") -> dict:
        result, _ = await self._execute(
            Task.SUMMARIZE, {}, lambda p: p.extract_structured(text, lang=lang))
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result, _ = await self._execute(Task.EMBED, {}, lambda p: p.embed(texts))
        return result

    # ------------------------------------------------------------------ #
    async def warmup(self) -> None:
        """Model warm pool: pre-load configured providers (best effort)."""
        async def _warm(task: Task):
            name = self._configured_name(task)
            try:
                await self.provider(task, name).warmup()
            except Exception as e:
                log.info("warmup %s/%s skipped: %s", task, name, e)
        await asyncio.gather(*[_warm(t) for t in TASKS], return_exceptions=True)

    async def health(self) -> dict[str, Any]:
        assert self.router is not None
        out: dict[str, Any] = {}
        for task in TASKS:
            name = self._configured_name(task)
            provider = self.provider(task, name)
            ok = False
            try:
                ok = await provider.healthcheck()
            except Exception:
                ok = False
            out[task.value] = {"provider": name, "healthy": ok}
        return out

    def is_dev_mode(self, task: Task) -> bool:
        name = self._configured_name(task)
        return name.startswith("dev_")


ai = AIFacade()
