"""Application configuration (pydantic-settings).

Every tunable lives here — no magic numbers scattered through business logic.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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


def _is_serverless() -> bool:
    return bool(
        os.environ.get("VERCEL")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        or os.environ.get("LAMBDA_TASK_ROOT")
    )


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
    database_url: str = (
        "sqlite+aiosqlite:////tmp/globaltalk.db"
        if _is_serverless()
        else "sqlite+aiosqlite:///./data/globaltalk.db"
    )
    fallback_database_url: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False
    redis_url: str = ""
    cache_backend: str = "auto"  # auto | redis | memory

    # --- supabase ---
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # --- storage ---
    s3_enabled: bool = False
    s3_endpoint: str = ""
    s3_bucket: str = "globaltalk"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    local_storage_path: str = "/tmp/storage" if _is_serverless() else "./data/storage"
    max_upload_mb: int = 50

    # --- livekit ---
    livekit_enabled: bool = False
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # --- telephony & international calling ---
    telephony_provider: str = "auto"  # auto | twilio | telnyx | livekit_sip | simulated
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    twilio_twiml_app_sid: str = ""
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: str = ""
    twilio_agent_identity: str = "human_agent"
    telephony_human_mobile_number: str = ""
    telnyx_api_key: str = ""
    telnyx_phone_number: str = ""
    telephony_webhook_base_url: str = ""
    telephony_sample_rate: int = 8000

    # --- AI providers ---
    translation_provider: str = "auto"
    translation_model: str = ""
    deepl_api_key: str = ""
    deepl_api_url: str = "https://api-free.deepl.com/v2/translate"
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
    model_cache_path: str = "/tmp/model_cache" if _is_serverless() else "./model_cache"
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
    rate_limit_auth: str = "300/minute"
    rate_limit_default: str = "300/minute"
    rate_limit_ws_connect: str = "30/minute"
    rate_limit_telephony_call: str = "30/minute"
    rate_limit_telephony_webhook: str = "120/minute"

    # --- telephony security & privacy (PDD Phase 12 & 13) ---
    telephony_recording_default: bool = False
    telephony_verify_webhook_signatures: bool = True

    # --- observability ---
    otel_enabled: bool = False
    otel_endpoint: str = ""
    sentry_dsn: str = ""
    metrics_enabled: bool = True
    metrics_token: str = ""

    # --- security ---
    clamav_host: str = ""
    clamav_port: int = 3310
    cors_origins: list[str] | str = Field(default_factory=lambda: [
        "http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return ["http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173"]
            if v.startswith("[") and v.endswith("]"):
                try:
                    import json
                    loaded = json.loads(v)
                    if isinstance(loaded, list):
                        return [str(x).strip() for x in loaded]
                except Exception:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, (list, tuple, set)):
            return [str(x).strip() for x in v]
        return ["http://localhost:5173", "http://localhost:4173", "http://127.0.0.1:5173"]

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

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Settings:
        if self.app_env == "production":
            insecure_defaults = {
                "dev-secret-key",
                "dev-jwt-secret",
                "secret",
                "change-me",
                "changeme",
                "default",
            }
            if self.secret_key in insecure_defaults or len(self.secret_key) < 32:
                raise ValueError(
                    "Production environment requires a strong 'SECRET_KEY' (at least 32 characters, non-default)."
                )
            if self.jwt_secret in insecure_defaults or len(self.jwt_secret) < 32:
                raise ValueError(
                    "Production environment requires a strong 'JWT_SECRET' (at least 32 characters, non-default)."
                )
            if not self.redis_url:
                raise ValueError(
                    "Production environment requires 'REDIS_URL' for distributed caching and queues."
                )
            if "sqlite" in self.database_url.lower():
                raise ValueError(
                    "Production environment requires a production PostgreSQL database ('DATABASE_URL'). SQLite is not permitted in production."
                )
            if any(o == "*" for o in self.cors_origins):
                raise ValueError(
                    "Production environment forbids wildcard '*' in 'cors_origins' when credentials are enabled."
                )
        return self

    @model_validator(mode="after")
    def _adjust_serverless_paths(self) -> Settings:
        if _is_serverless():
            if "./data/" in self.database_url:
                self.database_url = self.database_url.replace("./data/", "/tmp/")
            if self.local_storage_path.startswith("./data"):
                self.local_storage_path = "/tmp/storage"
            if self.model_cache_path.startswith("./model_cache"):
                self.model_cache_path = "/tmp/model_cache"
        return self

    @property
    def resolved_database_url(self) -> str:
        return self.database_url

    def ensure_dirs(self) -> None:
        for p in (self.local_storage_path, self.model_cache_path):
            try:
                Path(p).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        db_url = self.database_url
        if db_url.startswith("sqlite"):
            try:
                db_path = db_url.split("///")[-1]
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
