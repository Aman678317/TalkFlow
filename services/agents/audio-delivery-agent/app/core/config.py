"""Configuration loader and settings validation for Agent 07."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class AgentMetadata(BaseModel):
    name: str = "audio_delivery_agent"
    version: str = "1.0.0"
    description: str = "TalkFlow Audio Synchronization & Delivery Agent"


class ApiConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8007
    debug: bool = False
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


class DeliveryConfig(BaseModel):
    transport: str = "websocket"
    livekit_enabled: bool = False
    livekit_url: str = "ws://127.0.0.1:7880"
    livekit_public_url: str = ""
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    audio_sample_rate: int = 24000
    channels: int = 1
    audio_format: str = "pcm_s16le"
    synthetic_marker_required: bool = True


class SyncConfig(BaseModel):
    reorder_window_ms: int = 150
    reorder_wait_ms: float = 60.0
    max_jitter_buffer_ms: int = 400
    stale_utterance_timeout_ms: int = 8000
    max_stale_delay_ms: float = 1500.0
    drop_late_chunks: bool = True
    enable_adaptive_scheduling: bool = True
    clock_skew_tolerance_ms: int = 500


class RoutingConfig(BaseModel):
    default_mode: str = "translated"
    enable_translation_fanout: bool = True
    ducking_enabled: bool = True
    ducking_ratio: float = 0.20
    ducking_attenuation_db: float = -14.0
    ducking_attack_ms: int = 50
    ducking_release_ms: int = 200


class QueueConfig(BaseModel):
    max_queue_size: int = 500
    worker_concurrency: int = 4
    queue_timeout_ms: int = 5000


class PrivacyConfig(BaseModel):
    private_only: bool = False
    offline_only: bool = False
    log_audio_payloads: bool = False
    temp_retention_seconds: int = 30


class LLMAgentConfig(BaseModel):
    enabled: bool = True
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.2
    timeout_seconds: int = 10


class IntegrationConfig(BaseModel):
    agent06_url: str = "http://127.0.0.1:8006"
    talkflow_api_url: str = "http://127.0.0.1:8000"
    shared_secret: str = "talkflow_mt_secret_token_dev"


class Settings(BaseModel):
    agent: AgentMetadata = Field(default_factory=AgentMetadata)
    api: ApiConfig = Field(default_factory=ApiConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    llm_agent: LLMAgentConfig = Field(default_factory=LLMAgentConfig)
    integration: IntegrationConfig = Field(default_factory=IntegrationConfig)

    # Convenience properties
    @property
    def server(self) -> ApiConfig:
        return self.api

    @property
    def jitter_buffer(self) -> SyncConfig:
        return self.sync

    @property
    def audio_sync(self) -> Any:
        class _AudioSyncProxy:
            def __init__(self, sync_cfg: SyncConfig, routing_cfg: RoutingConfig):
                self.max_stale_delay_ms = sync_cfg.max_stale_delay_ms
                self.ducking_ratio = routing_cfg.ducking_ratio
                self.ducking_attack_ms = routing_cfg.ducking_attack_ms
                self.ducking_release_ms = routing_cfg.ducking_release_ms
        return _AudioSyncProxy(self.sync, self.routing)

    @property
    def transports(self) -> DeliveryConfig:
        return self.delivery

    @property
    def server_port(self) -> int:
        return self.api.port

    @property
    def cors_origins(self) -> List[str]:
        return self.api.cors_origins

    @property
    def audio_sample_rate(self) -> int:
        return self.delivery.audio_sample_rate

    @property
    def transport(self) -> str:
        return self.delivery.transport

    @property
    def livekit_enabled(self) -> bool:
        return self.delivery.livekit_enabled

    @property
    def shared_secret(self) -> str:
        return self.integration.shared_secret

    @property
    def agent06_url(self) -> str:
        return self.integration.agent06_url

    @property
    def ollama_url(self) -> str:
        return self.llm_agent.base_url


def load_settings() -> Settings:
    config_file = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    data: Dict[str, Any] = {}
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Environment variable overrides
    port_env = os.environ.get("DELIVERY_SERVICE_PORT") or os.environ.get("PORT")
    if port_env:
        data.setdefault("api", {})["port"] = int(port_env)

    if transport := os.environ.get("GT_AUDIO_DELIVERY_TRANSPORT"):
        data.setdefault("delivery", {})["transport"] = transport

    if lk_en := os.environ.get("LIVEKIT_ENABLED"):
        data.setdefault("delivery", {})["livekit_enabled"] = lk_en.lower() in ("true", "1", "yes")

    if a06 := os.environ.get("AGENT06_URL"):
        data.setdefault("integration", {})["agent06_url"] = a06

    if secret := os.environ.get("TALKFLOW_SHARED_SECRET"):
        data.setdefault("integration", {})["shared_secret"] = secret

    if brain_en := os.environ.get("AGENT_BRAIN_ENABLED"):
        data.setdefault("llm_agent", {})["enabled"] = brain_en.lower() in ("true", "1", "yes")

    if ollama_host := os.environ.get("OLLAMA_HOST"):
        data.setdefault("llm_agent", {})["base_url"] = ollama_host

    return Settings(**data)


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = load_settings()
    return _settings_instance


settings = get_settings()
