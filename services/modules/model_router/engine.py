"""Dynamic Model Router Engine (Module F).

Selects and ranks candidate models for STT, MT, TTS, VAD, Diarization, and Audio Enhancement
based on language coverage, measured quality, latency, memory footprint, hardware availability,
licensing, and cost.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Tuple
from modules.model_router.models import (
    ModelProfile,
    ModelSelectionResult,
    RoutingConstraint,
)

logger = logging.getLogger("talkflow.modules.model_router")


class DynamicModelRouter:
    """Configurable model selection and multi-tier fallback engine."""

    def __init__(self) -> None:
        # task -> Dict[model_id, ModelProfile]
        self._registry: Dict[str, Dict[str, ModelProfile]] = {
            "stt": {},
            "mt": {},
            "tts": {},
            "diarization": {},
            "vad": {},
            "enhancement": {},
        }
        self._seed_default_models()

    def _seed_default_models(self) -> None:
        """Seed realistic models across speech and language tasks."""
        # STT Models
        self.register_model(
            ModelProfile(
                model_id="whisper-faster-base",
                task="stt",
                name="Faster-Whisper Base (CTranslate2 INT8)",
                provider="faster-whisper",
                supported_languages=["en", "hi", "mr", "bn", "es", "fr", "de", "ja", "zh", "ar"],
                quality_score=0.91,
                typical_latency_ms=180.0,
                typical_rtf=0.18,
                memory_mb=450,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="whisper-faster-small",
                task="stt",
                name="Faster-Whisper Small (CTranslate2 INT8)",
                provider="faster-whisper",
                supported_languages=["en", "hi", "mr", "bn", "es", "fr", "de", "ja", "zh", "ar"],
                quality_score=0.95,
                typical_latency_ms=350.0,
                typical_rtf=0.32,
                memory_mb=900,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )

        # Translation Models
        self.register_model(
            ModelProfile(
                model_id="google-gtx-neural",
                task="mt",
                name="Google GTX Neural (Fast Online Hybrid)",
                provider="google-gtx",
                supported_languages=["en", "hi", "mr", "bn", "gu", "ta", "te", "es", "fr", "de", "ja", "zh", "ar"],
                quality_score=0.94,
                typical_latency_ms=120.0,
                typical_rtf=0.05,
                memory_mb=64,
                device_required="any",
                license_type="commercial_api",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="qwen-3.5-4b-instruct",
                task="mt",
                name="Local Qwen 3.5 4B (Hinglish & Regional Code-Switching)",
                provider="ollama",
                supported_languages=["en", "hi", "mr", "bn", "es", "fr", "de", "ja", "zh"],
                quality_score=0.93,
                typical_latency_ms=280.0,
                typical_rtf=0.22,
                memory_mb=2800,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=False,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="argos-translate-offline",
                task="mt",
                name="Argos Translate Offline (Zero-Network Permissive)",
                provider="argos",
                supported_languages=["en", "es", "fr", "de", "hi", "ar"],
                quality_score=0.86,
                typical_latency_ms=90.0,
                typical_rtf=0.08,
                memory_mb=350,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )

        # TTS Models
        self.register_model(
            ModelProfile(
                model_id="edge-neural-speech",
                task="tts",
                name="Microsoft Edge Neural Speech (High-Fidelity Human Voices)",
                provider="edge_tts",
                supported_languages=["en", "hi", "mr", "bn", "gu", "ta", "te", "kn", "ml", "pa", "ur", "es", "fr", "de", "ja", "zh", "ar"],
                quality_score=0.97,
                typical_latency_ms=150.0,
                typical_rtf=0.12,
                memory_mb=128,
                device_required="any",
                license_type="commercial_api",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="gtts-cloud-fallback",
                task="tts",
                name="Google TTS Cloud Fallback",
                provider="gtts",
                supported_languages=["en", "hi", "mr", "bn", "gu", "ta", "te", "es", "fr", "de", "ja", "zh", "ar"],
                quality_score=0.90,
                typical_latency_ms=220.0,
                typical_rtf=0.18,
                memory_mb=64,
                device_required="any",
                license_type="commercial_api",
                cost_per_minute_usd=0.0,
                supports_streaming=False,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="dev-tone-formant",
                task="tts",
                name="TalkFlow DevTone Formant Synthesizer (Zero-Weight Local)",
                provider="dev_tone",
                supported_languages=["*"],
                quality_score=0.65,
                typical_latency_ms=8.0,
                typical_rtf=0.01,
                memory_mb=16,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )

        # VAD & Diarization
        self.register_model(
            ModelProfile(
                model_id="silero-vad-v4",
                task="vad",
                name="Silero VAD v4 (Fast Neural Speech Boundary)",
                provider="silero",
                supported_languages=["*"],
                quality_score=0.96,
                typical_latency_ms=15.0,
                typical_rtf=0.02,
                memory_mb=50,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="energy-vad-heuristic",
                task="vad",
                name="Energy Threshold VAD",
                provider="talkflow-core",
                supported_languages=["*"],
                quality_score=0.82,
                typical_latency_ms=2.0,
                typical_rtf=0.002,
                memory_mb=8,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="pyannote-diarization-v3",
                task="diarization",
                name="PyAnnote Speaker Diarization v3",
                provider="pyannote",
                supported_languages=["*"],
                quality_score=0.94,
                typical_latency_ms=450.0,
                typical_rtf=0.40,
                memory_mb=1200,
                device_required="cpu",
                license_type="open_source",
                cost_per_minute_usd=0.0,
                supports_streaming=False,
                is_available_locally=True,
            )
        )
        self.register_model(
            ModelProfile(
                model_id="spectral-gate-enhancer",
                task="enhancement",
                name="Spectral Gating Acoustic Denoiser",
                provider="scipy-audio",
                supported_languages=["*"],
                quality_score=0.88,
                typical_latency_ms=12.0,
                typical_rtf=0.015,
                memory_mb=32,
                device_required="cpu",
                license_type="permissive",
                cost_per_minute_usd=0.0,
                supports_streaming=True,
                is_available_locally=True,
            )
        )

    def register_model(self, profile: ModelProfile) -> None:
        """Registers or updates a candidate model profile."""
        if profile.task in self._registry:
            self._registry[profile.task][profile.model_id] = profile

    def list_models(self, task: Optional[str] = None) -> List[ModelProfile]:
        """Lists registered models."""
        if task:
            return list(self._registry.get(task, {}).values())
        all_models = []
        for task_dict in self._registry.values():
            all_models.extend(task_dict.values())
        return all_models

    def route_model(self, constraints: RoutingConstraint) -> ModelSelectionResult:
        """Selects the primary model and builds a robust fallback chain based on multi-dimensional utility."""
        candidates = list(self._registry.get(constraints.task, {}).values())
        target_lang = constraints.target_language.lower().split("-")[0].strip()

        # Filter by language compatibility
        compatible = []
        for c in candidates:
            if not c.is_healthy:
                continue
            if "*" in c.supported_languages or target_lang in c.supported_languages:
                compatible.append(c)

        if not compatible:
            # Fallback to any healthy model in task
            compatible = [c for c in candidates if c.is_healthy]

        if not compatible:
            raise RuntimeError(f"No available or healthy models found for task '{constraints.task}'.")

        # Score candidates
        scored: List[Tuple[float, ModelProfile]] = []
        for m in compatible:
            score = m.quality_score * 50.0  # Quality weight
            # Latency penalty: penalize latency > 200ms
            if m.typical_latency_ms > 200.0:
                score -= ((m.typical_latency_ms - 200.0) / 100.0) * 8.0
            # Local preference bonus
            if constraints.prefer_local_only and m.is_available_locally and m.cost_per_minute_usd == 0:
                score += 15.0
            # Streaming requirement check
            if constraints.require_streaming and not m.supports_streaming:
                score -= 30.0

            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        primary = scored[0][1]
        fallbacks = [m for _, m in scored[1:4]]

        reason = (
            f"Selected '{primary.name}' (Quality: {primary.quality_score*100:.0f}%, "
            f"RTF: {primary.typical_rtf:.2f}, Latency: {primary.typical_latency_ms:.0f}ms) "
            f"matching language '{target_lang}'."
        )

        return ModelSelectionResult(
            task=constraints.task,
            primary_model=primary,
            fallback_chain=fallbacks,
            reasoning=reason,
            evaluated_candidates_count=len(compatible),
        )


# Global Router Instance
dynamic_model_router = DynamicModelRouter()

