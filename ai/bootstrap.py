"""AI provider bootstrap: builds the ModelRouter singleton from settings + registry.

Wiring rule (section 78): model-specific logic lives ONLY here and in ai/providers/*.
Routes/DB models/frontend never import a concrete model.
"""
from __future__ import annotations

import threading

from ai.interfaces import (EmbeddingProvider, LanguageDetectionProvider, LLMProvider,
                           STTProvider, TTSProvider, TranslationProvider)
from ai.model_router.router import ModelRouter
from globaltalk.core.config import settings
from globaltalk.core.logging import get_logger

log = get_logger("ai")

_router: ModelRouter | None = None
_lock = threading.Lock()


def _mem_total_mb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 16_000


def _marian_allowed() -> bool:
    """torch+transformers needs ~600MB RSS; never register it on tiny machines unless forced."""
    import os
    flag = os.environ.get("GT_ENABLE_MARIAN", "auto")
    if flag.lower() in ("1", "true", "yes"):
        return True
    if flag.lower() in ("0", "false", "no"):
        return False
    return _mem_total_mb() >= 2048


def _build() -> ModelRouter:
    import os
    # HF weights (whisper etc.) live under MODEL_CACHE_PATH — never in git, never in $HOME
    os.environ.setdefault("HF_HOME",
                          str(settings.resolve(settings.model_cache_path) / "hf"))
    r = ModelRouter()

    # --- STT chain: faster-whisper (primary on CPU dev) → (future: indicconformer, funasr)
    from ai.providers.stt.faster_whisper import FasterWhisperSTT
    stt = FasterWhisperSTT(model_size=settings.stt_model.split("/")[-1].replace("faster-whisper-", ""),
                           device=settings.stt_device, compute_type=settings.stt_compute_type)
    r.register("stt", stt.name, stt, priority=10)

    # --- MT chain: argos (real offline NMT) → marian/opus-mt (fills missing pairs, e.g. mr)
    #              → passthrough (honest degradation)
    from ai.providers.fallback import PassthroughTranslation
    from ai.providers.translation.argos import ArgosTranslation
    argos = ArgosTranslation()
    r.register("mt", argos.name, argos, priority=10)
    if _marian_allowed():
        from ai.providers.translation.marian import MarianTranslation
        marian = MarianTranslation()
        r.register("mt", marian.name, marian, priority=30)
    pt = PassthroughTranslation()
    r.register("mt", pt.name, pt, priority=1000)  # explicit last resort

    # --- TTS chain: piper (downloaded voices) → kokoro (when assets available)
    #     → none (captions-only fallback handled by realtime pipeline)
    from ai.providers.tts.kokoro import KokoroTTS
    from ai.providers.tts.piper import PiperTTS
    piper = PiperTTS()
    r.register("tts", piper.name, piper, priority=5)
    tts = KokoroTTS()
    r.register("tts", tts.name, tts, priority=8)

    # --- LangID: whisper audio LID is used inside STT; text LID: langid + script heuristic
    from ai.providers.fallback import ScriptHeuristicLangID
    from ai.providers.langid import LangIdDetector
    lid = LangIdDetector()
    r.register("langid", lid.name, lid, priority=10)
    sh = ScriptHeuristicLangID()
    r.register("langid", sh.name, sh, priority=50)

    # --- VAD
    from ai.providers.vad import get_vad
    vad = get_vad(settings.vad_provider)
    r.register("vad", vad.name, vad, priority=10)

    # --- LLM: vLLM when configured, else extractive assistant
    from ai.providers.llm import ExtractiveAssistant, VLLMProvider
    if settings.llm_provider == "vllm" and settings.vllm_base_url:
        r.register("llm", "vllm", VLLMProvider(settings.vllm_base_url, settings.vllm_model),
                   priority=10)
    r.register("llm", "extractive", ExtractiveAssistant(), priority=100)

    # --- Embeddings: vLLM embeddings when configured else deterministic hash embeddings
    from ai.providers.embeddings import HashEmbedding, VLLMEmbedding
    if settings.embedding_provider == "vllm" and settings.vllm_base_url:
        r.register("embedding", "vllm", VLLMEmbedding(settings.vllm_base_url, settings.vllm_model),
                   priority=10)
    r.register("embedding", "hash", HashEmbedding(), priority=100)

    return r


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        with _lock:
            if _router is None:
                _router = _build()
    return _router


def reset_router() -> None:
    global _router
    with _lock:
        _router = None
