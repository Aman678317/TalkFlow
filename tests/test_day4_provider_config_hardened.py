"""Roadmap day 4 — model router, provider health and configuration.

Hardened regressions for the four gaps the day-4 audit confirmed:

1. `dev_echo` used to forward non-canned text to the online provider from
   inside the chain's final, private-classified hop and relabel the cloud
   result `provider=dev_echo` — now it is offline and honest.
2. The canonical app resolved HF weights at `~/.cache/huggingface` (the HF
   default) while `scripts/download_models.sh` provisions
   `MODEL_CACHE_PATH/hf` — now `app.config` pins `HF_HOME` and the
   adapters/probes delegate to the HF default instead of a divergent root.
3. `/api/v1/system/diagnostics` collapsed configured / available /
   supported / production-validated into one `healthy` flag — now the
   registry-backed supported languages and validated pairs are reported.
4. Router coverage filters (validated pairs, languages, domains) and the
   all-providers-down degradation are pinned by tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.types import Intent, ProviderUnavailable, Task, TranslationRequest


# --------------------------------------------------------------------------- #
# 1. dev_echo: offline, always; honest on both hit and miss
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dev_echo_never_calls_the_online_provider(monkeypatch):
    """A non-canned sentence must come back as flagged passthrough — the
    online provider must not even be constructed-and-called from inside
    the private-classified final hop."""
    from gt_ai.translation import neural_online as no
    from gt_ai.translation.dev_echo import DevEchoTranslationProvider

    async def _forbidden(self, req):  # noqa: ARG001
        raise AssertionError(
            "dev_echo forwarded the request to the online provider")

    monkeypatch.setattr(no.NeuralOnlineTranslationProvider, "translate",
                        _forbidden)
    text = "a sentence no phrase table could ever know"
    res = await DevEchoTranslationProvider().translate(TranslationRequest(
        text=text, source_lang="en", target_lang="de"))
    assert res.provider == "dev_echo"
    assert res.model == "dev-echo-v1"
    assert res.text == text, "a miss must pass the source through, unchanged"
    assert "untranslated_fallback" in res.quality_flags
    assert "dev_provider" in res.quality_flags
    assert "neural_mt" not in res.quality_flags, (
        "the passthrough must never wear a real-model flag")


@pytest.mark.asyncio
async def test_dev_echo_canned_hit_carries_the_phrase_table_flag():
    from gt_ai.translation.dev_echo import DevEchoTranslationProvider
    res = await DevEchoTranslationProvider().translate(TranslationRequest(
        text="Hello world", source_lang="en", target_lang="de"))
    assert res.text == "Hallo Welt"
    assert "phrase_table" in res.quality_flags
    assert "neural_mt" not in res.quality_flags
    assert "dev_provider" in res.quality_flags


# --------------------------------------------------------------------------- #
# 2. the HF cache root: one policy, shared with the download script
# --------------------------------------------------------------------------- #

def test_app_config_pins_hf_home_under_the_model_cache():
    from app.config import settings
    hf_home = Path(__import__("os").environ.get("HF_HOME", ""))
    assert hf_home != Path(""), "HF_HOME must be set at settings import"
    assert hf_home.resolve() == (Path(settings.model_cache_path).resolve()
                                 / "hf"), (
        "HF_HOME must point at MODEL_CACHE_PATH/hf — the root "
        "scripts/download_models.sh provisions")


def test_faster_whisper_probe_delegates_to_the_hf_default_when_no_cache_dir():
    """cache_dir=None must ask the HF default location (which app.config
    points at MODEL_CACHE_PATH/hf), not probe a divergent literal root."""
    import huggingface_hub

    from gt_ai.stt.faster_whisper import FasterWhisperProvider
    seen: dict = {}

    def _spy(*, repo_id, filename, cache_dir=None):  # noqa: ARG001
        seen["cache_dir"] = cache_dir
        return None  # honest miss; we only care WHERE it looked

    import gt_ai.translation.model_fetch as mf
    orig = huggingface_hub.try_to_load_from_cache
    import gt_ai.stt.faster_whisper as fw

    monkey_target = fw.model_fetch
    assert monkey_target is mf
    huggingface_hub.try_to_load_from_cache = _spy
    try:
        FasterWhisperProvider(model_size="small")._weights_cached()
    finally:
        huggingface_hub.try_to_load_from_cache = orig
    assert seen.get("cache_dir") is None


def test_faster_whisper_probe_finds_weights_in_an_explicit_hf_layout(tmp_path):
    """The no-load probe recognizes a provisioned HF cache layout
    (models--org--name/{refs,snapshots}) under an explicit cache_dir."""
    from gt_ai.stt.faster_whisper import FasterWhisperProvider
    pytest.importorskip("huggingface_hub")
    repo = "Systran/faster-whisper-small"
    hub = tmp_path / "hf" / "hub"
    sha = "0" * 40
    model_dir = hub / "models--Systran--faster-whisper-small"
    snap = model_dir / "snapshots" / sha
    snap.mkdir(parents=True)
    (snap / "model.bin").write_bytes(b"fake")
    refs = model_dir / "refs"
    refs.mkdir(parents=True)
    (refs / "main").write_text(sha)
    p = FasterWhisperProvider(model_size=repo, cache_dir=str(hub))
    assert p._weights_cached() is True


def test_provider_kwargs_do_not_override_the_hf_root():
    """faster_whisper / madlad400 must not carry a cache_dir kwarg: a
    download_root under MODEL_CACHE_PATH re-downloaded weights that the
    download script had already provisioned one directory over."""
    from app.ai import ai
    for task, name in ((Task.STT, "faster_whisper"), (Task.MT, "madlad400")):
        kwargs = ai._provider_kwargs(task, name)
        assert "cache_dir" not in kwargs, (
            f"{name} must resolve weights through the HF_HOME policy")


# --------------------------------------------------------------------------- #
# 3. diagnostics: configured / available / supported / validated, honestly
# --------------------------------------------------------------------------- #

class _HealthyProvider:
    name = "madlad400"

    async def healthcheck(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_diagnostics_report_supported_languages_and_validated_pairs(
        monkeypatch):
    from app.ai import AIFacade
    f = AIFacade()
    # The configured provider (conftest pins TRANSLATION_PROVIDER=dev_echo)
    # is the one the four-state fields describe.
    f._specs = {Task.MT: [ProviderSpec(
        name="dev_echo", task=Task.MT,
        languages={"en", "hi"}, validated_pairs={("en", "hi")})]}
    f.router = ModelRouter(f._specs)
    monkeypatch.setattr(f, "provider",
                        lambda task, name: _HealthyProvider())
    diag = await f.diagnostics()
    mt = diag["tasks"]["mt"]
    assert mt["configured_provider"] == "dev_echo"
    assert mt["supported_languages"] == ["en", "hi"]
    assert mt["validated_pairs"] == ["en->hi"]
    assert mt["healthy"] is True
    # secrets never appear in the diagnostics payload
    dumped = json.dumps(diag)
    from app.config import settings
    for secret in (settings.azure_speech_key, settings.azure_translator_key,
                   settings.deepl_api_key, settings.jwt_secret):
        if secret:
            assert secret not in dumped


# --------------------------------------------------------------------------- #
# 4. router coverage filters + all-providers-down degradation
# --------------------------------------------------------------------------- #

def _router(specs, health=None):
    return ModelRouter({Task.MT: specs}, gpu_available=False, health=health or {})


def test_validated_pairs_filter_routes_to_the_validated_provider():
    validated = ProviderSpec(name="validated_one", task=Task.MT,
                             validated_pairs={("en", "de")}, priority=10)
    general = ProviderSpec(name="general_one", task=Task.MT, priority=1)
    d = _router([general, validated]).route(
        Task.MT, source_lang="en", target_lang="de",
        intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider == "validated_one", (
        "the explicitly validated provider must win the pair")


def test_unvalidated_pair_prefers_another_candidate_when_one_exists():
    """Coverage filters are decisive while any candidate survives them; with
    a second general candidate available, the validated provider must NOT be
    picked for a pair it was never validated for."""
    validated = ProviderSpec(name="validated_one", task=Task.MT,
                             validated_pairs={("en", "de")}, priority=10)
    general = ProviderSpec(name="general_one", task=Task.MT, priority=1)
    d = _router([validated, general]).route(
        Task.MT, source_lang="en", target_lang="fr",
        intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider == "general_one", (
        "the validated provider must not claim a pair it was never "
        "validated for while another candidate covers it")


def test_last_resort_ladder_reintroduces_a_filtered_candidate():
    """Documented degrade behavior: when the filters exclude EVERY
    candidate (single validated provider, unvalidated pair), the router
    still returns it rather than raising — the provider adapter itself
    rejects the pair at execution time and the chain fails over. Pinned so
    a change to this trade-off is a deliberate decision, not an accident."""
    validated = ProviderSpec(name="validated_one", task=Task.MT,
                             validated_pairs={("en", "de")})
    d = _router([validated]).route(
        Task.MT, source_lang="en", target_lang="fr",
        intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider == "validated_one"


def test_language_coverage_filter_prefers_the_covered_provider():
    covered = ProviderSpec(name="covered", task=Task.MT,
                           languages={"en", "de"}, priority=10)
    general = ProviderSpec(name="general_one", task=Task.MT, priority=1)
    d = _router([covered, general]).route(
        Task.MT, source_lang="en", target_lang="hi",
        intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider == "general_one", (
        "a provider without the target language must not serve the pair "
        "while another candidate covers it")


def test_private_only_with_no_serving_provider_fails_honestly():
    cloud = ProviderSpec(name="neural_online", task=Task.MT, private=False,
                         languages={"en", "de"})
    r = _router([cloud])
    with pytest.raises(Exception) as e:
        r.route(Task.MT, source_lang="en", target_lang="hi",
                intent=Intent.PRIVATE_ONLY)
    assert "private" in str(e.value).lower()


@pytest.mark.asyncio
async def test_all_real_providers_down_degrades_to_the_flagged_dev_standin(
        monkeypatch):
    """Every real candidate raises: outside production the chain ends at
    dev_echo (clearly flagged), never at a fabricated translation."""
    from gt_ai.registry import create

    from app.ai import AIFacade

    class _Broken:
        name = "madlad400"

        def runtime_ready(self) -> bool:
            return True

        async def translate(self, req):  # noqa: ARG002
            raise ProviderUnavailable("weights unreadable")

    class _BrokenCloud:
        name = "neural_online"

        def runtime_ready(self) -> bool:
            return True

        async def translate(self, req):  # noqa: ARG002
            raise ProviderUnavailable("upstream unreachable")

    def _provider(task, name):
        if name == "madlad400":
            return _Broken()
        if name == "neural_online":
            return _BrokenCloud()
        return create(task.value, name)  # dev_echo: the real stand-in

    f = AIFacade()
    f._specs = {Task.MT: [ProviderSpec(name="madlad400", task=Task.MT)]}
    f.router = ModelRouter(f._specs)
    monkeypatch.setattr(f, "provider", _provider)
    res, decision = await f.translate(TranslationRequest(
        text="ordinary sentence", source_lang="en", target_lang="de"))
    assert decision.provider == "dev_echo"
    assert "dev_provider" in res.quality_flags
