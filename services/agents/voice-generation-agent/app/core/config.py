"""Configuration loader and settings validation for Voice Generation Agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class AgentMetadata(BaseModel):
    name: str = "voice_generation_agent"
    version: str = "1.0.0"
    description: str = "TalkFlow Voice Generation Agent"


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8006
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


class TTSConfig(BaseModel):
    default_provider: str = "dev_tone"
    default_language: str = "en"
    default_locale: str = "en-US"
    default_voice: str = "af_heart"
    default_style: str = "natural"
    sample_rate: int = 24000
    channels: int = 1
    encoding: str = "pcm_s16le"
    output_format: str = "wav"
    streaming_enabled: bool = True
    ttfb_deadline_ms: int = 2000
    request_timeout_ms: int = 15000
    max_concurrent_synthesis: int = 4
    queue_max_size: int = 100
    preload_models: bool = False
    allow_model_downloads: bool = False
    device: str = "cpu"
    min_quality_score: float = 0.40
    supported_languages: List[str] = Field(default_factory=lambda: [
        "en", "hi", "mr", "bn", "gu", "kn", "ml", "pa", "ta", "te", "ur", "ar", "ja", "es", "fr", "de", "zh", "pt", "it", "ko"
    ])
    kokoro_model_path: str = "model_cache/kokoro/kokoro-v0_19.onnx"
    kokoro_voices_path: str = "model_cache/kokoro/voices.json"
    piper_model_dir: str = "model_cache/piper"
    azure_speech_key: Optional[str] = None
    azure_speech_region: Optional[str] = None


class PrivacyConfig(BaseModel):
    private_only: bool = False
    offline_only: bool = False
    external_providers_enabled: bool = False
    require_explicit_consent: bool = True
    voice_cloning_enabled: bool = False


class IntegrationConfig(BaseModel):
    agent05_url: str = "http://127.0.0.1:8005"
    agent07_url: str = "http://127.0.0.1:8007"
    talkflow_api_url: str = "http://127.0.0.1:8000"
    shared_secret: str = "talkflow_mt_secret_token_dev"


class LLMAgentConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.2
    timeout_seconds: int = 10


class Settings(BaseModel):
    agent: AgentMetadata = Field(default_factory=AgentMetadata)
    api: ApiConfig = Field(default_factory=ApiConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    voice_map: Dict[str, str] = Field(default_factory=lambda: {
        "en": "af_heart",
        "hi": "hf_alpha",
        "mr": "mr_IN-google-medium",
        "bn": "bn_BD-google-medium",
        "ja": "jf_alpha",
    })
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    llm_agent: LLMAgentConfig = Field(default_factory=LLMAgentConfig)

    # Convenience properties
    @property
    def server_port(self) -> int:
        return self.api.port

    @property
    def cors_origins(self) -> List[str]:
        return self.api.cors_origins

    @property
    def audio_sample_rate(self) -> int:
        return self.tts.sample_rate

    @property
    def default_provider(self) -> str:
        return self.tts.default_provider

    @property
    def supported_languages(self) -> List[str]:
        return self.tts.supported_languages

    @property
    def min_quality_score(self) -> float:
        return self.tts.min_quality_score

    @property
    def offline_only(self) -> bool:
        return self.privacy.offline_only

    @property
    def private_only(self) -> bool:
        return self.privacy.private_only

    @property
    def agent07_url(self) -> str:
        return self.integration.agent07_url

    @property
    def shared_secret(self) -> str:
        return self.integration.shared_secret

    @property
    def kokoro_model_path(self) -> str:
        return self.tts.kokoro_model_path

    @property
    def kokoro_voices_path(self) -> str:
        return self.tts.kokoro_voices_path

    @property
    def piper_model_dir(self) -> str:
        return self.tts.piper_model_dir

    @property
    def azure_speech_key(self) -> Optional[str]:
        return self.tts.azure_speech_key

    @property
    def azure_speech_region(self) -> Optional[str]:
        return self.tts.azure_speech_region

    @property
    def ollama_model(self) -> str:
        return self.llm_agent.model if self.llm_agent.enabled else ""

    @property
    def ollama_base_url(self) -> str:
        return self.llm_agent.base_url


def load_settings() -> Settings:
    config_file = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    data: Dict[str, Any] = {}
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Environment variable overrides
    port_env = os.environ.get("TTS_SERVICE_PORT") or os.environ.get("PORT")
    if port_env:
        data.setdefault("api", {})["port"] = int(port_env)

    if def_prov := os.environ.get("GT_TTS_DEFAULT_PROVIDER"):
        data.setdefault("tts", {})["default_provider"] = def_prov

    if priv := os.environ.get("GT_TTS_PRIVATE_ONLY"):
        data.setdefault("privacy", {})["private_only"] = priv.lower() in ("true", "1", "yes")

    if offl := os.environ.get("GT_TTS_OFFLINE_ONLY"):
        data.setdefault("privacy", {})["offline_only"] = offl.lower() in ("true", "1", "yes")

    if a05 := os.environ.get("AGENT05_HOST"):
        data.setdefault("integration", {})["agent05_url"] = a05

    if a07 := os.environ.get("AGENT07_HOST"):
        data.setdefault("integration", {})["agent07_url"] = a07

    if brain_en := os.environ.get("AGENT_BRAIN_ENABLED"):
        data.setdefault("llm_agent", {})["enabled"] = brain_en.lower() in ("true", "1", "yes")

    if ollama_host := os.environ.get("OLLAMA_HOST"):
        data.setdefault("llm_agent", {})["base_url"] = ollama_host

    if secret := os.environ.get("TALKFLOW_SHARED_SECRET"):
        data.setdefault("integration", {})["shared_secret"] = secret

    return Settings(**data)


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = load_settings()
    return _settings_instance


settings = get_settings()
