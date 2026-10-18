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
from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.registry import create
from gt_ai.types import (
    AudioChunk, DetectionResult, ProviderUnavailable,
    RouteDecision, Task, TranslationRequest, TranslationResult, TranscriptChunk,
)

log = logging.getLogger("app.ai")

TASKS = (Task.STT, Task.MT, Task.TTS, Task.LANG_DETECT, Task.SUMMARIZE, Task.EMBED)


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
        candidates = list(self.router.providers.get(task, []))
        max_attempts = max(10, len(candidates) + 2)
        try:
            for _ in range(max_attempts):
                try:
                    decision = self.router.route(task, **route_kw)
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
        return order

    async def _execute(self, task: Task, route_kw: dict, call):
        """call(provider) -> result; failover across providers."""
        last_err: Exception | None = None
        for decision in self._ordered_candidates(task, route_kw):
            t0 = time.perf_counter()
            try:
                provider = self.provider(task, decision.provider)
                result = await call(provider)
                latency = (time.perf_counter() - t0) * 1000
                if self.router is not None:
                    self.router.record_outcome(task, decision.provider, latency, ok=True)
                return result, decision
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
            "AI capability temporarily unavailable. Original content is unaffected.",
            details={"task": task.value, "error": str(last_err)})

    # ------------------------------------------------------------------ #
    # Public API used by services / realtime pipeline
    # ------------------------------------------------------------------ #
    async def detect_language(self, text: str) -> DetectionResult:
        result, decision = await self._execute(
            Task.LANG_DETECT, {}, lambda p: p.detect(text))
        met.LANG_DETECT_CONFIDENCE.labels(
            language=result.language or "unknown").observe(result.confidence or 0.0)
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
        met.MT_STAGE_LATENCY.labels(
            src=pair[0] or "auto", tgt=pair[1] or "unknown",
            provider=decision.provider or "unknown",
            model=result.model or "unknown",
        ).observe(result.latency_ms)
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
        elapsed_ms = (time.perf_counter() - t0) * 1000
        met.STT_LATENCY.labels(provider=decision.provider).observe(elapsed_ms)
        met.STT_STAGE_LATENCY.labels(
            provider=decision.provider or "unknown", stage="final").observe(elapsed_ms)
        return result, decision

    async def synthesize(self, text: str, lang: str,
                         voice: str | None = None) -> tuple[AudioChunk, RouteDecision]:
        t0 = time.perf_counter()
        result, decision = await self._execute(
            Task.TTS, {}, lambda p: p.synthesize(text, lang, voice))
        met.TTS_STAGE_TTFB.labels(
            provider=decision.provider or "unknown", voice=voice or "default",
        ).observe((time.perf_counter() - t0) * 1000)
        return result, decision

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        if self.router is None:
            raise ProviderError("AI router not initialized")
        candidates = self._ordered_candidates(Task.TTS, {})
        for decision in candidates:
            name = decision.provider
            try:
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
        decision = self.router.route(Task.TTS)
        provider = self.provider(Task.TTS, decision.provider)
        stream = await _open_tts_stream(provider.synthesize_stream(text, lang, voice))
        return stream, decision  # type: ignore[attr-defined,return-value]

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

        core_pairs = [
            ("en", "hi"), ("hi", "en"),
            ("en", "mr"), ("mr", "en"),
            ("en", "es"), ("es", "en"),
            ("en", "fr"), ("fr", "en"),
            ("en", "de"), ("de", "en"),
            ("en", "ja"), ("ja", "en"),
            ("en", "zh"), ("zh", "en"),
        ]

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
