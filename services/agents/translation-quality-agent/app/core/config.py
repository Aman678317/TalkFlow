"""Configuration loader using PyYAML and Pydantic Settings for Translation Quality Agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    name: str = "translation_quality_agent"
    version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8005
    cors_origins: List[str] = ["*"]


class EvaluationConfig(BaseModel):
    realtime_qa_enabled: bool = True
    final_qa_enabled: bool = True
    max_input_length: int = 5000
    timeout_seconds: float = 5.0
    max_concurrent_evaluations: int = 16
    reference_free_evaluator: str = "semantic_multilingual"
    reference_based_evaluator: str = "sacrebleu"


class DeterministicChecksConfig(BaseModel):
    empty_check: bool = True
    number_check: bool = True
    currency_check: bool = True
    dates_check: bool = True
    times_check: bool = True
    urls_emails_check: bool = True
    protected_spans_check: bool = True
    glossary_check: bool = True
    script_check: bool = True
    negation_check: bool = True
    duplication_check: bool = True
    max_length_ratio: float = 3.5
    min_length_ratio: float = 0.15


class ScoringWeightsConfig(BaseModel):
    semantic_accuracy: float = 0.35
    completeness: float = 0.20
    data_integrity: float = 0.25
    terminology: float = 0.10
    fluency: float = 0.10


class ThresholdsConfig(BaseModel):
    quality_threshold: float = 0.70
    warning_threshold: float = 0.55
    retry_budget: int = 2


class LLMAgentConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    timeout_seconds: int = 15


class IntegrationConfig(BaseModel):
    agent04_url: str = "http://127.0.0.1:8004"
    agent06_url: str = "http://127.0.0.1:8006"
    shared_secret: str = "talkflow_mt_secret_token_dev"


class Settings(BaseSettings):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    deterministic_checks: DeterministicChecksConfig = Field(default_factory=DeterministicChecksConfig)
    scoring_weights: ScoringWeightsConfig = Field(default_factory=ScoringWeightsConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    llm_agent: LLMAgentConfig = Field(default_factory=LLMAgentConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def load_from_yaml(cls, path: Optional[Path] = None) -> "Settings":
        cfg_path = path or (Path(__file__).resolve().parent.parent.parent / "config.yaml")
        data: Dict[str, Any] = {}
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded

        # Apply environment overrides explicitly
        if os.getenv("API_PORT"):
            data.setdefault("api", {})["port"] = int(os.getenv("API_PORT"))
        if os.getenv("API_HOST"):
            data.setdefault("api", {})["host"] = os.getenv("API_HOST")
        if os.getenv("REALTIME_QA_ENABLED"):
            data.setdefault("evaluation", {})["realtime_qa_enabled"] = os.getenv("REALTIME_QA_ENABLED").lower() in ("1", "true")
        if os.getenv("FINAL_QA_ENABLED"):
            data.setdefault("evaluation", {})["final_qa_enabled"] = os.getenv("FINAL_QA_ENABLED").lower() in ("1", "true")
        if os.getenv("OLLAMA_MODEL"):
            data.setdefault("llm_agent", {})["model"] = os.getenv("OLLAMA_MODEL")
        if os.getenv("OLLAMA_BASE_URL"):
            data.setdefault("llm_agent", {})["base_url"] = os.getenv("OLLAMA_BASE_URL")
        if os.getenv("OLLAMA_ENABLED"):
            data.setdefault("llm_agent", {})["enabled"] = os.getenv("OLLAMA_ENABLED").lower() in ("1", "true")
        if os.getenv("AGENT04_URL"):
            data.setdefault("integration", {})["agent04_url"] = os.getenv("AGENT04_URL")
        if os.getenv("AGENT06_URL"):
            data.setdefault("integration", {})["agent06_url"] = os.getenv("AGENT06_URL")

        return cls(**data)


settings = Settings.load_from_yaml()

