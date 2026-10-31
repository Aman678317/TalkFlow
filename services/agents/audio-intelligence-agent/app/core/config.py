"""Configuration loader and schema definition using Pydantic Settings and PyYAML."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentMetadataConfig(BaseModel):
    name: str = "audio_intelligence_agent"
    version: str = "1.0.0"
    description: str = "TalkFlow Audio Intelligence Agent"


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    frame_duration_ms: int = 50
    encoding: str = "pcm_s16le"
    max_frame_size_bytes: int = 8192
    retention_policy: str = "ephemeral"  # ephemeral | memory_only | debug_disk
    temp_storage_dir: str = "temp_audio"

    @property
    def frame_samples(self) -> int:
        return (self.sample_rate * self.frame_duration_ms) // 1000

    @property
    def expected_bytes_per_frame(self) -> int:
        return self.frame_samples * self.channels * 2  # 2 bytes per 16-bit sample


class NoiseSuppressionConfig(BaseModel):
    enabled: bool = True
    provider: str = "spectral"  # spectral | noisereduce | passthrough
    spectral_subtraction_factor: float = 1.5
    spectral_flooring: float = 0.05
    stationary_noise_estimation_frames: int = 10


class VADConfig(BaseModel):
    provider: str = "silero"  # silero | webrtc | energy
    sensitivity: int = 2  # 0 to 3 for webrtcvad
    speech_threshold: float = 0.5  # Silero/Energy speech probability threshold
    silence_threshold: float = 0.35
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 500
    max_utterance_duration_ms: int = 15000
    partial_processing_interval_ms: int = 1200
    phrase_commit_interval_ms: int = 4000
    hangover_duration_ms: int = 600


class QualityConfig(BaseModel):
    snr_warning_threshold_db: float = 10.0
    clipping_warning_ratio: float = 0.01
    silence_warning_ratio: float = 0.95
    min_confidence_good: float = 0.75
    min_confidence_fair: float = 0.50


class StreamingConfig(BaseModel):
    queue_capacity: int = 100
    max_concurrent_sessions: int = 64
    backpressure_drop_stale_partials: bool = True
    session_timeout_seconds: int = 300


class LLMAgentConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"  # ollama | openai | disabled
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434/v1"
    temperature: float = 0.2
    timeout_seconds: int = 10
    api_key: str = "ollama"


class APIConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


class MonitoringConfig(BaseModel):
    prometheus_metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    log_level: str = "INFO"
    structured_logging: bool = False


class IntegrationConfig(BaseModel):
    talkflow_api_url: str = "http://localhost:8000"
    talkflow_shared_secret: str = "talkflow-insecure-dev-secret"


class Settings(BaseSettings):
    """Global unified settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    agent: AgentMetadataConfig = Field(default_factory=AgentMetadataConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    noise_suppression: NoiseSuppressionConfig = Field(default_factory=NoiseSuppressionConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    llm_agent: LLMAgentConfig = Field(default_factory=LLMAgentConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Settings":
        """Loads config from YAML file if present, then overlays environment variables."""
        yaml_data: dict[str, Any] = {}
        target_path = Path(config_path) if config_path else Path("config.yaml")

        if not target_path.exists():
            # Try searching parent directories
            alt_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"
            if alt_path.exists():
                target_path = alt_path

        if target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    if isinstance(content, dict):
                        yaml_data = content
            except Exception as e:
                print(f"Warning: Failed to load {target_path}: {e}")

        # Override with environment variables where provided
        env_overrides = cls._get_env_overrides()
        for section, values in env_overrides.items():
            if section not in yaml_data:
                yaml_data[section] = {}
            yaml_data[section].update(values)

        return cls(**yaml_data)

    @staticmethod
    def _get_env_overrides() -> dict[str, dict[str, Any]]:
        overrides: dict[str, dict[str, Any]] = {
            "agent": {},
            "audio": {},
            "noise_suppression": {},
            "vad": {},
            "streaming": {},
            "llm_agent": {},
            "api": {},
            "monitoring": {},
            "integration": {}
        }

        if v := os.environ.get("AGENT_NAME"):
            overrides["agent"]["name"] = v
        if v := os.environ.get("AGENT_VERSION"):
            overrides["agent"]["version"] = v

        if v := os.environ.get("AUDIO_SAMPLE_RATE"):
            overrides["audio"]["sample_rate"] = int(v)
        if v := os.environ.get("AUDIO_CHANNELS"):
            overrides["audio"]["channels"] = int(v)
        if v := os.environ.get("AUDIO_FRAME_DURATION_MS"):
            overrides["audio"]["frame_duration_ms"] = int(v)
        if v := os.environ.get("AUDIO_RETENTION_POLICY"):
            overrides["audio"]["retention_policy"] = v

        if v := os.environ.get("NOISE_SUPPRESSION_ENABLED"):
            overrides["noise_suppression"]["enabled"] = v.lower() in ("true", "1", "yes")
        if v := os.environ.get("NOISE_SUPPRESSION_PROVIDER"):
            overrides["noise_suppression"]["provider"] = v

        if v := os.environ.get("VAD_PROVIDER"):
            overrides["vad"]["provider"] = v
        if v := os.environ.get("VAD_SPEECH_THRESHOLD"):
            overrides["vad"]["speech_threshold"] = float(v)
        if v := os.environ.get("VAD_MIN_SPEECH_MS"):
            overrides["vad"]["min_speech_duration_ms"] = int(v)
        if v := os.environ.get("VAD_MIN_SILENCE_MS"):
            overrides["vad"]["min_silence_duration_ms"] = int(v)
        if v := os.environ.get("VAD_MAX_UTTERANCE_MS"):
            overrides["vad"]["max_utterance_duration_ms"] = int(v)
        if v := os.environ.get("VAD_PARTIAL_INTERVAL_MS"):
            overrides["vad"]["partial_processing_interval_ms"] = int(v)
        if v := os.environ.get("VAD_PHRASE_COMMIT_MS"):
            overrides["vad"]["phrase_commit_interval_ms"] = int(v)

        if v := os.environ.get("QUEUE_CAPACITY"):
            overrides["streaming"]["queue_capacity"] = int(v)
        if v := os.environ.get("MAX_CONCURRENT_SESSIONS"):
            overrides["streaming"]["max_concurrent_sessions"] = int(v)

        if v := os.environ.get("LLM_AGENT_ENABLED"):
            overrides["llm_agent"]["enabled"] = v.lower() in ("true", "1", "yes")
        if v := os.environ.get("LLM_PROVIDER"):
            overrides["llm_agent"]["provider"] = v
        if v := os.environ.get("LLM_MODEL"):
            overrides["llm_agent"]["model"] = v
        if v := os.environ.get("LLM_BASE_URL"):
            overrides["llm_agent"]["base_url"] = v
        if v := os.environ.get("OPENAI_API_KEY"):
            overrides["llm_agent"]["api_key"] = v

        if v := os.environ.get("API_HOST"):
            overrides["api"]["host"] = v
        if v := os.environ.get("API_PORT"):
            overrides["api"]["port"] = int(v)
        if v := os.environ.get("DEBUG"):
            overrides["api"]["debug"] = v.lower() in ("true", "1", "yes")

        if v := os.environ.get("LOG_LEVEL"):
            overrides["monitoring"]["log_level"] = v
        if v := os.environ.get("STRUCTURED_LOGGING"):
            overrides["monitoring"]["structured_logging"] = v.lower() in ("true", "1", "yes")

        if v := os.environ.get("TALKFLOW_API_URL"):
            overrides["integration"]["talkflow_api_url"] = v
        if v := os.environ.get("TALKFLOW_SHARED_SECRET"):
            overrides["integration"]["talkflow_shared_secret"] = v

        # Prune empty sections
        return {k: val for k, val in overrides.items() if val}


settings = Settings.load()

