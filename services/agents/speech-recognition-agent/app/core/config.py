"""Configuration loader using PyYAML and Pydantic Settings for Speech Recognition Agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    name: str = "speech_recognition_agent"
    version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8002
    cors_origins: List[str] = ["*"]


class AudioConfig(BaseModel):
    canonical_sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"
    frame_duration_ms: int = 50
    max_audio_duration_seconds: float = 1800.0  # 30 minutes
    max_file_size_bytes: int = 104857600       # 100 MB


class STTConfig(BaseModel):
    primary_provider: str = "faster-whisper"
    model_size: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    cpu_threads: int = 4
    beam_size: int = 1
    task: str = "transcribe"
    language_hint: Optional[str] = None
    word_timestamps: bool = True
    condition_on_previous_text: bool = False
    vad_filter: bool = False


class StreamingConfig(BaseModel):
    partial_enabled: bool = True
    partial_interval_ms: int = 500
    min_audio_duration_ms: int = 200
    max_audio_duration_ms: int = 30000
    stale_partial_drop: bool = True


class AntiHallucinationConfig(BaseModel):
    enabled: bool = True
    min_confidence: float = 0.25
    no_speech_threshold: float = 0.60
    max_repetition_count: int = 3
    suppress_silence_loops: bool = True


class ConcurrencyConfig(BaseModel):
    max_concurrent_sessions: int = 50
    max_concurrent_inferences: int = 4
    queue_capacity: int = 100
    worker_threads: int = 4


class LLMAgentConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    timeout_seconds: int = 15


class MonitoringConfig(BaseModel):
    log_level: str = "INFO"
    structured_logging: bool = True
    metrics_enabled: bool = True


class IntegrationConfig(BaseModel):
    language_agent_url: str = "http://127.0.0.1:8003"
    forward_to_agent03: bool = True


class Settings(BaseSettings):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    anti_hallucination: AntiHallucinationConfig = Field(default_factory=AntiHallucinationConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    llm_agent: LLMAgentConfig = Field(default_factory=LLMAgentConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings(config_path: Optional[str] = None) -> Settings:
    """Loads settings from config.yaml with env overrides."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    if config_path is None:
        cfg_file = base_dir / "config.yaml"
    else:
        cfg_file = Path(config_path)

    config_dict: Dict[str, Any] = {}
    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                config_dict = loaded

    # Apply environment overrides
    if os.getenv("API_PORT"):
        config_dict.setdefault("api", {})["port"] = int(os.getenv("API_PORT"))
    if os.getenv("API_HOST"):
        config_dict.setdefault("api", {})["host"] = os.getenv("API_HOST")
    if os.getenv("STT_PROVIDER"):
        config_dict.setdefault("stt", {})["primary_provider"] = os.getenv("STT_PROVIDER")
    if os.getenv("STT_MODEL_SIZE"):
        config_dict.setdefault("stt", {})["model_size"] = os.getenv("STT_MODEL_SIZE")
    if os.getenv("STT_DEVICE"):
        config_dict.setdefault("stt", {})["device"] = os.getenv("STT_DEVICE")
    if os.getenv("STT_COMPUTE_TYPE"):
        config_dict.setdefault("stt", {})["compute_type"] = os.getenv("STT_COMPUTE_TYPE")
    if os.getenv("GT_STT_CPU_THREADS"):
        config_dict.setdefault("stt", {})["cpu_threads"] = int(os.getenv("GT_STT_CPU_THREADS"))
    if os.getenv("OLLAMA_MODEL"):
        config_dict.setdefault("llm_agent", {})["model"] = os.getenv("OLLAMA_MODEL")
    if os.getenv("OLLAMA_BASE_URL"):
        config_dict.setdefault("llm_agent", {})["base_url"] = os.getenv("OLLAMA_BASE_URL")
    if os.getenv("OLLAMA_ENABLED"):
        config_dict.setdefault("llm_agent", {})["enabled"] = os.getenv("OLLAMA_ENABLED").lower() in ("1", "true", "yes")

    return Settings(**config_dict)


settings = load_settings()
