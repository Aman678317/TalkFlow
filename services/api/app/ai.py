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
import importlib.util
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

# Each local-model adapter defers its heavy `import` until first use, so a build
# whose requirements omit the package still registers the provider and still
# answers with its name. This table is the only place that records which module
# each provider is waiting for, which is what lets a deployment report the runtimes
# it actually has instead of the ones it was configured to prefer. Providers not
# listed here need no local model package.
_RUNTIME_MODULE = {
    "faster_whisper": "faster_whisper",
    "piper": "piper",
    "kokoro": "kokoro_onnx",
    "argos": "argostranslate",
    "nllb_ct2": "ctranslate2",
    "madlad400": "transformers",
    "sentence_transformers": "sentence_transformers",
    "fasttext": "fasttext",
    "langdetect": "langdetect",
}

# Providers whose work happens outside this process, with the setting that has to
# be non-empty before they can do anything. `neural_online` is absent because it
# needs neither a key nor a URL — it cascades over public web endpoints.
_REMOTE_REQUIREMENT = {
    "stt_http": "stt_http_url",
    "mt_http": "mt_http_url",
    "tts_http": "tts_http_url",
    "llm_http": "llm_http_url",
    "deepl": "deepl_api_key",
}

#: Network providers that need no configuration of their own to be reachable.
_NETWORK_ONLY = frozenset({"neural_online"})


def _module_present(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


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
            Task.MT: ["neural_online", "deepl", "airllm", "madlad400", "nllb_ct2", "argos", "mt_http", "dev_echo"],
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
            Task.MT: [ProviderSpec(
                name=self._configured_name(Task.MT), task=Task.MT,
                requires_gpu=self._configured_name(Task.MT) == "airllm",
                private=self._configured_name(Task.MT) == "airllm",
                latency_class="batch" if self._configured_name(Task.MT) == "airllm" else "fast",
            )],
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
        # A registry reload must not erase what the last hour of calls proved:
        # the health records and the open circuits are the process's memory of
        # which providers answer on this host.
        health = self.router.health if self.router else {}
        breakers = self.router.breakers if self.router else {}
        self.router = ModelRouter(specs, gpu_available=settings.gpu_available,
                                  health=health, breakers=breakers,
                                  breaker_cooldown_s=settings.provider_cooldown_s,
                                  breaker_max_cooldown_s=settings.provider_max_cooldown_s)
        log.info("model registry loaded: %s",
                 {t.value: [s.name for s in specs[t]] for t in TASKS})

    # ------------------------------------------------------------------ #
    # Routed execution with failover
    # ------------------------------------------------------------------ #
    def _ordered_candidates(self, task: Task, route_kw: dict) -> list[RouteDecision]:
        """Ask the router for its best route, then for the next best, and so on.

        Walking is done by excluding tried providers from the routing call, not
        by marking them unhealthy. The version this replaces flipped
        `available` to make the router move on and restored it afterwards —
        which zeroed every candidate's health counters on every failover, so the
        error rate the circuit breaker reads described how many candidates this
        request happened to have rather than how often the provider failed.
        """
        assert self.router is not None
        order: list[RouteDecision] = []
        tried: set[str] = set()
        candidates = list(self.router.providers.get(task, []))
        for _ in range(max(10, len(candidates) + 2)):
            try:
                decision = self.router.route(task, exclude=frozenset(tried),
                                             **route_kw)
            except Exception:
                break
            tried.add(decision.provider)
            order.append(decision)

        # The last resort is named here because it is not in the registry: an
        # online translator with no key configured, and the local dev stand-in.
        # The network one obeys the circuit breaker — a public endpoint that is
        # down should cost the room one timeout, not one per turn forever. The
        # local one does not: it is what answers when everything else has
        # tripped, and refusing it fast is cheaper than reasoning about it.
        if task == Task.MT:
            last = [("neural_online", "neural translation provider", True),
                    ("dev_echo", "fallback to dev provider", False)]
        else:
            dev_fallback = {
                Task.STT: "dev_text",
                Task.TTS: "dev_tone",
                Task.LANG_DETECT: "langdetect",
                Task.SUMMARIZE: "extractive",
                Task.EMBED: "hash_tfidf",
            }.get(task)
            last = [(dev_fallback, "fallback provider", False)] if dev_fallback else []
        for cand, rsn, obey_breaker in last:
            if cand and cand not in tried and (
                    not obey_breaker or not self.router.circuit_open(task, cand)):
                order.append(RouteDecision(provider=cand, model=cand,
                                           task=task, reason=rsn))
        return order

    async def _execute(self, task: Task, route_kw: dict, call):
        """call(provider) -> result; failover across providers, on a clock.

        The deadline is what makes the failover reachable. The loop moves on when
        a provider *raises*, and a provider that accepts the request and then
        stalls never does: without a ceiling, one wedged candidate is the end of
        the walk, and the candidates behind it — including the local fallback —
        are never tried.
        """
        last_err: Exception | None = None
        budget = settings.ai_retry_budget_s
        cap = settings.ai_timeout_s
        started = time.perf_counter()
        for decision in self._ordered_candidates(task, route_kw):
            elapsed = time.perf_counter() - started
            remaining = budget - elapsed
            if remaining <= 0:
                last_err = last_err or TimeoutError(
                    f"retry budget of {budget:.1f}s exhausted")
                log.warning("AI %s: retry budget of %.1fs exhausted after %.1fs; "
                            "not trying further candidates", task, budget, elapsed)
                break
            t0 = time.perf_counter()
            try:
                provider = self.provider(task, decision.provider)
                result = await asyncio.wait_for(call(provider),
                                                min(cap, remaining))
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=True)
                return result, decision
            except ProviderUnavailable as e:
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=False)
                last_err = e
                log.warning("provider %s/%s unavailable (%s); failing over",
                            task, decision.provider, e)
            except TimeoutError as e:
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=False)
                # `e` is empty for a wait_for cancellation; name what was cut, so
                # the log says which provider to go and look at.
                last_err = TimeoutError(
                    f"{task}/{decision.provider} did not answer within {cap:.1f}s")
                log.warning("provider %s/%s timed out after %.1fs; failing over",
                            task, decision.provider, latency / 1000)
            except Exception as e:
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
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
        if self.router is None:
            raise ProviderError("AI router not initialized")
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
        """Return (chunk iterator, decision) for the first voice that answers.

        A stream is committed to once it is handed out: Agent 3 is already
        waiting on its first frame and the room is waiting on Agent 3, so a
        provider that only fails when somebody pulls a frame leaves the caller
        with no candidate to fall back to. Checking here is cheap and is the last
        moment the choice can still be changed.
        """
        if self.router is None:
            raise ProviderError("AI router not initialized")
        for decision in self._ordered_candidates(Task.TTS, {}):
            name = decision.provider
            if self.router.circuit_open(Task.TTS, name):
                continue
            try:
                provider = self.provider(Task.TTS, name)
                if not hasattr(provider, "synthesize_stream"):
                    self.router.trip(Task.TTS, name, "cannot stream audio")
                    continue
                if hasattr(provider, "healthcheck") and not await provider.healthcheck():
                    # A voice that will not answer a healthcheck is not going to
                    # answer the room either, and it is asked again on the next
                    # turn unless something remembers. This host was paying two
                    # refused probes per turn for a Piper and a Kokoro that are
                    # not installed.
                    self.router.trip(Task.TTS, name, "healthcheck refused")
                    continue
                return provider.synthesize_stream(text, lang, voice), decision
            except Exception as exc:
                self.router.trip(Task.TTS, name, f"unusable: {type(exc).__name__}")
                log.warning("TTS stream candidate %s unusable: %s", name, exc)
        # Saying so is the useful failure. Returning a stream that dies on the
        # first frame turns "no voice on this host" into a per-turn mystery.
        raise ProviderError(
            "No text-to-speech voice is available. Translated captions remain "
            "active.", details={"task": Task.TTS.value})

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

    def runtime_report(self) -> dict[str, dict[str, str]]:
        """Per task: the configured provider and whether this process can run it.

        Answers the question `_configured_name()` alone cannot: an operator
        setting of `auto` resolves to the head of a preference list, so a build
        that installs no speech runtime still reported `faster_whisper` while
        every call fell through to the dev stand-in.

        `importable` means the package is in the image and nothing more —
        weights, voice files, API keys and a loadable onnxruntime are proven only
        when a stage actually runs, which is what `health()` and the stage
        counters report.
        """
        out: dict[str, dict[str, str]] = {}
        for task in TASKS:
            name = self._configured_name(task)
            if name.startswith("dev_"):
                runtime = "dev_stand_in"
            elif name in _REMOTE_REQUIREMENT:
                runtime = ("remote" if getattr(settings, _REMOTE_REQUIREMENT[name], "")
                           else "remote_unconfigured")
            elif name in _RUNTIME_MODULE:
                runtime = ("importable" if _module_present(_RUNTIME_MODULE[name])
                           else "missing")
            else:
                runtime = "remote" if name in _NETWORK_ONLY else "builtin"
            out[task.value] = {"provider": name, "runtime": runtime}
        return out

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
