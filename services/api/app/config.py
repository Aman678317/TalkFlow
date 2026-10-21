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
    livekit_public_url: str = ""  # browser-reachable wss:// URL
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # --- P2P WebRTC mesh ICE configuration (WS transport meetings) ---
    # JSON list passed straight to RTCPeerConnection.iceServers for room members
    # only. Deployments behind symmetric NAT/mobile carriers must host a TURN
    # server; public STUN-only defaults stay when this is empty.
    # e.g. '[{"urls":"turn:turn.example.com:3478?transport=udp","username":"tk","credential":"pw"}]'
    webrtc_ice_servers_json: str = ""

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

    # --- Asterisk local SIP adapter (P1 design; opt-in, operator-controlled) ---
    # The adapter places calls ONLY into allowlisted local SIP extensions; all
    # credentials stay backend-only. A real call is never silently substituted:
    # selecting the provider while disabled/config-less fails loudly instead of
    # falling back to simulated. See docs/ASTERISK_LOCAL_SIP_LAB.md.
    asterisk_telephony_enabled: bool = False
    asterisk_ari_base_url: str = ""  # e.g. http://127.0.0.1:8088 (lab default)
    asterisk_ari_username: str = ""  # dedicated least-privilege ARI user
    asterisk_ari_password: str = ""
    asterisk_ari_app_name: str = "talkflow"  # Stasis application name
    asterisk_allowed_extensions: str = ""  # comma-separated, e.g. "1001,1002"
    asterisk_request_timeout_seconds: float = 10.0
    asterisk_event_retry_seconds: float = 2.0  # grace for originate-commit races
    asterisk_ws_reconnect_seconds: float = 5.0  # WS reconnect backoff cap

    # --- P4 auto-dial worker (explicit operator opt-in, default off) ---
    call_worker_enabled: bool = False
    call_worker_interval_seconds: float = 2.0  # due-scan tick interval
    call_worker_batch_size: int = 16  # max jobs enqueued per tick

    # --- agent media runtime (P3 marathon follow-up; explicit opt-in, default off) ---
    # Bridges the validated externalMedia runtime to the AI-agent turn loop for
    # connected outbound calls. Requires `asterisk_telephony_enabled`. Without a
    # wired STT the agent fail-closes (graph's own low-confidence escalation);
    # without a wired TTS the lines are decided and audited but no frames are
    # sent. No PSTN or human-audio claim: lab-local lane only.
    asterisk_media_enabled: bool = False
    asterisk_media_bind_host: str = "0.0.0.0"
    asterisk_media_bind_port: int = 8787  # the port Asterisk's dials per call
    asterisk_media_external_host: str = "talkflow-media-cfg"  # websocket-client object
    asterisk_agent_permitted_documents: str = ""  # comma-separated doc ids
    asterisk_agent_segment_wait_seconds: float = 2.0  # recognizer-path wait

    # Inbound Stasis legs (P3 lab decision): accept a call only when the
    # dialplan shape is `Stasis(talkflow,inbound)`, the caller AND dialed
    # extension are both operator-allowlisted local extensions, and the
    # owning organization is explicitly configured (empty = fail closed —
    # multi-tenant ownership is never guessed from an ARI event).
    asterisk_inbound_enabled: bool = False
    asterisk_inbound_org_id: str = ""

    # --- AI providers ---
    translation_provider: str = "auto"
    translation_model: str = ""
    airllm_model_id: str = "meta-llama/Llama-3.1-70B-Instruct"
    airllm_hf_token: str = ""
    airllm_layer_shards_path: str = ""
    airllm_max_input_tokens: int = 512
    airllm_max_new_tokens: int = 128
    deepl_api_key: str = ""
    deepl_api_url: str = "https://api-free.deepl.com/v2/translate"
    mt_http_url: str = ""
    mt_http_style: str = "opennmt"
    # Azure is optional and server-side only. Translator credentials may be
    # separate; adapters fall back to the Speech key/region for multi-service
    # Azure resources.
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_language: str = "en-US"
    azure_speech_auto_detect_languages: str = ""
    azure_speech_voice_map: str = ""
    azure_translator_key: str = ""
    azure_translator_region: str = ""
    azure_translator_endpoint: str = "https://api.cognitive.microsofttranslator.com"
    azure_translator_api_version: str = "3.0"
    stt_provider: str = "auto"
    stt_model: str = "small"
    stt_device: str = "auto"
    stt_compute_type: str = "int8"
    stt_http_url: str = ""
    tts_provider: str = "auto"
    tts_model: str = "kokoro-v1.0"
    tts_http_url: str = ""
    # Which voice speaks which target language: "hi=hf_alpha,en=af_heart".
    # Empty means the provider's own default, which for Kokoro is a single
    # English voice — correct for en, wrong for every other language the room
    # translates into. Populated from the voice benchmark, not from a guess.
    tts_voice_map: str = ""
    lang_detect_provider: str = "auto"
    fasttext_lid_model: str = ""
    summarization_provider: str = "extractive"
    llm_http_url: str = ""
    llm_model: str = "local-llm"
    embedding_provider: str = "hash_tfidf"
    embedding_model: str = ""
    model_cache_path: str = "/tmp/model_cache" if _is_serverless() else "./model_cache"
    vad_provider: str = "webrtc_energy"
    document_translation_concurrency: int = 4
    ocr_provider: str = "auto"

    # --- turn segmentation (Phase 3) --------------------------------------- #
    # One source of truth for when a turn ends. Before this the numbers lived in
    # two places that never met: EnergyVAD's constructor defaults (250/500 ms,
    # its own 20 s cap) and literals in the speaker loop (15 s force-split, 1.2 s
    # partial cadence), so two turn-length limits disagreed and neither could be
    # retuned per deployment without a code change.
    # tests/unit/test_vad_cadence.py measures what each one costs.
    vad_min_speech_ms: int = 250      # below this a burst is a cough, not a turn
    vad_min_silence_ms: int = 500     # pause that ends a turn; also endpoint latency
    vad_max_speech_ms: int = 15000    # forced commit for a never-pausing speaker
    vad_partial_interval_ms: int = 1200  # live-caption cadence
    # Once a turn has run this long, a clause terminator in the live caption
    # commits it immediately instead of waiting for the speaker to breathe.
    # 0 disables the early commit; turns still end on silence or the cap above.
    vad_phrase_commit_ms: int = 4000

    gpu_available: bool = False

    # --- writing service (P2): provider-backed contextual grammar tier --------
    write_neural_timeout_s: float = 12.0

    # Per-attempt provider deadline (P0 remediation for #109(a)). No single
    # provider attempt may own a request forever: providers that hang at
    # first use (offline model bootstrap, upstream stalls) get their attempt
    # bounded and the chain fails over to the next candidate. 0 disables.
    provider_attempt_timeout_s: float = 20.0

    # realtime tuning (PDD §11.4)
    # Per-stage provider deadlines (remediation plan §2.3). A stage that blows its
    # deadline fails over / degrades instead of stalling the room's event loop.
    rt_stt_deadline_ms: float = 3000.0
    rt_mt_deadline_ms: float = 2500.0
    rt_tts_ttfb_deadline_ms: float = 2000.0
    # Bounded local-inference concurrency across STT/MT/TTS in one process.
    rt_inference_concurrency: int = 4
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
    cookie_samesite: str = "lax"
    cookie_domain: str | None = None
    refresh_grace_seconds: int = 15
    csrf_enabled: bool = True

    # Phase 2 (docs/PRODUCTION_ROADMAP.md): real social authentication. Verification
    # FAILS CLOSED while a provider is unconfigured — Google/Apple ID tokens cannot
    # be audience-validated without the client id, so they are refused, not silently
    # accepted. Secrets are server-only; the SPA reads its own VITE_* client ids.
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    apple_client_id: str = ""

    # Phase 1 (docs/PRODUCTION_ROADMAP.md): dev auth shortcuts must fail CLOSED in
    # every mode. These are explicit, opt-in-only escape hatches for local dev and
    # CI — NOT tied to app_env. Off by default everywhere, including development, so
    # no ambient backdoor exists and the production image can never reach them by
    # accident. Enable deliberately: ALLOW_SEED=true, ALLOW_TEST_AUTH=true.
    allow_seed: bool = False        # seed demo/admin users at startup
    allow_test_auth: bool = False   # accept wildcard test keys / mock social tokens

    # --- retention (days; 0 = forever) ---
    retention_audio_days: int = 7
    retention_transcript_days: int = 365
    retention_document_days: int = 90
    retention_usage_days: int = 730
    # resolved escalate-ticket audit rows (§E2 durable transport). The
    # resolution itself outlives the row on the call's own event ledger.
    retention_escalation_days: int = 30

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
            if self.cookie_samesite.lower() not in ("lax", "strict", "none"):
                raise ValueError("cookie_samesite must be 'lax', 'strict', or 'none'.")
            self.secure_cookies = True
            # --- §E1 production telephony gates (fail-closed at boot) --------- #
            # 0. An explicit provider choice is mandatory the moment carrier
            #    credentials exist: "auto" silently resolves at runtime and can
            #    pick a carrier WITHOUT passing that carrier's production gates
            #    below — that is exactly how a half-configured lane boots.
            carrier_creds_present = any((
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.telnyx_api_key,
            ))
            if self.telephony_provider == "auto" and carrier_creds_present:
                raise ValueError(
                    "Production requires an explicit 'telephony_provider' "
                    "when carrier credentials are configured — 'auto' "
                    "resolves silently and can bypass this environment's "
                    "lane gates."
                )
            # 1. Signed carrier webhooks can never be disabled in production;
            #    anti-replay + HMAC are silent safety nets otherwise.
            if not self.telephony_verify_webhook_signatures:
                raise ValueError(
                    "Production environment must not disable "
                    "'telephony_verify_webhook_signatures' (signed webhooks, "
                    "anti-replay). Verification is compile-safety, not optional."
                )
            # 2. A selected CARRIER lane must bring its full secret set AND a
            #    TLS-terminating webhook base URL — carrier callbacks carry
            #    signed requests; a signed webhook over http:// is worthless.
            expected_https = "https://"
            if self.telephony_provider == "twilio":
                missing = [name for name, value in (
                    ("TWILIO_ACCOUNT_SID", self.twilio_account_sid),
                    ("TWILIO_AUTH_TOKEN", self.twilio_auth_token),
                    ("TWILIO_PHONE_NUMBER", self.twilio_phone_number),
                ) if not value]
                if missing:
                    raise ValueError(
                        "Production twilio provider requires " + ", ".join(missing))
            elif self.telephony_provider == "telnyx":
                if not self.telnyx_api_key:
                    raise ValueError(
                        "Production telnyx provider requires 'TELNYX_API_KEY'.")
            elif self.telephony_provider == "livekit_sip":
                if not (self.livekit_enabled and self.livekit_url
                        and self.livekit_api_key and self.livekit_api_secret):
                    raise ValueError(
                        "Production livekit_sip provider requires 'LIVEKIT_ENABLED' "
                        "plus LIVEKIT_URL / API key / API secret.")
            elif self.telephony_provider == "asterisk":
                if not (self.asterisk_telephony_enabled and self.asterisk_ari_base_url
                        and self.asterisk_ari_username and self.asterisk_ari_password
                        and self.asterisk_allowed_extensions):
                    raise ValueError(
                        "Production asterisk (local SIP) lane requires "
                        "'ASTERISK_TELEPHONY_ENABLED' plus ARI base URL, "
                        "least-privilege credentials and an explicit extension "
                        "allowlist (public dialing is rejected by design).")
            if self.telephony_provider in ("twilio", "telnyx", "livekit_sip"):
                if not self.telephony_webhook_base_url.startswith(expected_https):
                    raise ValueError(
                        "Production carrier telephony requires an HTTPS "
                        "'telephony_webhook_base_url' (signed carrier callbacks "
                        "arrive there; http:// or empty is not acceptable).")
            # 3. LiveKit SFU configured in production must be fully specified —
            #    half-configured media = silent failure of real traffic.
            if self.livekit_enabled:
                if not self.livekit_url or not self.livekit_api_key \
                        or not self.livekit_api_secret:
                    raise ValueError(
                        "Production LIVEKIT_ENABLED requires LIVEKIT_URL, "
                        "LIVEKIT_API_KEY and LIVEKIT_API_SECRET.")
                if not self.livekit_public_url.startswith("wss://"):
                    raise ValueError(
                        "Production requires a browser-reachable wss:// "
                        "'livekit_public_url' (TLS media path).")
                if self.webrtc_ice_servers_json.strip():
                    import json as _json
                    try:
                        ice = _json.loads(self.webrtc_ice_servers_json)
                    except _json.JSONDecodeError:
                        raise ValueError(
                            "'webrtc_ice_servers_json' must be a JSON list of "
                            "{urls, username, credential} TURN objects.") from None
                    if not (isinstance(ice, list) and len(ice) > 0 and all(
                            isinstance(s, dict) and s.get("urls") for s in ice)):
                        raise ValueError(
                            "'webrtc_ice_servers_json' must be a JSON list of "
                            "{urls, username, credential} TURN objects.")
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
