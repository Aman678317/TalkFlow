"""Configuration loader using PyYAML and Pydantic Settings for Language Intelligence Agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    name: str = "language_intelligence_agent"
    version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8003
    cors_origins: List[str] = ["*"]


class DetectionConfig(BaseModel):
    primary_text_provider: str = "fasttext"
    fallback_text_provider: str = "langdetect"
    min_text_length: int = 2
    confidence_threshold: float = 0.45
    short_text_threshold: int = 12
    top_candidates_count: int = 5
    fasttext_model_path: str = "models/lid.176.ftz"


class CodeSwitchConfig(BaseModel):
    enabled: bool = True
    min_span_length_chars: int = 3
    min_tokens_for_switch: int = 1
    span_confidence_threshold: float = 0.60
    hinglish_latin_detection: bool = True


class FusionWeightsConfig(BaseModel):
    text_lid: float = 0.40
    stt_hint: float = 0.25
    audio_lid: float = 0.15
    script_evidence: float = 0.10
    speaker_history: float = 0.10


class EvidenceFusionConfig(BaseModel):
    weights: FusionWeightsConfig = Field(default_factory=FusionWeightsConfig)
    agreement_boost: float = 0.15
    disagreement_penalty: float = 0.20
    hysteresis_margin: float = 0.15


class SessionsConfig(BaseModel):
    max_concurrent_sessions: int = 64
    speaker_history_window: int = 10
    session_timeout_seconds: int = 300
    language_stability_count: int = 3


class LLMAgentConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    timeout_seconds: int = 15


class IntegrationConfig(BaseModel):
    agent02_url: str = "http://127.0.0.1:8002"
    agent04_url: str = "http://127.0.0.1:8004"
    talkflow_shared_secret: str = "talkflow-insecure-dev-secret"


class MonitoringConfig(BaseModel):
    log_level: str = "INFO"
    structured_logging: bool = True
    metrics_enabled: bool = True


class Settings(BaseSettings):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    code_switch: CodeSwitchConfig = Field(default_factory=CodeSwitchConfig)
    evidence_fusion: EvidenceFusionConfig = Field(default_factory=EvidenceFusionConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    llm_agent: LLMAgentConfig = Field(default_factory=LLMAgentConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings(config_path: Optional[str] = None) -> Settings:
    yaml_data: Dict[str, Any] = {}
    resolved_path = config_path or os.getenv("CONFIG_PATH")
    if not resolved_path:
        default_yaml = Path(__file__).resolve().parent.parent.parent / "config.yaml"
        if default_yaml.exists():
            resolved_path = str(default_yaml)

    if resolved_path and Path(resolved_path).exists():
        with open(resolved_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    # Environment variable overrides
    if "AGENT_PORT" in os.environ:
        yaml_data.setdefault("api", {})["port"] = int(os.environ["AGENT_PORT"])
    if "AGENT_HOST" in os.environ:
        yaml_data.setdefault("api", {})["host"] = os.environ["AGENT_HOST"]
    if "OLLAMA_MODEL" in os.environ:
        yaml_data.setdefault("llm_agent", {})["model"] = os.environ["OLLAMA_MODEL"]
    if "OLLAMA_BASE_URL" in os.environ:
        yaml_data.setdefault("llm_agent", {})["base_url"] = os.environ["OLLAMA_BASE_URL"]
    if "FASTTEXT_MODEL_PATH" in os.environ:
        yaml_data.setdefault("detection", {})["fasttext_model_path"] = os.environ["FASTTEXT_MODEL_PATH"]

    return Settings(**yaml_data)


settings = load_settings()
