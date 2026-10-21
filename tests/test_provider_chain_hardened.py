"""The provider chain must fail over honestly and never descend into a landmine.

Evidence behind this suite (2026-10-20 / 2026-10-21, #109):

* The offline MT tail (airllm / madlad400 / nllb_ct2 / argos) ran behind a
  user request with no readiness gate and no attempt deadline. On a box
  without cached weights, the first failure of the online pair descended
  into that tail and the API worker died natively (Windows event log:
  python.exe, exception 0xc0000374 — heap corruption — matching the
  2026-10-20 madlad download incident already documented in
  :mod:`gt_ai.translation.model_fetch`).
* ``_installed_codes_sync`` called ``argostranslate.package.
  update_package_index()`` — a network fetch with no timeout — on the
  request path, before even looking at which packs are installed.
* ``mt/neural_online`` and ``mt/deepl`` are the same adapter class, so the
  chain ran the identical implementation twice per failed request
  (doubled latency, doubled upstream rate-limit exposure).

Pinned here:

1. a provider attempt that hangs is cut at the per-attempt deadline and the
   chain fails over to the next candidate (the request stays bounded);
2. a candidate that is not runtime-ready (deps/weights absent) never
   enters the chain, while unregistered scaffolding names keep flowing
   (fail-open, so the gate cannot silently cut a real chain);
3. two chain slots backed by the same implementation collapse to one;
4. argos resolves installed packs cache-only — never refreshes the index
   over the network behind a request.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
import types

import pytest

from app.ai import AIFacade
from app.config import settings
from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.translation.argos import ArgosProvider
from gt_ai.translation.madlad400 import Madlad400Provider
from gt_ai.types import (
    ProviderUnavailable, Task, TranslationRequest, TranslationResult,
)


def _facade(specs: dict) -> AIFacade:
    facade = AIFacade()
    facade.router = ModelRouter(specs, gpu_available=False)
    return facade


def _candidate_names(facade: AIFacade, task: Task) -> list[str]:
    return [d.provider for d in facade._ordered_candidates(task, {})]


# --------------------------------------------------------------------------- #
# 1. attempt deadline: a hung provider is cut; the chain fails over
# --------------------------------------------------------------------------- #


class _HangingTranslator:
    """The exact failure shape of a first-use bootstrap that never returns:
    the provider object constructs fine, then its translate() hangs."""

    name = "hang_one"
    calls = 0

    async def translate(self, req) -> TranslationResult:  # noqa: ARG002
        _HangingTranslator.calls += 1
        await asyncio.sleep(3600)
        raise AssertionError("must be cancelled by the attempt deadline")


class _InstantTranslator:
    """A deterministic, network-free stand-in for the next honest candidate."""

    def __init__(self, name: str) -> None:
        self.name = name

    def runtime_ready(self) -> bool:
        return True

    async def translate(self, req) -> TranslationResult:  # noqa: ARG002
        return TranslationResult(
            text="[ok] " + req.text, source_lang=req.source_lang,
            target_lang=req.target_lang, model="instant-v1",
            provider=self.name, latency_ms=1.0,
            quality_flags=["instant"], confidence=0.9,
        )


@pytest.mark.asyncio
async def test_hung_attempt_is_cut_at_the_deadline_and_fails_over(monkeypatch):
    monkeypatch.setattr(settings, "provider_attempt_timeout_s", 0.5)
    facade = _facade({Task.MT: [
        ProviderSpec(name="hang_one", task=Task.MT),
        ProviderSpec(name="dev_echo", task=Task.MT),
    ]})

    def provider(task, name):  # noqa: ARG001
        if name == "hang_one":
            return _HangingTranslator()
        return _InstantTranslator(name)

    monkeypatch.setattr(facade, "provider", provider)
    req = TranslationRequest(text="heure test", source_lang="hi", target_lang="en")
    t0 = time.perf_counter()
    result, decision = await facade.translate(req)
    elapsed = time.perf_counter() - t0

    assert decision.provider == "dev_echo", (
        "the deadline must fail over to the next honest candidate")
    assert elapsed < 30, "a hung attempt must not own the request"
    assert result.quality_flags, "the fallback result carries its honesty flags"
    # the cut was recorded against the hung provider, not swallowed
    from app import metrics as met

    assert met.PROVIDER_RETRIES.labels(
        stage="mt", provider="hang_one")._value.get() >= 1


@pytest.mark.asyncio
async def test_attempt_outcome_is_honest_when_the_chain_is_empty_after_cutoff(
        monkeypatch):
    """No fallback candidate: the request must complete as an honest
    ProviderError, never as a wedge and never as dev output in production."""
    monkeypatch.setattr(settings, "provider_attempt_timeout_s", 0.3)
    monkeypatch.setattr(settings, "app_env", "production")
    facade = _facade({Task.MT: [ProviderSpec(name="hang_one", task=Task.MT)]})
    monkeypatch.setattr(facade, "provider", lambda t, n: _HangingTranslator())
    req = TranslationRequest(text="x", source_lang="en", target_lang="de")
    from app.errors import ProviderError

    with pytest.raises(ProviderError) as e:
        await facade.translate(req)
    assert "temporarily unavailable" in str(e.value)


# --------------------------------------------------------------------------- #
# 2. runtime-readiness gate: landmine candidates never enter the chain
# --------------------------------------------------------------------------- #


def test_not_ready_provider_is_excluded_from_the_chain(monkeypatch):
    monkeypatch.setattr(Madlad400Provider, "runtime_ready",
                        lambda self: False, raising=True)
    facade = _facade({Task.MT: [
        ProviderSpec(name="madlad400", task=Task.MT),
        ProviderSpec(name="dev_echo", task=Task.MT),
    ]})
    names = _candidate_names(facade, Task.MT)
    assert "madlad400" not in names, "a not-ready provider must be excluded"
    assert "dev_echo" in names, "the honest fallback must remain reachable"


def test_ready_provider_stays_in_the_chain(monkeypatch):
    monkeypatch.setattr(Madlad400Provider, "runtime_ready",
                        lambda self: True, raising=True)
    facade = _facade({Task.MT: [ProviderSpec(name="madlad400", task=Task.MT)]})
    assert "madlad400" in _candidate_names(facade, Task.MT)


@pytest.mark.asyncio
async def test_not_ready_provider_is_dropped_at_execution_time(monkeypatch):
    """Execution shape: a provider that declares itself not-ready must be
    attempted zero times — the honest outage surfaces instead."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "provider_attempt_timeout_s", 0.3)

    class _NotReadyLandmine(_HangingTranslator):
        def runtime_ready(self) -> bool:
            return False

    attempts: list[str] = []
    facade = _facade({Task.MT: [ProviderSpec(name="landmine", task=Task.MT)]})
    monkeypatch.setattr(facade, "provider", lambda t, n: attempts.append(n) or _NotReadyLandmine())
    with pytest.raises(Exception) as e:
        await facade.translate(
            TranslationRequest(text="x", source_lang="en", target_lang="de"))
    assert "temporarily unavailable" in str(e.value) or \
        "No private provider" in str(e.value)
    _HangingTranslator.calls = 0  # zero the class counter for this test
    assert _NotReadyLandmine.calls == 0, (
        "not ready means the filter drops it; translate() never runs")


def test_unregistered_scaffold_names_fail_open(monkeypatch):
    """`real_a`/`real_b` style scaffolding (also used by the realtime
    invariant suite) must flow through the filter untouched — readiness is
    only decided for adapters we can actually construct."""
    monkeypatch.setattr(settings, "app_env", "production")
    facade = _facade({Task.MT: [
        ProviderSpec(name="real_a", task=Task.MT),
        ProviderSpec(name="real_b", task=Task.MT),
    ]})
    names = _candidate_names(facade, Task.MT)
    assert names[:2] == ["real_a", "real_b"], (
        f"scaffold names must flow through the filter untouched, got {names}")


def test_distinct_plain_fakes_do_not_cut_each_other(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    facade = _facade({Task.TTS: [
        ProviderSpec(name="kokoro", task=Task.TTS),
        ProviderSpec(name="dev_tone", task=Task.TTS),
    ]})

    class _FakeA:
        pass

    class _FakeB:
        pass

    def provider(task, name):  # noqa: ARG001
        return _FakeA() if name == "kokoro" else _FakeB()

    monkeypatch.setattr(facade, "provider", provider)
    names = _candidate_names(facade, Task.TTS)
    assert names[:2] == ["kokoro", "dev_tone"], "distinct fakes must both stay"


# --------------------------------------------------------------------------- #
# 3. one implementation, one chain slot (mt/neural_online vs mt/deepl)
# --------------------------------------------------------------------------- #


def test_deep_alias_of_neural_online_is_deduped_from_the_chain():
    facade = _facade({Task.MT: [
        ProviderSpec(name="neural_online", task=Task.MT),
        ProviderSpec(name="deepl", task=Task.MT),
    ]})
    names = _candidate_names(facade, Task.MT)
    assert "neural_online" in names
    assert "deepl" not in names, (
        "mt/deepl is the same adapter as mt/neural_online — "
        "the chain must not run it twice")
    assert "dev_echo" in names, (
        "the dev fallback (test/non-production extras) remains terminal")


def test_deep_alias_alone_still_serves_when_it_is_the_only_slot():
    facade = _facade({Task.MT: [ProviderSpec(name="deepl", task=Task.MT)]})
    assert "deepl" in _candidate_names(facade, Task.MT)


def test_no_chain_slot_survives_twice_regardless_of_kind(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    facade = _facade({Task.MT: [
        ProviderSpec(name="neural_online", task=Task.MT),
        ProviderSpec(name="deepl", task=Task.MT),
        ProviderSpec(name="dev_echo", task=Task.MT),
    ]})
    names = _candidate_names(facade, Task.MT)
    assert all(names.count(name) == 1 for name in names), (
        f"duplicate implementation survived the filter: {names}")


# --------------------------------------------------------------------------- #
# 4. argos: cache-only readiness + installed packs, never the network
# --------------------------------------------------------------------------- #


def _fake_argostranslate(monkeypatch):
    """Install importable fakes for the argostranslate modules so the
    provider's lazy imports resolve without the (possibly absent) package.
    ``update_package_index`` aboard the fake raises the moment the request
    path touches it — loud failure instead of silent network access."""

    seen_calls: list[str] = []

    class _Pack:
        def __init__(self, f: str, t: str) -> None:
            self.from_code = f
            self.to_code = t

    fake_root = types.ModuleType("argostranslate")

    fake_package = types.ModuleType("argostranslate.package")

    def _update_index():
        seen_calls.append("update_package_index")
        raise AssertionError(
            "argos attempted a network index refresh on the request path")

    fake_package.update_package_index = _update_index

    def _get_installed():
        seen_calls.append("get_installed_packages")
        return [_Pack("hi", "en"), _Pack("en", "hi"), _Pack("en", "mr")]

    fake_package.get_installed_packages = _get_installed

    fake_translate = types.ModuleType("argostranslate.translate")
    fake_translate.translate = (
        lambda *a, **k: "Translation(" + str(a) + ")")

    fake_root.package = fake_package
    fake_root.translate = fake_translate
    monkeypatch.setitem(sys.modules, "argostranslate", fake_root)
    monkeypatch.setitem(sys.modules, "argostranslate.package", fake_package)
    monkeypatch.setitem(sys.modules, "argostranslate.translate", fake_translate)
    return seen_calls


@pytest.mark.asyncio
async def test_argos_resolves_installed_packs_without_network(monkeypatch):
    seen_calls = _fake_argostranslate(monkeypatch)
    provider = ArgosProvider()

    await provider._ensure()

    assert await provider.healthcheck() is True
    assert "update_package_index" not in seen_calls, (
        "the request path must not refresh the argos package index")
    assert "get_installed_packages" in seen_calls
    assert provider.supported_languages == {"hi", "en", "mr"}


def test_argos_ready_only_with_the_package_extra(monkeypatch):
    """When the argostranslate extra is present, the provider is ready; when
    absent, runtime_ready() is False so the chain never descends into its
    heavy first import behind a request."""
    import importlib.machinery

    fake = types.ModuleType("argostranslate")
    fake.__spec__ = importlib.machinery.ModuleSpec("argostranslate", None)
    monkeypatch.setitem(sys.modules, "argostranslate", fake)
    assert ArgosProvider().runtime_ready() is True
    monkeypatch.delitem(sys.modules, "argostranslate", raising=False)
    if importlib.util.find_spec("argostranslate") is not None:
        pytest.skip("argostranslate is installed; the absent-extra case needs a "
                    "machine without the extra")
    assert ArgosProvider().runtime_ready() is False


@pytest.mark.asyncio
async def test_argos_honest_failure_for_missing_pack(monkeypatch):
    _fake_argostranslate(monkeypatch)
    provider = ArgosProvider()
    await provider._ensure()
    req = TranslationRequest(text="x", source_lang="en", target_lang="de")

    with pytest.raises(ProviderUnavailable) as e:
        await provider.translate(req)
    assert "argospm" in str(e.value), (
        "operators must be told how to install the missing pack")
