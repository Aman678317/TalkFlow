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
import inspect
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.errors import ProviderError
from app import metrics as met
from gt_ai.base import BaseProvider
from gt_ai.model_router.router import (
    ModelRouter, ProviderSpec, provider_is_private,
)
from gt_ai.registry import create
from gt_ai.types import (
    AudioChunk, DetectionResult, Intent, NoPrivateProviderAvailable, ProviderUnavailable,
    RouteDecision, Task, TranslationRequest, TranslationResult, TranscriptChunk,
)

log = logging.getLogger("app.ai")

TASKS = (Task.STT, Task.MT, Task.TTS, Task.LANG_DETECT, Task.SUMMARIZE, Task.EMBED)

#: The provider order used when the operator leaves a task on `auto`.
#: LOCAL-FIRST (issue #109 class 3, decision (d)): the default configuration
#: is on-tenant inference — the cloud tier is an explicit operator choice
#: (``TRANSLATION_PROVIDER=neural_online`` etc.), never the implicit head of
#: every request. The list still ends with the dev stand-in so a dev box
#: without weights has something honest to fall back to.
AUTO_PROVIDER_ORDER: dict[Task, list[str]] = {
    Task.MT: ["madlad400", "nllb_ct2", "argos", "airllm",
              "neural_online", "deepl", "mt_http", "dev_echo"],
    Task.STT: ["faster_whisper", "stt_http", "dev_text"],
    Task.TTS: ["kokoro", "piper", "tts_http", "dev_tone"],
    Task.LANG_DETECT: ["fasttext", "langdetect"],
    Task.SUMMARIZE: ["extractive", "llm_http"],
    Task.EMBED: ["sentence_transformers", "hash_tfidf"],
}


async def _open_tts_stream(raw):
    """Turn a provider's ``synthesize_stream`` result into an open stream.

    Providers with missing model extras raise lazily at stream-start (e.g.
    kokoro without ``pip install gt-ai[tts]``), so failover must verify the
    stream OPENS and emits its first chunk, not merely that the provider
    object exists. The first chunk is prefetched here and inlined into the
    returned iterator so consumers see an unopened, ordinary stream. Fakes
    and sync adapters that hand back a ready-made value (or a coroutine
    yielding one) keep the historical pass-through contract.
    """
    stream = await raw if inspect.isawaitable(raw) else raw
    if not isinstance(stream, AsyncIterator):
        return stream
    first = await stream.__anext__()

    def _prefetched(first=first, stream=stream):
        async def _it():
            yield first
            async for chunk in stream:
                yield chunk
        return _it()

    return _prefetched()


class AIFacade:
    def __init__(self) -> None:
        self.router: ModelRouter | None = None
        self._providers: dict[tuple[str, str], BaseProvider] = {}
        self._provider_args: dict[tuple[str, str], dict] = {}
        self._chain_provider_cache: dict[tuple[str, str], BaseProvider] = {}
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
        # Prefer the managed Azure path when its server-side credentials are
        # present. Without credentials, retain the existing local order.
        azure_ready = {
            Task.STT: bool(settings.azure_speech_key and settings.azure_speech_region),
            Task.TTS: bool(settings.azure_speech_key and settings.azure_speech_region),
            Task.MT: bool(
                (settings.azure_translator_key or settings.azure_speech_key)
                and (settings.azure_translator_region or settings.azure_speech_region)
            ),
        }
        if azure_ready.get(task):
            return {
                Task.STT: "azure_speech",
                Task.MT: "azure_translator",
                Task.TTS: "azure_speech_tts",
            }[task]
        # auto: prefer real providers that can healthcheck; dev fallback last.
        # LOCAL-FIRST under `auto` (issue #109 class 3, decision (d)): an
        # operator who wants the cloud tier ranks it explicitly — the
        # default configuration is on-tenant inference, and external
        # providers are the failover hop, not the default destination.
        order = AUTO_PROVIDER_ORDER[task]
        return order[0]  # lazily healthchecked; failover handles the rest

    def _explicitly_configured(self, task: Task) -> str | None:
        """The provider name ONLY when the operator named it explicitly.

        ``_configured_name`` always resolves ``auto`` to a concrete name (the
        local-first default), so ``cfg != "auto"`` was never a real guard and
        the cloud provider picked up the +2000 boost for every request by
        default (sweep finding 5). Only the raw setting counts as operator
        preference.
        """
        env_map = {
            Task.MT: settings.translation_provider,
            Task.STT: settings.stt_provider,
            Task.TTS: settings.tts_provider,
            Task.LANG_DETECT: settings.lang_detect_provider,
            Task.SUMMARIZE: settings.summarization_provider,
            Task.EMBED: settings.embedding_provider,
        }
        raw = (env_map.get(task) or "").strip()
        if raw and raw.lower() != "auto":
            return raw
        return None

    def _provider_kwargs(self, task: Task, name: str) -> dict:
        key = (task.value, name)
        if key in self._provider_args:
            return self._provider_args[key]
        kwargs: dict[str, Any] = {}
        cache = settings.model_cache_path
        if task == Task.MT and name in ("neural_online", "deepl"):
            kwargs = {
                "api_key": getattr(settings, "deepl_api_key", ""),
                "api_url": getattr(settings, "deepl_api_url", "https://api-free.deepl.com/v2/translate"),
            }
        elif task == Task.MT and name == "madlad400":
            kwargs = {"model_id": settings.translation_model or "google/madlad-400-3b-mt",
                      "cache_dir": cache}
        elif task == Task.MT and name == "airllm":
            kwargs = {
                "model_id": settings.airllm_model_id or settings.translation_model,
                "hf_token": settings.airllm_hf_token,
                "layer_shards_saving_path": settings.airllm_layer_shards_path or f"{cache}/airllm",
                "max_input_tokens": settings.airllm_max_input_tokens,
                "max_new_tokens": settings.airllm_max_new_tokens,
            }
        elif task == Task.MT and name == "mt_http":
            kwargs = {"url": settings.mt_http_url, "style": settings.mt_http_style}
        elif task == Task.MT and name in ("azure_translator", "azure_mt", "azure"):
            kwargs = {
                "key": settings.azure_translator_key or settings.azure_speech_key,
                "region": settings.azure_translator_region or settings.azure_speech_region,
                "endpoint": settings.azure_translator_endpoint,
                "api_version": settings.azure_translator_api_version,
            }
        elif task == Task.STT and name == "faster_whisper":
            kwargs = {"model_size": settings.stt_model, "device": settings.stt_device,
                      "compute_type": settings.stt_compute_type, "cache_dir": cache}
        elif task == Task.STT and name == "stt_http":
            kwargs = {"url": settings.stt_http_url}
        elif task == Task.STT and name in ("azure_speech", "azure_stt", "azure_speech_stt"):
            kwargs = {
                "key": settings.azure_speech_key,
                "region": settings.azure_speech_region,
                "default_language": settings.azure_speech_language,
                "auto_detect_languages": settings.azure_speech_auto_detect_languages,
            }
        elif task == Task.TTS and name == "kokoro":
            kwargs = {"model_path": f"{cache}/kokoro-v1.0.onnx",
                      "voices_path": f"{cache}/kokoro-voices.json"}
        elif task == Task.TTS and name == "piper":
            kwargs = {"model_dir": f"{cache}/piper"}
        elif task == Task.TTS and name == "tts_http":
            kwargs = {"url": settings.tts_http_url}
        elif task == Task.TTS and name in ("azure_speech_tts", "azure_tts", "azure_speech"):
            kwargs = {
                "key": settings.azure_speech_key,
                "region": settings.azure_speech_region,
                "voice_map": settings.azure_speech_voice_map,
            }
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

    def _http_private_overrides(self) -> set[str]:
        """Provider names the operator declared on-tenant (the *_HTTP_PRIVATE
        flags). An operator HTTP endpoint posts request content to a URL the
        code cannot verify, so it counts as private ONLY with the explicit
        opt-in (issue #109 class 3, finding 6)."""
        overrides: set[str] = set()
        if settings.mt_http_private:
            overrides.add("mt_http")
        if settings.stt_http_private:
            overrides.add("stt_http")
        if settings.tts_http_private:
            overrides.add("tts_http")
        if settings.llm_http_private:
            overrides.add("llm_http")
        return overrides

    def _effective_private(self, provider: str, seeded: bool,
                           overrides: set[str]) -> bool:
        """The privacy flag the ROUTER must see for this provider.

        The registry row carries the seeded value, but the operator's live
        ``*_HTTP_PRIVATE`` setting is the current statement about that
        endpoint — it wins over a stale seeded row (issue #109 class 3,
        finding 6). Every other provider keeps the registry's own value, so
        an operator who deliberately flipped a row is honored.
        """
        if provider in ("mt_http", "stt_http", "tts_http", "llm_http"):
            return provider in overrides
        return bool(seeded)

    def _fallback_specs(self) -> dict[Task, list[ProviderSpec]]:
        """The spec used for a task the registry knows nothing about.

        Every spec carries the provider's REAL privacy classification — the
        ``ProviderSpec`` dataclass default (``private=True``) used to tell
        the router that a cloud provider was private, so the private_only
        hard filter could not exclude it (sweep finding 4).
        """
        overrides = self._http_private_overrides()

        def _spec(task: Task) -> ProviderSpec:
            name = self._configured_name(task)
            return ProviderSpec(
                name=name, task=task,
                requires_gpu=(task == Task.MT and name == "airllm"),
                private=provider_is_private(name, overrides),
                latency_class=("batch" if (task == Task.MT and name == "airllm")
                               else "fast"),
            )

        return {t: [_spec(t)] for t in TASKS}

    def _apply_priority_policy(self, specs: dict[Task, list[ProviderSpec]]) -> None:
        """Apply the operator-preference policy to the task's specs.

        * an EXPLICITLY named provider is a strong operator preference: it
          gets the +2000 boost, so routing tries it first with the rest of
          the registry as failover;
        * while the task is on `auto`, a NON-private provider is demoted
          (-2000) below the on-tenant ones — the seeded quality tiers alone
          do not guarantee it (the cloud translator is seeded at 95, the
          local madlad400 at 85), so the default configuration would still
          start at the cloud tier. The cloud stays reachable as the failover
          hop; it is simply not the default destination (decision (d)).
        """
        for t in TASKS:
            task_specs = specs.get(t) or []
            explicit = self._explicitly_configured(t)
            if explicit:
                for s in task_specs:
                    if s.name == explicit:
                        s.priority += 2000
            else:
                for s in task_specs:
                    if not s.private:
                        s.priority -= 2000

    async def load_registry(self, db: AsyncSession) -> None:
        """Load provider specs from the DB model registry (source of truth),
        merged with static defaults for anything not yet registered."""
        res = await db.execute(select(M.ModelRegistry).where(M.ModelRegistry.status == "active"))
        rows = res.scalars().all()
        specs: dict[Task, list[ProviderSpec]] = {t: [] for t in TASKS}
        http_overrides = self._http_private_overrides()
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
                latency_class=r.latency_class,
                private=self._effective_private(r.provider, r.private, http_overrides),
                requires_gpu=r.requires_gpu, languages=langs, validated_pairs=pairs,
                domains=set(r.domains_json or {"general"}), priority=r.priority,
            ))
        # ensure at least one spec per task (registry may be empty in tests).
        # Every fallback spec carries its REAL privacy flag (sweep finding 4):
        # the ProviderSpec default (private=True) told the router a cloud
        # provider was private, so the private_only hard filter could not
        # exclude it. The names satisfy _provider_kwargs (explicit configs
        # resolve there; auto resolves to the local-first default).
        fallback_specs = self._fallback_specs()
        for t in TASKS:
            if not specs[t]:
                specs[t] = fallback_specs[t]
            else:
                # configured provider always joins the candidate list — with
                # its real privacy flag; an unnamed "auto" no longer injects
                # a synthetic cloud candidate (it is in the registry or fails
                # over through the extras).
                explicit = self._explicitly_configured(t)
                if explicit and not any(s.name == explicit for s in specs[t]):
                    specs[t].append(ProviderSpec(
                        name=explicit, task=t,
                        private=provider_is_private(explicit, self._http_private_overrides())))
        # The operator-preference policy (explicit boost / local-first under
        # `auto`) is applied once, to the assembled specs.
        self._apply_priority_policy(specs)
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
        # Candidates resolved here (readiness filter below) are handed to
        # _execute through this per-call map so a candidate instance is built
        # exactly once: the filter's resolution is the attempt's provider.
        self._chain_provider_cache.clear()
        order: list[RouteDecision] = []
        tried: set[str] = set()
        touched: list[tuple[Task, str, bool]] = []
        candidates = list(self.router.providers.get(task, []))
        max_attempts = max(10, len(candidates) + 2)
        # "Private only" is a promise: the chain must not end in the online
        # provider, which would send the caller's content to an external
        # service (observed 2026-10-20).
        intent = route_kw.get("intent")
        private_only = getattr(intent, "value", intent) == Intent.PRIVATE_ONLY.value
        try:
            for _ in range(max_attempts):
                try:
                    decision = self.router.route(task, **route_kw)
                except NoPrivateProviderAvailable:
                    # The private pool is exhausted. If the chain already holds
                    # private candidates, that is the END of the chain — the
                    # request continues with them. Only a chain with NO
                    # private candidate at all is the honest failure.
                    if order:
                        break
                    raise
                except Exception:
                    break
                if decision.provider in tried:
                    break
                tried.add(decision.provider)
                order.append(decision)
                t_key = task.value if isinstance(task, Task) else task
                prev_h = self.router.health.get((t_key, decision.provider))
                touched.append((task, decision.provider, prev_h.available if prev_h is not None else True))
                self.router.mark_available(task, decision.provider, False)

            # Providers the router may not have listed, tried after everything it did.
            if task == Task.MT:
                if private_only:
                    # No online fallback for a private_only request.
                    extras: list[tuple[str, str]] = [("dev_echo", "fallback to dev provider")]
                else:
                    extras = [("neural_online", "neural translation provider"),
                              ("dev_echo", "fallback to dev provider")]
            else:
                fallback = {
                    Task.STT: "dev_text",
                    Task.TTS: "dev_tone",
                    Task.LANG_DETECT: "langdetect",
                    Task.SUMMARIZE: "extractive",
                    Task.EMBED: "hash_tfidf",
                }.get(task)
                extras = [(fallback, "fallback provider")] if fallback else []
            for cand, rsn in extras:
                if cand in tried:
                    continue
                # A `dev_*` stand-in echoes source text, transcribes nothing, or
                # plays a tone. Outside production that is how the pipe gets
                # exercised without model weights; in a live meeting the same
                # output would reach listeners as a real translation, so an
                # outage there must stay an outage. An operator who *configures*
                # a dev provider still routes to it — that comes through the
                # registry, not this list.
                if cand.startswith("dev_") and settings.is_production:
                    continue
                order.append(RouteDecision(provider=cand, model=cand, task=task,
                                           reason=rsn))
        finally:
            for t, name, prev in touched:
                t_key = t.value if isinstance(t, Task) else t
                self.router.mark_available(t, name, prev)
                # mark_available reset counters only when flipping to unavailable;
                # ensure original state restored
                h = self.router.health.get((t_key, name))
                if h is not None:
                    h.available = prev

        served: set[object] = set()
        chain: list[RouteDecision] = []
        for decision in order:
            try:
                provider = self.provider(task, decision.provider)
            except Exception:
                # Not registered / not buildable on this install (a test
                # scaffolding name or an adapter whose factory input is
                # absent). Fail open: the name stays in the chain, and the
                # per-attempt deadline bounds whatever it does. A fresh
                # identity keeps two such names from colliding in `served`.
                impl = object()
            else:
                impl = type(provider)
                self._chain_provider_cache[(task.value, decision.provider)] = provider
                try:
                    is_ready = provider.runtime_ready()
                except Exception:
                    # Stand-in without the pre-flight hook (test fakes,
                    # adapters predating the hook): no information either
                    # way — keep it; the bounded attempt decides.
                    is_ready = True
                if not is_ready:
                    log.info("provider %s/%s not runtime-ready "
                             "(deps/weights absent); excluded from chain",
                             task, decision.provider)
                    continue
            if impl in served:
                log.info("candidate %s duplicates an earlier chain slot (%s); "
                         "excluded to avoid retrying the same implementation",
                         decision.provider, getattr(impl, "__name__", impl))
                continue
            served.add(impl)
            chain.append(decision)
        return chain

    async def _execute(self, task: Task, route_kw: dict, call):
        """call(provider) -> result; failover across providers."""
        last_err: Exception | None = None
        intent = route_kw.get("intent")
        private_only = getattr(intent, "value", intent) == Intent.PRIVATE_ONLY.value
        try:
            decisions = self._ordered_candidates(task, route_kw)
        except NoPrivateProviderAvailable as e:
            # Honest failure: the request was NOT sent to any external service.
            raise ProviderError(
                "No private provider is available for this request; the content was "
                "not sent to any external service.",
                details={"task": task.value, "error": str(e)},
            ) from e
        timeout_s = settings.provider_attempt_timeout_s
        for decision in decisions:
            t0 = time.perf_counter()
            try:
                provider = self._chain_provider_cache.get(
                    (task.value, decision.provider))
                if provider is None:
                    provider = self.provider(task, decision.provider)
                attempt = call(provider)
                if timeout_s > 0:
                    # Deadline-first failover (#109(a) P0): a provider attempt
                    # must never own the request forever. Cancelling the await
                    # abandons a stuck attempt (a thread stuck in a native
                    # load keeps running, but the loop — and this request's
                    # failover — stay alive and honest).
                    result = await asyncio.wait_for(attempt, timeout=timeout_s)
                else:
                    result = await attempt
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=True)
                return result, decision
            except asyncio.TimeoutError:
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=False)
                last_err = ProviderUnavailable(
                    f"attempt exceeded the {timeout_s:.1f}s provider deadline")
                met.PROVIDER_RETRIES.labels(
                    stage=task.value, provider=decision.provider).inc()
                log.warning("provider %s/%s exceeded %.1fs attempt deadline; failing over",
                            task, decision.provider, timeout_s)
            except ProviderUnavailable as e:
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=False)
                last_err = e
                met.PROVIDER_RETRIES.labels(
                    stage=task.value, provider=decision.provider).inc()
                log.warning("provider %s/%s unavailable (%s); failing over",
                            task, decision.provider, e)
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=False)
                last_err = e
                met.PROVIDER_RETRIES.labels(
                    stage=task.value, provider=decision.provider).inc()
                met.STAGE_FAILURES.labels(
                    stage=task.value, provider=decision.provider,
                    reason=type(e).__name__).inc()
                log.exception("provider %s/%s failed", task, decision.provider)
        raise ProviderError(
            self._NO_PRIVATE_MSG
            if private_only
            else "AI capability temporarily unavailable. Original content is unaffected.",
            details={"task": task.value, "error": str(last_err),
                     "private_only": private_only})

    # ------------------------------------------------------------------ #
    # Public API used by services / realtime pipeline
    # ------------------------------------------------------------------ #
    async def detect_language(self, text: str, intent: Intent | None = None) -> DetectionResult:
        result, decision = await self._execute(
            Task.LANG_DETECT, {"intent": intent} if intent is not None else {},
            lambda p: p.detect(text))
        met.LANG_DETECT_CONFIDENCE.labels(
            language=result.language or "unknown").observe(result.confidence or 0.0)
        return result

    async def translate(self, req: TranslationRequest,
                        language_capability: Any = None) -> tuple[TranslationResult, RouteDecision]:
        # The tenant-level private flag is a promise, not a provider-name
        # preference (sweep finding 1: the literal "private_only" matched no
        # provider name and the flag had zero effect). Tenant flag wins over
        # any per-request intent.
        intent = Intent.PRIVATE_ONLY if req.tenant_private_only else req.intent
        route_kw: dict = dict(
            source_lang=req.source_lang, target_lang=req.target_lang,
            domain=req.domain, intent=intent,
        )
        result, decision = await self._execute(Task.MT, route_kw, lambda p: p.translate(req))
        pair = (req.source_lang, req.target_lang)
        met.TRANSLATION_LATENCY.labels(src=pair[0], tgt=pair[1],
                                       provider=decision.provider).observe(result.latency_ms)
        met.MT_STAGE_LATENCY.labels(
            src=pair[0] or "auto", tgt=pair[1] or "unknown",
            provider=decision.provider or "unknown",
            model=result.model or "unknown",
        ).observe(result.latency_ms)
        return result, decision

    _NO_PRIVATE_MSG = ("No private provider is available for this request; the "
                       "content was not sent to any external service.")

    async def translate_stream(self, req: TranslationRequest):
        if self.router is None:
            raise ProviderError("AI router not initialized")
        intent = Intent.PRIVATE_ONLY if req.tenant_private_only else req.intent
        try:
            decision = self.router.route(Task.MT, source_lang=req.source_lang,
                                         target_lang=req.target_lang, domain=req.domain,
                                         intent=intent)
        except NoPrivateProviderAvailable as e:
            raise ProviderError(self._NO_PRIVATE_MSG,
                                details={"task": Task.MT.value, "error": str(e)}) from e
        provider = self.provider(Task.MT, decision.provider)
        return provider.translate_stream(req), decision  # type: ignore[attr-defined]

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None,
                         intent: Intent | None = None) -> tuple[TranscriptChunk, RouteDecision]:
        t0 = time.perf_counter()
        result, decision = await self._execute(
            Task.STT, {"intent": intent} if intent is not None else {},
            lambda p: p.transcribe(audio, sample_rate, lang_hint))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        met.STT_LATENCY.labels(provider=decision.provider).observe(elapsed_ms)
        met.STT_STAGE_LATENCY.labels(
            provider=decision.provider or "unknown", stage="final").observe(elapsed_ms)
        return result, decision

    async def synthesize(self, text: str, lang: str,
                         voice: str | None = None,
                         intent: Intent | None = None) -> tuple[AudioChunk, RouteDecision]:
        t0 = time.perf_counter()
        result, decision = await self._execute(
            Task.TTS, {"intent": intent} if intent is not None else {},
            lambda p: p.synthesize(text, lang, voice))
        met.TTS_STAGE_TTFB.labels(
            provider=decision.provider or "unknown", voice=voice or "default",
        ).observe((time.perf_counter() - t0) * 1000)
        return result, decision

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None,
                                intent: Intent | None = None):
        if self.router is None:
            raise ProviderError("AI router not initialized")
        route_kw: dict = {"intent": intent} if intent is not None else {}
        try:
            candidates = self._ordered_candidates(Task.TTS, route_kw)
        except NoPrivateProviderAvailable as e:
            raise ProviderError(self._NO_PRIVATE_MSG,
                                details={"task": Task.TTS.value, "error": str(e)}) from e
        for decision in candidates:
            name = decision.provider
            try:
                provider = self._chain_provider_cache.get(
                    (Task.TTS.value, name))
                if provider is None:
                    provider = self.provider(Task.TTS, name)
                if hasattr(provider, "healthcheck"):
                    ok = await provider.healthcheck()
                    if not ok:
                        continue
                if hasattr(provider, "synthesize_stream"):
                    # `_ordered_candidates` already imposed routing order and
                    # fallthrough (real providers first, dev stand-ins last,
                    # never outside non-production) — route() is consulted
                    # only as the last-resort decision below.
                    stream = await _open_tts_stream(
                        provider.synthesize_stream(text, lang, voice))
                    if not isinstance(stream, AsyncIterator):
                        # Ready-made value, not a stream (sync adapters and
                        # fakes): keep the historical pass-through contract.
                        return stream, decision  # type: ignore[attr-defined,return-value]
                    return stream, decision  # type: ignore[attr-defined]
            except Exception:
                continue
        # In production there is no test-tone stand-in: a generated beep must
        # not be delivered as somebody's translated voice (Phase 5).
        if not settings.is_production:
            try:
                provider = self.provider(Task.TTS, "dev_tone")
                decision = RouteDecision(provider="dev_tone", model="dev_tone",
                                         task=Task.TTS, reason="test-tone fallback")
                stream = await _open_tts_stream(
                    provider.synthesize_stream(text, lang, voice))
                return stream, decision  # type: ignore[attr-defined,return-value]
            except Exception:
                pass
        try:
            decision = self.router.route(Task.TTS, **route_kw)
        except NoPrivateProviderAvailable as e:
            raise ProviderError(self._NO_PRIVATE_MSG,
                                details={"task": Task.TTS.value, "error": str(e)}) from e
        provider = self.provider(Task.TTS, decision.provider)
        stream = await _open_tts_stream(provider.synthesize_stream(text, lang, voice))
        return stream, decision  # type: ignore[attr-defined,return-value]

    async def summarize(self, text: str, instruction: str = "",
                        max_length: int = 400, lang: str = "en",
                        intent: Intent | None = None) -> str:
        result, _ = await self._execute(
            Task.SUMMARIZE, {"intent": intent} if intent is not None else {},
            lambda p: p.summarize(text, instruction, max_length, lang))
        return result

    async def extract_structured(self, text: str, lang: str = "en",
                                 intent: Intent | None = None) -> dict:
        result, _ = await self._execute(
            Task.SUMMARIZE, {"intent": intent} if intent is not None else {},
            lambda p: p.extract_structured(text, lang=lang))
        return result

    async def embed(self, texts: list[str], intent: Intent | None = None) -> list[list[float]]:
        result, _ = await self._execute(
            Task.EMBED, {"intent": intent} if intent is not None else {},
            lambda p: p.embed(texts))
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

    async def diagnostics(self) -> dict[str, Any]:
        """Readiness diagnostics for configured providers, weights, voices, language pairs,
        and OCR availability, strictly without exposing secrets."""
        import os
        import shutil
        from app.realtime.voices import parse_voice_map

        task_diags: dict[str, Any] = {}
        cache = settings.model_cache_path

        for task in TASKS:
            cfg_name = self._configured_name(task)
            provider = self.provider(task, cfg_name)
            is_healthy = False
            try:
                # 1.5s deadline to avoid blocking on large on-demand model weight downloads
                is_healthy = await asyncio.wait_for(provider.healthcheck(), timeout=1.5)
            except Exception:
                is_healthy = False

            weights_loaded = True
            if task == Task.STT and cfg_name == "faster_whisper":
                weights_loaded = os.path.exists(cache)
            elif task == Task.TTS and cfg_name == "kokoro":
                weights_loaded = os.path.exists(f"{cache}/kokoro-v1.0.onnx")
            elif task == Task.TTS and cfg_name == "piper":
                weights_loaded = os.path.exists(f"{cache}/piper")
            elif task == Task.LANG_DETECT and cfg_name == "fasttext":
                weights_loaded = os.path.exists(settings.fasttext_lid_model or f"{cache}/lid.176.ftz")

            fallbacks: list[str] = []
            if self.router and task in self.router.providers:
                fallbacks = [spec.name for spec in self.router.providers[task]]
            if not fallbacks:
                fallbacks = [cfg_name]

            model_info = getattr(settings, f"{task.value.lower()}_model", "")
            if not model_info:
                if task == Task.MT:
                    model_info = settings.translation_model or "google/madlad-400-3b-mt"
                elif task == Task.STT:
                    model_info = settings.stt_model
                elif task == Task.TTS:
                    model_info = settings.tts_model

            task_diags[task.value] = {
                "configured_provider": cfg_name,
                "active_provider": cfg_name,
                "model": model_info,
                "healthy": is_healthy,
                "weights_present": weights_loaded,
                "fallback_chain": fallbacks,
            }

        voice_map = parse_voice_map(settings.tts_voice_map)
        default_voices = {
            "hi": voice_map.get("hi", "hi-IN-SwaraNeural" if "azure" in settings.tts_provider else "hf_alpha"),
            "mr": voice_map.get("mr", "mr-IN-AarohiNeural" if "azure" in settings.tts_provider else "mr_female"),
            "en": voice_map.get("en", "en-US-JennyNeural" if "azure" in settings.tts_provider else "af_heart"),
            "es": voice_map.get("es", "es-ES-ElviraNeural" if "azure" in settings.tts_provider else "ef_dora"),
            "fr": voice_map.get("fr", "fr-FR-DeniseNeural" if "azure" in settings.tts_provider else "ff_siwis"),
        }

        ocr_status = {"available": False, "engine": "none", "details": ""}
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            try:
                _ = page.get_textpage_ocr(language="eng")
                ocr_status["available"] = True
                ocr_status["engine"] = "pymupdf_tesseract"
                ocr_status["details"] = "PyMuPDF integrated Tesseract engine active"
            except Exception as ocr_err:
                tess_bin = shutil.which("tesseract")
                if tess_bin:
                    ocr_status["available"] = True
                    ocr_status["engine"] = f"tesseract_cli:{tess_bin}"
                    ocr_status["details"] = "Tesseract binary found on PATH"
                else:
                    ocr_status["details"] = f"Tesseract not available: {ocr_err}"
            doc.close()
        except Exception as e:
            ocr_status["details"] = f"PyMuPDF not available: {e}"

        # Day-3 (2026-10-23): the diagnostics pair matrix must be the
        # capability registry, not a frozen hand-written seven-language
        # sample. Hub-and-spoke en<->X covers every translation-supported
        # registry language; the count is the size of the advertised matrix.
        from gt_ai.capabilities import DEFAULT_LANGUAGES
        supported = [lc.code for lc in DEFAULT_LANGUAGES if lc.translation_supported]
        core_pairs: list[tuple[str, str]] = []
        for code in supported:
            if code == "en":
                continue
            core_pairs.append(("en", code))
            core_pairs.append((code, "en"))

        return {
            "status": "ready" if all(t["healthy"] for t in task_diags.values()) else "degraded",
            "tasks": task_diags,
            "voices": {
                "voice_map": voice_map,
                "supported_targets": default_voices,
            },
            "ocr": ocr_status,
            "language_pairs": {
                "supported_count": len(core_pairs),
                "core_sample": [f"{s}->{t}" for s, t in core_pairs],
                "languages": sorted(supported),
            },
        }

    def is_dev_mode(self, task: Task) -> bool:
        # `transcript.inject` etc. are dev affordances. The configured name is
        # the operator's preference (often `auto` -> "kokoro"), but at runtime
        # we may have failed over to `dev_*` providers (kokoro model files
        # missing on Render -> dev_tone). Trust the health map, not the
        # configured name — otherwise injection is wrongly disabled in
        # production where STT/TTS silently falls back to dev_*.
        if self.router is not None:
            for (t_key, name), h in self.router.health.items():
                if t_key == task.value and name.startswith("dev_"):
                    if h is None or h.available:
                        return True
        # Non-production environments always count as dev mode so the
        # frontend "Inject test transcript" affordance works in local QA.
        if not settings.is_production:
            return True
        return self._configured_name(task).startswith("dev_")


ai = AIFacade()
