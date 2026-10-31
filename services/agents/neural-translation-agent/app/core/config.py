"""Pydantic Settings and PyYAML configuration loader for Neural Translation Agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseModel):
    name: str = "neural_translation_agent"
    version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8004
    cors_origins: List[str] = ["*"]


class TranslationConfig(BaseModel):
    primary_provider: str = "argos"
    default_model: str = "argos-default"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 2
    max_input_length: int = 50000
    max_output_length: int = 50000
    translation_timeout_sec: float = 10.0
    partial_enabled: bool = True
    partial_interval_ms: int = 400
    min_prefix_chars: int = 20
    stable_prefix_length: int = 32
    max_concurrent_jobs: int = 16
    dedup_ttl_seconds: int = 300


class ArgosConfig(BaseModel):
    packages_dir: str = "model_cache/argos"
    auto_download: bool = False


class MarianConfig(BaseModel):
    cache_dir: str = "model_cache/hf"
    auto_download: bool = False


class NllbConfig(BaseModel):
    model_dir: str = "model_cache/nllb-200-600m-ct2-int8"
    tokenizer_file: str = "model_cache/nllb-200-600m-ct2-int8/sentencepiece.bpe.model"
    license_warning_accepted: bool = False


class MadladConfig(BaseModel):
    model_id: str = "google/madlad400-3b-mt"
    cache_dir: str = "model_cache/hf"


class OnlineConfig(BaseModel):
    deepl_api_key: Optional[str] = None
    azure_translator_key: Optional[str] = None
    azure_region: str = "global"


class ModelsConfig(BaseModel):
    argos: ArgosConfig = Field(default_factory=ArgosConfig)
    marian: MarianConfig = Field(default_factory=MarianConfig)
    nllb: NllbConfig = Field(default_factory=NllbConfig)
    madlad400: MadladConfig = Field(default_factory=MadladConfig)
    online: OnlineConfig = Field(default_factory=OnlineConfig)


class RoutingConfig(BaseModel):
    default_intent: str = "quality_optimized"
    allow_pivot_translation: bool = False
    pivot_language: str = "en"
    strict_privacy: bool = True


class GlossaryConfig(BaseModel):
    enabled: bool = True
    case_sensitive: bool = False
    enforce_target_terms: bool = True
    protect_source_terms: bool = True


class TMConfig(BaseModel):
    enabled: bool = True
    exact_match_threshold: float = 1.0
    fuzzy_match_threshold: float = 0.85
    semantic_match_threshold: float = 0.88
    approved_only: bool = True
    writeback_enabled: bool = False


class StyleConfig(BaseModel):
    default_formality: str = "neutral"
    default_domain: str = "general"


class LLMAgentConfig(BaseModel):
    enabled: bool = True
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3.5:4b"
    api_key: str = "ollama"
    timeout_sec: float = 10.0


class IntegrationConfig(BaseModel):
    agent03_url: str = "http://127.0.0.1:8003"
    agent05_url: str = "http://127.0.0.1:8005"
    talkflow_api_url: str = "http://127.0.0.1:8000"


_BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    """Unified application settings."""
    model_config = SettingsConfigDict(
        env_file=str(_BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    agent: AgentConfig = Field(default_factory=AgentConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    glossary: GlossaryConfig = Field(default_factory=GlossaryConfig)
    translation_memory: TMConfig = Field(default_factory=TMConfig)
    style: StyleConfig = Field(default_factory=StyleConfig)
    llm_agent: LLMAgentConfig = Field(default_factory=LLMAgentConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)

    @classmethod
    def load_from_yaml(cls, path: str = "config.yaml") -> Settings:
        config_path = Path(path)
        if not config_path.is_absolute():
            base_dir = Path(__file__).resolve().parent.parent.parent
            resolved = base_dir / path
            if resolved.exists():
                config_path = resolved
        if not config_path.exists():
            return cls()
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            agent=AgentConfig(**data.get("agent", {})),
            api=APIConfig(**data.get("api", {})),
            translation=TranslationConfig(**data.get("translation", {})),
            models=ModelsConfig(**data.get("models", {})),
            routing=RoutingConfig(**data.get("routing", {})),
            glossary=GlossaryConfig(**data.get("glossary", {})),
            translation_memory=TMConfig(**data.get("translation_memory", {})),
            style=StyleConfig(**data.get("style", {})),
            llm_agent=LLMAgentConfig(**data.get("llm_agent", {})),
            integration=IntegrationConfig(**data.get("integration", {})),
        )


settings = Settings.load_from_yaml()
