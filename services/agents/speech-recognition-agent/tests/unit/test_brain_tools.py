"""Unit tests for OpenAI Agents SDK operational tools."""
from app.agents.tools import (
    get_language_capabilities_fn,
    get_stt_status_fn,
    list_available_models_fn,
    list_stt_providers_fn,
    recommend_stt_profile_fn,
)


def test_get_stt_status_fn():
    status = get_stt_status_fn()
    assert status["status"] == "operational"
    assert "provider" in status
    assert "model_size" in status


def test_list_stt_providers_fn():
    providers = list_stt_providers_fn()
    assert len(providers) >= 2
    assert any(p["name"] == "faster-whisper" for p in providers)


def test_list_available_models_fn():
    models = list_available_models_fn()
    names = [m["model"] for m in models]
    assert "tiny" in names
    assert "base" in names
    assert "small" in names


def test_recommend_stt_profile_fn():
    # GPU recommendation
    gpu_rec = recommend_stt_profile_fn("cuda-gpu", "en")
    assert gpu_rec["device"] == "cuda"
    assert gpu_rec["compute_type"] == "float16"

    # CPU recommendation
    cpu_rec = recommend_stt_profile_fn("intel-i5", "hi")
    assert cpu_rec["device"] == "cpu"
    assert cpu_rec["compute_type"] == "int8"

