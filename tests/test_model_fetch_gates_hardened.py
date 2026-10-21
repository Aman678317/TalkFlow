"""Cache-first model-fetch gates for every provider task (issue #109, class 2).

Evidence behind this suite (2026-10-21, #109):

* ``gt_ai/embeddings/st_embed.py`` loaded ``intfloat/multilingual-e5-small``
  (~470 MB) with no cache probe and no flag — the first TM fuzzy match or
  assistant query started the download.
* ``gt_ai/stt/faster_whisper.py::healthcheck()`` ran ``_ensure_loaded()`` —
  the admin dashboard health poll could start a multi-hundred-MB download.
* ``app/routers/translate.py::_get_whisper_model()`` built
  ``WhisperModel("tiny")`` with no ``download_root``, landing weights in the
  default HF cache outside MODEL_CACHE_PATH.
* ``gt_ai/translation/airllm.py::runtime_ready()`` only checked ``find_spec``
  — a GPU image with airllm but no cached Llama weights would fetch
  ``meta-llama/Llama-3.1-70B-Instruct`` on the first request.
* The legacy ``ai/providers`` lane forced downloads: marian set
  ``TRANSFORMERS_OFFLINE=0``, argos refreshed the remote index and installed
  up to ~1 GB of packages inside a translation request, and silero VAD
  cloned its GitHub repo through torch.hub on first use.

Pinned here: every loader checks the local cache first and fails honestly
with :class:`ProviderUnavailable` when the weights are absent, unless the
operator opts in via ``GT_ALLOW_MODEL_DOWNLOAD`` (or the legacy
``GT_MT_ALLOW_MODEL_DOWNLOAD``). Health probes never load or download.
"""
from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os
import sys
import types

import pytest

from gt_ai.translation import model_fetch
from gt_ai.translation.model_fetch import (
    ALLOW_DOWNLOAD_ENV,
    GENERIC_ALLOW_DOWNLOAD_ENV,
    downloads_allowed,
    hf_artifact_cached,
    require_cached_or_raise,
)
from gt_ai.types import ProviderUnavailable

# the legacy lane raises its own exception class — same honest contract,
# different import, and pytest.raises must match the one actually raised
from ai.interfaces import ProviderUnavailable as LegacyProviderUnavailable


def _both_flags_off(monkeypatch) -> None:
    monkeypatch.delenv(GENERIC_ALLOW_DOWNLOAD_ENV, raising=False)
    monkeypatch.delenv(ALLOW_DOWNLOAD_ENV, raising=False)


def _specful_module(name: str) -> types.ModuleType:
    """A fake module that survives ``importlib.util.find_spec``."""
    mod = types.ModuleType(name)
    mod.__spec__ = importlib.machinery.ModuleSpec(name, None)
    return mod


def _fake_find_spec(monkeypatch, present: dict[str, object] | None) -> None:
    """Patch find_spec so ``name`` looks installed exactly when in ``present``."""
    real_find_spec = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        if present and name in present:
            return present[name]
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)


# --------------------------------------------------------------------------- #
# The shared policy module
# --------------------------------------------------------------------------- #
def test_downloads_allowed_honours_generic_and_legacy_flags(monkeypatch):
    _both_flags_off(monkeypatch)
    assert downloads_allowed() is False

    monkeypatch.setenv(GENERIC_ALLOW_DOWNLOAD_ENV, "1")
    assert downloads_allowed() is True

    monkeypatch.delenv(GENERIC_ALLOW_DOWNLOAD_ENV, raising=False)
    monkeypatch.setenv(ALLOW_DOWNLOAD_ENV, "1")
    assert downloads_allowed() is True, "the original MT-only name stays accepted"


def test_hf_artifact_cached_demands_every_filename_and_a_known_repo(monkeypatch):
    import huggingface_hub

    calls = []

    def fake_lookup(repo_id, filename, cache_dir=None):
        calls.append((repo_id, filename, cache_dir))
        return {"model.bin": "/cached/model.bin"}.get(filename)

    monkeypatch.setattr(huggingface_hub, "try_to_load_from_cache", fake_lookup)

    assert hf_artifact_cached("Systran/faster-whisper-small", "cache", ("model.bin",)) is True
    assert hf_artifact_cached(
        "Systran/faster-whisper-small", "cache", ("model.bin", "config.json")
    ) is False, "a missing file means the weights set is incomplete"

    assert hf_artifact_cached("small", "cache", ("model.bin",)) is False, \
        "a bare short name is not a known HF repo id"
    assert all(c[0] != "small" for c in calls), \
        "the probe is short-circuited before any cache lookup happens"


def test_require_cached_or_raise_names_both_opt_in_flags(monkeypatch):
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)

    with pytest.raises(ProviderUnavailable) as exc:
        require_cached_or_raise("embedding", "intfloat/multilingual-e5-small", None)
    msg = str(exc.value)
    assert GENERIC_ALLOW_DOWNLOAD_ENV in msg and ALLOW_DOWNLOAD_ENV in msg
    assert "not present in the local cache" in msg

    gated = []
    monkeypatch.setattr(
        model_fetch, "hf_artifact_cached",
        lambda repo, cache, names: gated.append((repo, cache, names)) or True)
    require_cached_or_raise("embedding", "intfloat/multilingual-e5-small", "cc")
    assert gated and gated[0][0] == "intfloat/multilingual-e5-small"


# --------------------------------------------------------------------------- #
# Canonical gt_ai provider gates (services/api tree)
# --------------------------------------------------------------------------- #
def _fake_st(monkeypatch, constructed: list) -> None:
    mod = _specful_module("sentence_transformers")

    class SentenceTransformer:
        def __init__(self, model_id, cache_folder=None, local_files_only=False):
            constructed.append({"model_id": model_id, "cache_folder": cache_folder,
                                "local_files_only": local_files_only})

        def encode(self, texts, **kwargs):
            # real ST returns numpy embeddings; emulate the tolist() contract
            return [types.SimpleNamespace(tolist=lambda: [0.1, 0.2]) for _ in texts]

    mod.SentenceTransformer = SentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)


def _st_provider():
    from gt_ai.embeddings.st_embed import SentenceTransformerEmbeddingProvider
    return SentenceTransformerEmbeddingProvider()


async def test_st_embed_never_downloads_e5_behind_a_request(monkeypatch):
    _both_flags_off(monkeypatch)
    constructed: list = []
    _fake_st(monkeypatch, constructed)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)

    with pytest.raises(ProviderUnavailable):
        await _st_provider().embed(["hello"])
    assert constructed == [], "the ~470 MB weights must not even be constructed"


async def test_st_embed_builds_from_the_local_cache_when_present(monkeypatch):
    _both_flags_off(monkeypatch)
    constructed: list = []
    _fake_st(monkeypatch, constructed)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: True)

    provider = _st_provider()
    result = await provider.embed(["hello"])
    assert result == [[0.1, 0.2]]
    assert constructed and constructed[0]["local_files_only"] is True, \
        "cache-only mode must pass local_files_only to the loader"


def test_st_embed_runtime_ready_follows_the_cache_gate(monkeypatch):
    _both_flags_off(monkeypatch)
    _fake_find_spec(monkeypatch, {"sentence_transformers": object()})
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)
    provider = _st_provider()

    assert provider.runtime_ready() is False, "not cached + no opt-in must not serve"

    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: True)
    assert provider.runtime_ready() is True

    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)
    monkeypatch.setenv(GENERIC_ALLOW_DOWNLOAD_ENV, "1")
    assert provider.runtime_ready() is True

    _fake_find_spec(monkeypatch, {"sentence_transformers": None})  # package absent — never ready
    assert provider.runtime_ready() is False


def _fake_fw(monkeypatch, constructed: list) -> None:
    mod = _specful_module("faster_whisper")

    class WhisperModel:
        def __init__(self, model_size, device=None, compute_type=None, download_root=None):
            constructed.append({"model_size": model_size, "device": device,
                                "download_root": download_root})

        def transcribe(self, audio, **kwargs):
            info = types.SimpleNamespace(language="en", language_probability=0.9,
                                         avg_logprob=-0.5)
            segment = types.SimpleNamespace(text="hi", start=0.0, end=0.1, language="en")
            return iter([segment]), info

    mod.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def _fw_provider(**kwargs):
    from gt_ai.stt.faster_whisper import FasterWhisperProvider
    return FasterWhisperProvider(**kwargs)


async def test_whisper_healthcheck_never_loads_the_model(monkeypatch):
    _both_flags_off(monkeypatch)
    constructed: list = []
    _fake_fw(monkeypatch, constructed)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)
    provider = _fw_provider(model_size="small")

    assert await provider.healthcheck() is False
    assert constructed == [], "the admin health poll used to start the download"
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: True)
    assert await provider.healthcheck() is True
    assert constructed == [], "a poll must not load the weights even when cached"


async def test_whisper_transcribe_loads_only_from_cache(monkeypatch):
    _both_flags_off(monkeypatch)
    constructed: list = []
    _fake_fw(monkeypatch, constructed)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)
    provider = _fw_provider(model_size="small")

    with pytest.raises(ProviderUnavailable) as exc:
        await provider.transcribe(b"\x00\x00" * 2000, 16000)
    assert constructed == []
    assert GENERIC_ALLOW_DOWNLOAD_ENV in str(exc.value)

    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: True)
    chunk = await provider.transcribe(b"\x00\x00" * 2000, 16000)
    assert chunk.text == "hi"
    assert constructed[0]["model_size"] == "small"
    assert constructed[0]["download_root"] == provider.cache_dir


async def test_whisper_downloads_only_when_the_operator_opts_in(monkeypatch):
    _both_flags_off(monkeypatch)
    monkeypatch.setenv(GENERIC_ALLOW_DOWNLOAD_ENV, "1")
    constructed: list = []
    _fake_fw(monkeypatch, constructed)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)

    chunk = await _fw_provider(model_size="small").transcribe(b"\x00\x00" * 2000, 16000)
    assert chunk.text == "hi", "an explicit opt-in keeps the documented download path"
    assert constructed and constructed[0]["model_size"] == "small"


def test_whisper_weights_cached_accepts_a_local_dir(tmp_path):
    provider = _fw_provider(model_size=str(tmp_path))
    assert provider._weights_cached() is False
    (tmp_path / "model.bin").write_bytes(b"ct2-weights")
    assert provider._weights_cached() is True  # pure filesystem probe, no network


def _airllm_provider(**kwargs):
    from gt_ai.translation.airllm import AirLLMTranslationProvider
    kwargs.setdefault("model_id", "meta-llama/Llama-3.1-70B-Instruct")
    return AirLLMTranslationProvider(**kwargs)


def test_airllm_never_serves_uncached_70b_weights(monkeypatch):
    real_find_spec = importlib.util.find_spec
    if real_find_spec("airllm") is None:
        provider = _airllm_provider()
        assert provider.runtime_ready() is False, \
            "the package must be installed before anything is offered"

    _both_flags_off(monkeypatch)
    _fake_find_spec(monkeypatch, {"airllm": object()})
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)
    provider = _airllm_provider()
    assert provider.runtime_ready() is False, \
        "the default is Llama-3.1-70B-instruct-sized (>=100 GB); a request must never fetch it"

    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: True)
    assert provider.runtime_ready() is True, "cached weights ARE servable"

    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)
    monkeypatch.setenv(GENERIC_ALLOW_DOWNLOAD_ENV, "1")
    assert provider.runtime_ready() is True

    _fake_find_spec(monkeypatch, {"airllm": None})  # package absent — never ready
    assert provider.runtime_ready() is False


async def test_airllm_load_path_refuses_uncached_weights(monkeypatch):
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)
    with pytest.raises(ProviderUnavailable) as exc:
        await _airllm_provider()._load_model()
    assert "Llama-3.1-70B" in str(exc.value), "the operator sees which model failed the gate"


# --------------------------------------------------------------------------- #
# The voice-transcribe route
# --------------------------------------------------------------------------- #
def test_voice_transcribe_model_is_cache_first(monkeypatch):
    from app.config import settings
    from app.routers import translate as translate_mod

    constructed: list = []
    _fake_fw(monkeypatch, constructed)
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(translate_mod, "_whisper_instance", None)
    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: False)

    assert translate_mod._get_whisper_model() is None, \
        "cache-first: None hands off to the AIFacade chain instead of downloading"
    assert constructed == []

    monkeypatch.setattr(model_fetch, "hf_artifact_cached", lambda *a, **k: True)
    assert translate_mod._get_whisper_model() is not None
    assert constructed[-1]["model_size"] == "tiny"
    assert constructed[-1]["download_root"] == str(settings.model_cache_path), \
        "the tiny weights must land in MODEL_CACHE_PATH, not the default HF cache"


# --------------------------------------------------------------------------- #
# The legacy ai/providers lane (self-contained gates)
# --------------------------------------------------------------------------- #
def _legacy(name: str):
    return importlib.import_module(name)


def test_legacy_whisper_health_never_loads(monkeypatch):
    legacy = _legacy("ai.providers.stt.faster_whisper")
    _both_flags_off(monkeypatch)
    loads: list = []

    def _must_not_load(*args, **kwargs):
        loads.append(1)
        raise AssertionError("healthy()/available() must never load the model")

    monkeypatch.setattr(legacy, "load_model", _must_not_load)
    provider = legacy.FasterWhisperSTT(model_size="missing-whisper-xyz")
    assert provider.healthy() is False
    assert provider.available() is False
    assert loads == []


def test_legacy_whisper_load_gates_on_cache(monkeypatch):
    legacy = _legacy("ai.providers.stt.faster_whisper")
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(legacy, "_model", None)
    provider = legacy.FasterWhisperSTT(model_size="missing-whisper-xyz")

    with pytest.raises(LegacyProviderUnavailable) as exc:
        provider.transcribe(b"\x00\x00" * 2000, 16000)
    assert "not present in the local cache" in str(exc.value)
    assert GENERIC_ALLOW_DOWNLOAD_ENV in str(exc.value)


def test_legacy_marian_is_offline_first(monkeypatch):
    legacy = _legacy("ai.providers.translation.marian")
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(os, "environ", dict(os.environ))  # contain the HF_HOME setdefault
    monkeypatch.setattr(legacy, "_models", {})
    loads: list = []

    class _FailLocal:
        @classmethod
        def from_pretrained(cls, repo, *args, local_files_only=False, **kwargs):
            loads.append({"repo": repo, "local_files_only": local_files_only})
            if local_files_only:
                raise OSError("offline miss")
            return cls()

    fake = types.ModuleType("transformers")
    fake.MarianTokenizer = _FailLocal
    fake.MarianMTModel = _FailLocal
    monkeypatch.setitem(sys.modules, "transformers", fake)

    with pytest.raises(LegacyProviderUnavailable) as exc:
        legacy._load("en", "mr")
    assert loads and loads[0]["local_files_only"] is True
    assert loads[0]["repo"] == "Helsinki-NLP/opus-mt-en-mr"
    assert "not present in the local HF cache" in str(exc.value)
    assert "GT_ALLOW_MODEL_DOWNLOAD" in str(exc.value)


def test_legacy_marian_no_longer_forces_network_mode(monkeypatch):
    legacy = _legacy("ai.providers.translation.marian")
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(
        os, "environ",
        {k: v for k, v in os.environ.items() if k != "TRANSFORMERS_OFFLINE"})
    monkeypatch.setattr(legacy, "_models", {})

    fake = types.ModuleType("transformers")

    class _FailLocal:
        @classmethod
        def from_pretrained(cls, repo, *args, local_files_only=False, **kwargs):
            raise OSError("offline miss")

    fake.MarianTokenizer = _FailLocal
    fake.MarianMTModel = _FailLocal
    monkeypatch.setitem(sys.modules, "transformers", fake)

    with pytest.raises(LegacyProviderUnavailable):
        legacy._load("mr", "en")
    assert "TRANSFORMERS_OFFLINE" not in os.environ, \
        "the adapter used to setdefault TRANSFORMERS_OFFLINE=0 (forced network)"


def _fake_argostranslate(monkeypatch, index_calls: list, installs: list,
                         installed_codes: list) -> types.ModuleType:
    class _P:
        def __init__(self, f, t):
            self.from_code = f
            self.to_code = t

    class _DownloadablePkg:
        from_code = "en"
        to_code = "hi"

        def download(self):
            return "package-file"

    def _index():
        index_calls.append(1)
        return []

    package_mod = types.ModuleType("argostranslate.package")
    package_mod._P = _P
    package_mod.update_package_index = _index
    package_mod.get_installed_packages = lambda: [_P(f, t) for f, t in installed_codes]
    package_mod.get_available_packages = lambda: [_DownloadablePkg()]
    package_mod.install_from_path = lambda path: installs.append(path)
    return package_mod


def test_legacy_argos_request_path_is_cache_only(monkeypatch):
    legacy = _legacy("ai.providers.translation.argos")
    _both_flags_off(monkeypatch)
    index_calls: list = []
    installs: list = []
    pkg = _fake_argostranslate(monkeypatch, index_calls, installs, [("hi", "en")])
    monkeypatch.setattr(legacy, "_import_argos", lambda: (object(), pkg))
    monkeypatch.setattr(legacy, "_use_cache_dir", lambda cache: None)
    monkeypatch.setattr(legacy, "_installed_pairs", None)

    have = legacy._ensure_installed()
    assert have == {("hi", "en")}
    assert index_calls == [], "no remote index refresh behind a request"
    assert installs == [], "no package downloads behind a request"


def test_legacy_argos_downloads_only_when_the_operator_opts_in(monkeypatch):
    legacy = _legacy("ai.providers.translation.argos")
    _both_flags_off(monkeypatch)
    monkeypatch.setenv(GENERIC_ALLOW_DOWNLOAD_ENV, "1")
    index_calls: list = []
    installs: list = []
    pkg = _fake_argostranslate(monkeypatch, index_calls, installs, [("hi", "en")])
    monkeypatch.setattr(legacy, "_import_argos", lambda: (object(), pkg))
    monkeypatch.setattr(legacy, "_use_cache_dir", lambda cache: None)
    monkeypatch.setattr(legacy, "_installed_pairs", None)

    have = legacy._ensure_installed()
    assert have == {("hi", "en"), ("en", "hi")}, \
        "the opt-in keeps the documented provisioning flow working"
    assert index_calls == [1] and installs == ["package-file"]


def test_legacy_vad_cache_only(monkeypatch):
    legacy = _legacy("ai.providers.vad")
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(legacy, "_silero_cached", lambda: False)
    import torch
    monkeypatch.setattr(torch.hub, "load",
                        lambda *a, **k: pytest.fail("torch.hub.load is not a cache probe"))
    assert legacy.SileroVAD().healthy() is False, \
        "absent silero weights + no opt-in, and no GitHub clone happens"


async def test_mirror_vad_cache_only(monkeypatch):
    mirror = _legacy("ai.gt_ai.vad")
    _both_flags_off(monkeypatch)
    monkeypatch.setattr(mirror, "_silero_cached", lambda: False)
    import torch
    monkeypatch.setattr(torch.hub, "load",
                        lambda *a, **k: pytest.fail("torch.hub.load is not a cache probe"))
    with pytest.raises(RuntimeError) as exc:
        await mirror.SileroVAD().load()
    assert "GT_ALLOW_MODEL_DOWNLOAD" in str(exc.value), \
        "the operator sees the honest failure instead of a silent GitHub clone"
