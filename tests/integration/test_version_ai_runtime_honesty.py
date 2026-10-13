"""Phase 6: `GET /version` has to admit what the image cannot do.

The deployment that motivated this: `/version` answered
`{"stt": "faster_whisper", "tts": "kokoro"}` while the backend image installed
neither package, so every realtime call fell through to the dev stand-in and the
operator's one-curl config check said everything was configured correctly. The
configured name is a preference; the runtime is evidence. Both now appear.
"""
from __future__ import annotations

import app.ai as ai_mod
from app.config import settings

TASK_KEYS = ("stt", "mt", "tts", "lang_detect", "summarize", "embed")
RUNTIME_STATES = {"importable", "missing", "remote", "remote_unconfigured",
                  "dev_stand_in", "builtin"}


def _version_ai(services_app_client) -> dict:
    r = services_app_client.get("/version")
    assert r.status_code == 200, r.text
    return r.json()["ai"]


def test_every_task_reports_provider_and_runtime(services_app_client):
    block = _version_ai(services_app_client)
    assert set(block) == set(TASK_KEYS)
    for task, info in block.items():
        assert info["provider"], task
        assert info["runtime"] in RUNTIME_STATES, task


def test_provider_without_its_runtime_package_is_reported_missing(
        services_app_client, monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "heavy_local_model")
    monkeypatch.setattr(ai_mod, "_RUNTIME_MODULE",
                        {**ai_mod._RUNTIME_MODULE,
                         "heavy_local_model": "a_module_not_in_any_image"})
    assert _version_ai(services_app_client)["stt"] == {
        "provider": "heavy_local_model", "runtime": "missing"}


def test_provider_with_its_runtime_package_is_reported_importable(
        services_app_client, monkeypatch):
    # numpy is a hard dependency of this service, so it is importable here for
    # the same reason `piper` is importable in an image that installs it.
    monkeypatch.setattr(settings, "tts_provider", "some_onnx_voice")
    monkeypatch.setattr(ai_mod, "_RUNTIME_MODULE",
                        {**ai_mod._RUNTIME_MODULE, "some_onnx_voice": "numpy"})
    assert _version_ai(services_app_client)["tts"]["runtime"] == "importable"


def test_dev_stand_in_is_named_as_such_even_when_configured(services_app_client,
                                                            monkeypatch):
    """A pinned `dev_*` provider is a fake, and `transcript.inject` depends on
    knowing that — the label must survive the move from "configured name"."""
    monkeypatch.setattr(settings, "stt_provider", "dev_text")
    monkeypatch.setattr(settings, "tts_provider", "dev_tone")
    block = _version_ai(services_app_client)
    assert block["stt"] == {"provider": "dev_text", "runtime": "dev_stand_in"}
    assert block["tts"] == {"provider": "dev_tone", "runtime": "dev_stand_in"}


def test_remote_provider_without_an_endpoint_is_reported_unconfigured(
        services_app_client, monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "stt_http")
    monkeypatch.setattr(settings, "stt_http_url", "")
    assert _version_ai(services_app_client)["stt"]["runtime"] == "remote_unconfigured"


def test_remote_provider_with_an_endpoint_is_reported_remote(
        services_app_client, monkeypatch):
    monkeypatch.setattr(settings, "stt_provider", "stt_http")
    monkeypatch.setattr(settings, "stt_http_url", "http://127.0.0.1:9/v1")
    assert _version_ai(services_app_client)["stt"]["runtime"] == "remote"


def test_public_web_provider_needs_no_key_to_be_reachable(services_app_client,
                                                          monkeypatch):
    """`neural_online` cascades over public endpoints, so an empty DeepL key must
    not be reported as a missing runtime — that would be a lie in the other
    direction, and this is the provider production translation actually uses."""
    monkeypatch.setattr(settings, "translation_provider", "neural_online")
    monkeypatch.setattr(settings, "deepl_api_key", "")
    assert _version_ai(services_app_client)["mt"] == {
        "provider": "neural_online", "runtime": "remote"}


def test_in_process_provider_needs_no_runtime_package(services_app_client,
                                                      monkeypatch):
    monkeypatch.setattr(settings, "summarization_provider", "extractive")
    assert _version_ai(services_app_client)["summarize"]["runtime"] == "builtin"
