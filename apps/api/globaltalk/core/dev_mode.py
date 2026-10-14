"""is_dev_mode helper: trust the runtime provider chain, not just the configured name.

`transcript.inject` is a dev affordance for exercising the realtime pipeline
without STT weights. It used to be gated only on `is_production` + the
configured provider name. That broke production: when faster-whisper isn't
installed and STT silently fails over to `dev_text` (empty transcripts),
`is_dev_mode` returned False and injection was wrongly disabled.

This module checks the runtime ModelRouter health map first. If ANY
healthy dev_* provider is reachable for the task, the operator's intent
is "I'm running in dev/auto-fallback mode" — and we should expose the
dev affordances.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai.model_router.router import ModelRouter

from globaltalk.core.config import settings

# Map Tree A Task enum values to Tree B task strings.
_TASK_KEYS = {"stt": "stt", "mt": "mt", "tts": "tts"}


def is_dev_mode(task: str) -> bool:
    """True iff the runtime is in dev/fallback mode for this task.

    Args:
        task: "stt" | "mt" | "tts" | "langid" | "llm" | "embedding"
    """
    router = _get_router_safely()
    if router is not None:
        for (t_key, name), h in router.health.items():
            if t_key != task:
                continue
            if not name.startswith("dev_"):
                continue
            if h is None or getattr(h, "available", True):
                return True
    if (getattr(settings, "app_env", "development") or "development") != "production":
        return True
    configured = _configured_name(task)
    return configured.startswith("dev_")


def _get_router_safely() -> "ModelRouter | None":
    try:
        from ai.bootstrap import get_router
        return get_router()
    except Exception:
        return None


def _configured_name(task: str) -> str:
    """Best-effort lookup of the operator-configured provider name.

    Tree B settings use different field names per task: `stt_model` for
    STT (a HuggingFace-style model id), `translation_provider` / `tts_provider`
    for MT and TTS. Any of them starting with `dev_` counts as dev-mode.
    """
    for key in ("stt_model", "translation_provider", "tts_provider"):
        val = getattr(settings, key, "") or ""
        if not val:
            continue
        if task == "stt" and key == "stt_model":
            return val
        if task == "mt" and key == "translation_provider":
            return val
        if task == "tts" and key == "tts_provider":
            return val
    return "auto"
