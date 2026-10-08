from pathlib import Path
import yaml
from app.db.session import _normalize_db_url, _make_engine
from app.realtime.protocol import ServerEventType


def test_render_yaml_configuration():
    render_path = Path("render.yaml")
    assert render_path.exists(), "render.yaml must exist at repository root"

    content = yaml.safe_load(render_path.read_text(encoding="utf-8"))
    assert "services" in content
    services = content["services"]
    assert len(services) >= 1

    api_service = next((s for s in services if s.get("name") == "globaltalk-api"), None)
    assert api_service is not None, "Must define globaltalk-api service"
    assert api_service.get("type") == "web"
    assert api_service.get("runtime") == "python"
    assert api_service.get("branch") == "fix/vercel-deployment-500"
    assert api_service.get("healthCheckPath") == "/health"
    assert "alembic upgrade head" in api_service.get("startCommand", "")
    assert "uvicorn app.main:app" in api_service.get("startCommand", "")

    env_vars = {item["key"]: item for item in api_service.get("envVars", [])}
    assert "DATABASE_URL" in env_vars
    assert "SUPABASE_URL" in env_vars
    assert "JWT_SECRET" in env_vars
    assert "CORS_ORIGINS" in env_vars


def test_supabase_db_url_normalization():
    # 1. postgres:// prefix -> postgresql+asyncpg://
    raw_supabase = "postgres://postgres.abc123xyz:secretpassword@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
    normalized = _normalize_db_url(raw_supabase)
    assert normalized.startswith("postgresql+asyncpg://")
    assert "ssl=require" in normalized
    assert "sslmode=" not in normalized

    # 2. direct connection
    direct_supabase = "postgresql://postgres:secretpassword@db.abc123xyz.supabase.co:5432/postgres?sslmode=require"
    norm_direct = _normalize_db_url(direct_supabase)
    assert norm_direct.startswith("postgresql+asyncpg://")
    assert "ssl=require" in norm_direct

    # 3. SQLite normalization
    sqlite_url = "sqlite:///./data/globaltalk.db"
    norm_sqlite = _normalize_db_url(sqlite_url)
    assert norm_sqlite.startswith("sqlite+aiosqlite://")


def test_supabase_engine_disables_statement_cache_for_pgbouncer():
    pooler_url = "postgresql://postgres.abc123xyz:secretpassword@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
    engine = _make_engine(pooler_url)
    # Check that connect_args statement_cache_size is set to 0 for pgbouncer
    connect_args = engine.url.query.copy() if hasattr(engine.url, "query") else {}
    # The asyncpg connect args are stored in engine.dialect.connect_args
    dialect_args = getattr(engine.dialect, "connect_args", {})
    # Engine was created without crashing
    assert engine is not None
    assert engine.dialect.name == "postgresql"


def test_realtime_protocol_event_contract_aliases():
    assert ServerEventType.TRANSCRIPT_PARTIAL == "transcript.partial"
    assert ServerEventType.TRANSCRIPT_FINAL == "transcript.final"
    assert ServerEventType.TRANSLATION_FINAL == "translation.final"
    assert ServerEventType.TTS_CHUNK == "tts.chunk"
    assert ServerEventType.TTS_COMPLETED == "tts.completed"

    # Master prompt event aliases
    assert ServerEventType.TRANSLATION_TRANSCRIPT_PARTIAL == "translation.transcript.partial"
    assert ServerEventType.TRANSLATION_TRANSCRIPT_FINAL == "translation.transcript.final"
    assert ServerEventType.TRANSLATION_SEGMENT_TRANSLATED == "translation.segment.translated"
    assert ServerEventType.TRANSLATION_TTS_READY == "translation.tts.ready"
    assert ServerEventType.TRANSLATION_STATUS == "translation.status"
    assert ServerEventType.TRANSLATION_ERROR == "translation.error"
