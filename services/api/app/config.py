"""Application configuration (pydantic-settings).

Every tunable lives here — no magic numbers scattered through business logic.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


def _find_env_file() -> str | None:
    env = os.environ.get("APP_ENV", "development")
    for candidate in (
        Path(os.environ.get("GT_ENV_FILE", "")) if os.environ.get("GT_ENV_FILE") else None,
        REPO_ROOT / f".env.{env}.local",
        REPO_ROOT / f".env.{env}",
        REPO_ROOT / ".env",
    ):
        if candidate and candidate.is_file():
            return str(candidate)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(), env_file_encoding="utf-8", extra="ignore"
    )

    # --- core ---
    app_env: str = "development"
    app_name: str = "GlobalTalk AI"
    version: str = "0.1.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8088
    web_origin: str = "http://localhost:5173"
    log_level: str = "INFO"
    secret_key: str = "dev-secret-key"
    jwt_secret: str = "dev-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 30
    bcrypt_rounds: int = 12

    # --- datastores ---
    database_url: str = "sqlite+aiosqlite:///./data/globaltalk.db"
    fallback_database_url: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False
    redis_url: str = ""
    cache_backend: str = "auto"  # auto | redis | memory

    # --- storage ---
    s3_enabled: bool = False
    s3_endpoint: str = ""
    s3_bucket: str = "globaltalk"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    local_storage_path: str = "./data/storage"
    max_upload_mb: int = 50

    # --- livekit ---
    livekit_enabled: bool = False
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # --- AI providers ---
    translation_provider: str = "auto"
    translation_model: str = ""
    mt_http_url: str = ""
    mt_http_style: str = "opennmt"
    stt_provider: str = "auto"
    stt_model: str = "small"
    stt_device: str = "auto"
    stt_compute_type: str = "int8"
    stt_http_url: str = ""
    tts_provider: str = "auto"
    tts_model: str = "kokoro-v1.0"
    tts_http_url: str = ""
    lang_detect_provider: str = "auto"
    fasttext_lid_model: str = ""
    summarization_provider: str = "extractive"
    llm_http_url: str = ""
    llm_model: str = "local-llm"
    embedding_provider: str = "hash_tfidf"
    embedding_model: str = ""
    model_cache_path: str = "./model_cache"
    vad_provider: str = "webrtc_energy"
    gpu_available: bool = False

    # realtime tuning (PDD §11.4)
    rt_target_latency_ms: float = 2500.0
    rt_stale_after_ms: float = 6000.0
    rt_min_chunk_ms: int = 200
    rt_max_chunk_ms: int = 2500
    rt_session_ttl_s: int = 3600
    rt_resume_buffer_size: int = 500  # events kept per session for reconnect replay

    # --- rate limits (count/period) ---
    rate_limit_translate: str = "60/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_default: str = "300/minute"
    rate_limit_ws_connect: str = "30/minute"

    # --- observability ---
    otel_enabled: bool = False
    otel_endpoint: str = ""
    sentry_dsn: str = ""
    metrics_enabled: bool = True

    # --- security ---
    clamav_host: str = ""
    clamav_port: int = 3310
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173"])
    secure_cookies: bool = False
    csrf_enabled: bool = True

    # --- retention (days; 0 = forever) ---
    retention_audio_days: int = 7
    retention_transcript_days: int = 365
    retention_document_days: int = 90
    retention_usage_days: int = 730

    # --- workers ---
    worker_inproc: bool = True  # run job worker loop inside API process (dev)
    doc_job_poll_interval_s: float = 1.0

    # --- feature flags (defaults; DB overrides) ---
    ff_voice_translation: bool = True
    ff_document_translation: bool = True
    ff_agent_bridge: bool = False
    ff_voice_preservation: bool = False
    ff_new_translation_model: bool = False
    ff_experimental_language: bool = False
    ff_enterprise_sso: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def resolved_database_url(self) -> str:
        return self.database_url

    def ensure_dirs(self) -> None:
        Path(self.local_storage_path).mkdir(parents=True, exist_ok=True)
        Path(self.model_cache_path).mkdir(parents=True, exist_ok=True)
        db_url = self.database_url
        if db_url.startswith("sqlite"):
            db_path = db_url.split("///")[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
