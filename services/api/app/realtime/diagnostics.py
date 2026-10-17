"""Truthful, secret-safe readiness diagnostics for real-time speech.

This module is deliberately observational: it never loads weights, sends audio,
calls external providers, or logs transcripts. "Configured" is not synonymous
with "verified"; a provider is only reported observed-healthy after the router
has recorded successful work for that provider.
"""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

from prometheus_client import REGISTRY

from app.config import settings
from gt_ai.types import Task

_CORE_TASKS = (Task.STT, Task.MT, Task.TTS)
_TASK_SETTING = {
    Task.STT: "stt_provider",
    Task.MT: "translation_provider",
    Task.TTS: "tts_provider",
}
_TASK_MODEL = {
    Task.STT: "stt_model",
    Task.MT: "translation_model",
    Task.TTS: "tts_model",
}
_DEV_PROVIDERS = {"dev_text", "dev_echo", "dev_tone"}
_EXPECTED_METRICS = {
    "gt_realtime_stage_duration_ms": "stage-level latency histogram",
    "gt_realtime_stage_failures_total": "stage-level failure counter",
    "gt_stt_latency_ms": "STT latency histogram",
    "gt_translation_latency_ms": "translation latency histogram",
    "gt_tts_first_audio_ms": "TTS time-to-first-audio histogram",
    "gt_e2e_latency_ms": "end-to-end latency histogram",
    "gt_language_detection_confidence": "language confidence histogram",
    "gt_stale_audio_dropped_total": "stale audio drop counter",
    "gt_translation_failures_total": "translation failure counter",
    "gt_queue_depth": "queue depth gauge",
}


def _registered_metric_names() -> set[str]:
    """Return registered Prometheus family names without inferring observations."""
    try:
        return {family.name for family in REGISTRY.collect()}
    except Exception:
        return set()



def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _provider_instance(ai: Any, task: Task, provider_name: str) -> Any | None:
    return getattr(ai, "_providers", {}).get((task.value, provider_name))


def _provider_observation(ai: Any, task: Task, provider_name: str) -> dict[str, Any]:
    router = getattr(ai, "router", None)
    health = getattr(router, "health", {}) if router is not None else {}
    item = health.get((task.value, provider_name))
    if item is None:
        return {"requests": 0, "errors": 0, "error_rate": 0.0, "available": None,
                "ewma_latency_ms": None, "state": "not_observed"}
    requests = int(getattr(item, "request_count", 0) or 0)
    errors = int(getattr(item, "error_count", 0) or 0)
    available = bool(getattr(item, "available", True))
    error_rate = round(float(getattr(item, "error_rate", 0.0) or 0.0), 4)
    latency = float(getattr(item, "ewma_latency_ms", 0.0) or 0.0)
    state = "not_observed" if requests == 0 else (
        "observed_healthy" if available and errors == 0 else "observed_degraded"
    )
    return {
        "requests": requests,
        "errors": errors,
        "error_rate": error_rate,
        "available": available,
        "ewma_latency_ms": round(latency, 1) if latency else None,
        "state": state,
    }


def _task_configuration(ai: Any, task: Task) -> dict[str, Any]:
    configured = str(getattr(settings, _TASK_SETTING[task], "auto") or "auto")
    preferred = ai._configured_name(task)
    model_setting = str(getattr(settings, _TASK_MODEL[task], "") or "")
    instance = _provider_instance(ai, task, preferred)
    observation = _provider_observation(ai, task, preferred)
    cache = Path(settings.model_cache_path)

    dependency: bool | None = None
    artifacts_present: bool | None = None
    endpoint_configured: bool | None = None
    model_loaded = False
    loaded_voice_count: int | None = None

    if task == Task.STT:
        if preferred == "faster_whisper":
            dependency = _has_module("faster_whisper")
            model_loaded = bool(getattr(instance, "_model", None))
            model_dir = cache / f"models--Systran--faster-whisper-{settings.stt_model}"
            artifacts_present = model_dir.is_dir() and any(model_dir.iterdir())
        elif preferred == "stt_http":
            endpoint_configured = bool(settings.stt_http_url)
            dependency = _has_module("httpx")
        elif preferred == "dev_text":
            dependency = True
        else:
            dependency = None
    elif task == Task.MT:
        if preferred == "mt_http":
            endpoint_configured = bool(settings.mt_http_url)
        elif preferred in {"neural_online", "deepl"}:
            # The online adapter has additional public fallbacks. We report
            # provider configuration, not external service reachability.
            endpoint_configured = True
        elif preferred in {"madlad400", "airllm", "nllb_ct2", "argos"}:
            model_loaded = bool(
                getattr(instance, "_model", None)
                or getattr(instance, "_translator", None)
                or getattr(instance, "_pipeline", None)
            )
            artifacts_present = cache.is_dir() and any(cache.iterdir())
        dependency = None
    elif task == Task.TTS:
        if preferred == "kokoro":
            dependency = _has_module("kokoro_onnx")
            artifacts_present = (
                (cache / "kokoro-v1.0.onnx").is_file()
                and (cache / "kokoro-voices.json").is_file()
            )
            model_loaded = bool(getattr(instance, "_tts", None))
            if model_loaded:
                try:
                    loaded_voice_count = len(instance._voice_names())
                except Exception:
                    loaded_voice_count = None
        elif preferred == "piper":
            dependency = _has_module("piper")
            voice_dir = cache / "piper"
            artifacts_present = voice_dir.is_dir() and any(
                p.suffix == ".onnx" for p in voice_dir.iterdir()
            )
            loaded = getattr(instance, "_voices", None)
            model_loaded = bool(loaded)
            loaded_voice_count = len(loaded) if isinstance(loaded, dict) else None
        elif preferred == "tts_http":
            endpoint_configured = bool(settings.tts_http_url)
            dependency = _has_module("httpx")
        elif preferred == "dev_tone":
            dependency = True

    missing = []
    if endpoint_configured is False:
        missing.append("provider_endpoint_not_configured")
    if dependency is False:
        missing.append("provider_dependency_missing")
    if artifacts_present is False and preferred in {
        "faster_whisper", "kokoro", "piper", "madlad400", "airllm", "nllb_ct2"
    }:
        missing.append("model_artifacts_not_found")
    if settings.is_production and preferred in _DEV_PROVIDERS:
        missing.append("development_provider_forbidden_in_production")

    if missing:
        status = "unavailable"
    elif observation["state"] == "observed_healthy":
        status = "observed_healthy"
    elif observation["state"] == "observed_degraded":
        status = "observed_degraded"
    elif model_loaded:
        status = "loaded_unverified"
    else:
        status = "configured_unverified"

    return {
        "configured_provider": configured,
        "preferred_provider": preferred,
        "model": model_setting or preferred,
        "status": status,
        "model_loaded": model_loaded,
        "dependency_installed": dependency,
        "model_artifacts_present": artifacts_present,
        "endpoint_configured": endpoint_configured,
        "loaded_voice_count": loaded_voice_count,
        "missing_requirements": missing,
        "observation": observation,
    }


def build_realtime_readiness(ai_facade: Any | None = None) -> dict[str, Any]:
    """Build a fast diagnostics snapshot without doing inference or network I/O."""
    if ai_facade is None:
        from app.ai import ai as ai_facade

    providers = {
        task.value: _task_configuration(ai_facade, task)
        for task in _CORE_TASKS
    }
    observed_healthy = all(
        entry["status"] == "observed_healthy" for entry in providers.values()
    )
    unavailable = any(entry["status"] == "unavailable" for entry in providers.values())
    overall = "observed_healthy" if observed_healthy else (
        "unavailable" if unavailable else "degraded_unverified"
    )

    specs = getattr(ai_facade, "_specs", {}) or {}
    pair_set: set[tuple[str, str]] = set()
    language_set: set[str] = set()
    for spec in specs.get(Task.MT, []):
        language_set.update(spec.languages or set())
        pair_set.update(spec.validated_pairs or set())

    voice_map_languages = sorted({
        part.partition("=")[0].strip()
        for part in (settings.tts_voice_map or "").split(",")
        if part.partition("=")[0].strip() and "=" in part
    })

    ocr_enabled = bool(settings.document_ocr_enabled)
    ocr_packages = {
        "pymupdf": _has_module("fitz"),
        "pillow": _has_module("PIL"),
        "pytesseract": _has_module("pytesseract"),
    }
    tesseract_found = bool(shutil.which("tesseract"))
    if not ocr_enabled:
        ocr_status = "disabled"
    elif all(ocr_packages.values()) and tesseract_found:
        ocr_status = "configured_unverified"
    else:
        ocr_status = "unavailable"

    livekit_configured = bool(
        settings.livekit_enabled
        and (settings.livekit_public_url or settings.livekit_url)
        and settings.livekit_api_key
        and settings.livekit_api_secret
    )
    registered = _registered_metric_names()
    metric_inventory = {
        name: {
            "description": description,
            "registered": name in registered,
            "runtime_observed": False,
        }
        for name, description in _EXPECTED_METRICS.items()
    }
    return {
        "overall_state": overall,
        "is_fully_verified": observed_healthy,
        "verification_mode": "passive_snapshot_no_external_probes",
        "providers": providers,
        "language_capabilities": {
            "registered_languages": sorted(language_set),
            "validated_translation_pairs": [
                {"source": source, "target": target}
                for source, target in sorted(pair_set)
            ],
            "note": "Only model-registry capabilities explicitly marked validated are listed.",
        },
        "tts": {
            "configured_voice_map_languages": voice_map_languages,
            "loaded_voice_count": providers["tts"]["loaded_voice_count"],
        },
        "media": {
            "livekit_enabled": bool(settings.livekit_enabled),
            "livekit_credentials_configured": livekit_configured,
            "livekit_connection_verified": False,
            "note": "LiveKit connectivity and TURN/ICE are not probed by this endpoint.",
        },
        "document_ocr": {
            "enabled": ocr_enabled,
            "status": ocr_status,
            "python_packages": ocr_packages,
            "tesseract_binary_found": tesseract_found,
        },
        "metrics": {
            "endpoint": "/metrics",
            "expected_inventory": metric_inventory,
            "missing_expected_metrics": sorted(set(_EXPECTED_METRICS) - registered),
            "quantiles": "Use Prometheus histogram_quantile(0.50|0.95|0.99, ...) over histogram buckets.",
            "runtime_note": "Registration confirms metric definitions, not nonzero observations; inspect /metrics samples for live traffic.",
        },
        "tracing": {
            "websocket_request_id_supported": True,
            "websocket_trace_id_supported": True,
            "ids_generated_when_missing": True,
            "cross_stage_propagation_runtime_verified": False,
        },
        "privacy": {
            "secrets_included": False,
            "audio_or_transcript_text_included": False,
        },
    }
