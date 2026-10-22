import pytest
from app.ai import ai


@pytest.mark.asyncio
async def test_ai_diagnostics_structure_and_safe_output():
    diag = await ai.diagnostics()
    assert isinstance(diag, dict)
    assert "status" in diag
    assert diag["status"] in ("ready", "degraded", "unavailable")
    assert "tasks" in diag
    assert "stt" in diag["tasks"]
    assert "mt" in diag["tasks"]
    assert "tts" in diag["tasks"]
    assert "language_pairs" in diag
    assert "ocr" in diag

    # Security check: Ensure no secrets or tokens are exposed
    diag_str = str(diag).lower()
    for forbidden in ("secret", "token", "password", "key_val", "bearer"):
        assert forbidden not in diag_str


def test_readiness_probe_includes_diagnostics(services_app_client):
    # Test with diagnostics parameter using services_app_client
    res = services_app_client.get("/ready?diagnostics=true")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "diagnostics" in data
    assert data["diagnostics"]["status"] in ("ready", "degraded", "unavailable")


def test_system_diagnostics_endpoint(services_app_client):
    res = services_app_client.get("/api/v1/system/diagnostics")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "infrastructure" in data
    assert "ai" in data
    assert "ocr" in data["ai"]


@pytest.mark.asyncio
async def test_the_diagnostics_pair_matrix_is_the_capability_registry():
    """Day-3 (2026-10-23): ``ai.diagnostics()`` froze a hand-written
    seven-language ``core_pairs`` sample nothing kept in sync — eleven
    registry languages the products DO translate (bn, ta, te, gu, kn, ml, pa,
    ur, pt, ar, ko) were invisible in the diagnostic surface. The matrix must
    be derived from the capability registry, not a literal."""
    from gt_ai.capabilities import DEFAULT_LANGUAGES

    diag = await ai.diagnostics()
    matrix = diag["language_pairs"]
    pairs = list(matrix["core_sample"])
    supported = {lc.code for lc in DEFAULT_LANGUAGES if lc.translation_supported}

    advertised: set[str] = set()
    for p in pairs:
        src, tgt = p.split("->")
        advertised |= {src, tgt}
    assert advertised <= supported, (
        "the diagnostics matrix advertised a language the capability registry "
        f"does not carry: {sorted(advertised - supported)}")
    assert matrix["supported_count"] == len(pairs)
    hub = {p for p in pairs if p.startswith("en->")}
    assert {p.split("->")[1] for p in hub} == supported - {"en"}, (
        "the diagnostics matrix must cover every translation-supported "
        "registry language, not a frozen seven-language sample")
