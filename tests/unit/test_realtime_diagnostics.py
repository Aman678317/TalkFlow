"""Regression tests for truthful, secret-safe realtime readiness diagnostics."""
from types import SimpleNamespace

from app.realtime import diagnostics
from gt_ai.types import Task


class _FakeAI:
    router = None
    _providers = {}
    _specs = {}

    @staticmethod
    def _configured_name(task):
        return {
            Task.STT: "dev_text",
            Task.MT: "dev_echo",
            Task.TTS: "dev_tone",
        }.get(task, "auto")


def test_readiness_does_not_claim_unobserved_providers_are_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics.settings, "app_env", "test")
    monkeypatch.setattr(diagnostics.settings, "model_cache_path", str(tmp_path))
    monkeypatch.setattr(diagnostics.settings, "document_ocr_enabled", False)
    monkeypatch.setattr(diagnostics.settings, "livekit_enabled", False)
    monkeypatch.setattr(diagnostics.settings, "tts_voice_map", "")
    monkeypatch.setattr(diagnostics.settings, "stt_provider", "auto")
    monkeypatch.setattr(diagnostics.settings, "translation_provider", "auto")
    monkeypatch.setattr(diagnostics.settings, "tts_provider", "auto")

    report = diagnostics.build_realtime_readiness(_FakeAI())

    assert report["overall_state"] == "degraded_unverified"
    assert report["is_fully_verified"] is False
    assert report["verification_mode"] == "passive_snapshot_no_external_probes"
    assert all(
        item["status"] == "configured_unverified"
        for item in report["providers"].values()
    )
    assert report["privacy"] == {
        "secrets_included": False,
        "audio_or_transcript_text_included": False,
    }
    assert report["media"]["livekit_connection_verified"] is False
    assert report["document_ocr"]["status"] == "disabled"


def test_production_readiness_marks_development_providers_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics.settings, "app_env", "production")
    monkeypatch.setattr(diagnostics.settings, "model_cache_path", str(tmp_path))
    monkeypatch.setattr(diagnostics.settings, "document_ocr_enabled", False)
    monkeypatch.setattr(diagnostics.settings, "livekit_enabled", False)
    monkeypatch.setattr(diagnostics.settings, "tts_voice_map", "")
    monkeypatch.setattr(diagnostics.settings, "stt_provider", "dev_text")
    monkeypatch.setattr(diagnostics.settings, "translation_provider", "dev_echo")
    monkeypatch.setattr(diagnostics.settings, "tts_provider", "dev_tone")

    report = diagnostics.build_realtime_readiness(_FakeAI())

    assert report["overall_state"] == "unavailable"
    assert report["is_fully_verified"] is False
    for task in ("stt", "mt", "tts"):
        assert report["providers"][task]["status"] == "unavailable"
        assert "development_provider_forbidden_in_production" in report["providers"][task]["missing_requirements"]



def test_metrics_inventory_distinguishes_registered_from_runtime_observed(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics.settings, "app_env", "test")
    monkeypatch.setattr(diagnostics.settings, "model_cache_path", str(tmp_path))
    monkeypatch.setattr(diagnostics.settings, "document_ocr_enabled", False)
    monkeypatch.setattr(diagnostics.settings, "livekit_enabled", False)
    monkeypatch.setattr(diagnostics.settings, "tts_voice_map", "")
    monkeypatch.setattr(diagnostics.settings, "stt_provider", "auto")
    monkeypatch.setattr(diagnostics.settings, "translation_provider", "auto")
    monkeypatch.setattr(diagnostics.settings, "tts_provider", "auto")
    monkeypatch.setattr(diagnostics, "_registered_metric_names", lambda: {
        "gt_stt_latency_ms", "gt_realtime_stage_duration_ms"
    })

    report = diagnostics.build_realtime_readiness(_FakeAI())
    metrics = report["metrics"]

    assert metrics["expected_inventory"]["gt_stt_latency_ms"] == {
        "description": "STT latency histogram",
        "registered": True,
        "runtime_observed": False,
    }
    assert metrics["expected_inventory"]["gt_e2e_latency_ms"]["registered"] is False
    assert "gt_e2e_latency_ms" in metrics["missing_expected_metrics"]
    assert "gt_realtime_stage_duration_ms" not in metrics["missing_expected_metrics"]
    assert report["tracing"]["websocket_request_id_supported"] is True
    assert report["tracing"]["cross_stage_propagation_runtime_verified"] is False
