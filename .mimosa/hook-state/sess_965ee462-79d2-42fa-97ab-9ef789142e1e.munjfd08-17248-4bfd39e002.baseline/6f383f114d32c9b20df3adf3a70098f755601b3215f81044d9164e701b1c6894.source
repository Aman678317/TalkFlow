"""Provider registry & factory.

Providers register by (task, name). The factory builds adapters lazily from
configuration, so unused heavy models are never imported.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from gt_ai.base import BaseProvider

log = logging.getLogger("gt_ai.registry")

_REGISTRY: dict[tuple[str, str], Callable[..., BaseProvider]] = {}
_INSTANCES: dict[tuple[str, str, tuple], BaseProvider] = {}


def register(task: str, name: str):
    """Decorator: register a provider factory under (task, name)."""

    def deco(cls: Callable[..., BaseProvider]):
        _REGISTRY[(task, name)] = cls
        return cls

    return deco


def registered(task: str) -> list[str]:
    return [n for (t, n) in _REGISTRY if t == task]


def create(task: str, name: str, **kwargs: Any) -> BaseProvider:
    key = (task, name)
    if key not in _REGISTRY:
        # import adapter modules on demand so optional deps stay optional
        _import_adapters(task)
    if key not in _REGISTRY:
        raise KeyError(f"No provider registered for task={task} name={name}. "
                       f"Available: {registered(task)}")
    cache_key = (task, name, tuple(sorted((k, str(v)) for k, v in kwargs.items())))
    if cache_key not in _INSTANCES:
        _INSTANCES[cache_key] = _REGISTRY[key](**kwargs)  # type: ignore[call-arg]
    return _INSTANCES[cache_key]


def reset_instances() -> None:
    """Used by tests."""
    _INSTANCES.clear()


def _import_adapters(task: str) -> None:
    import importlib

    modules = {
        "stt": ["gt_ai.stt.faster_whisper", "gt_ai.stt.http", "gt_ai.stt.dev"],
        "mt": [
            "gt_ai.translation.madlad400",
            "gt_ai.translation.nllb_ct2",
            "gt_ai.translation.http",
            "gt_ai.translation.argos",
            "gt_ai.translation.dev_echo",
        ],
        "tts": ["gt_ai.tts.kokoro", "gt_ai.tts.piper", "gt_ai.tts.http", "gt_ai.tts.dev_tone"],
        "lang_detect": ["gt_ai.detection.fasttext", "gt_ai.detection.langdetect_p"],
        "summarize": ["gt_ai.summarize.extractive", "gt_ai.summarize.llm_http"],
        "embed": ["gt_ai.embeddings.hash_tfidf", "gt_ai.embeddings.st_embed"],
    }
    for mod in modules.get(task, []):
        try:
            importlib.import_module(mod)
        except ImportError as e:  # optional dependency missing
            log.debug("adapter %s unavailable: %s", mod, e)
