"""Argos has to chain two installed models for pairs the package index does not ship.

Argos' own lookup is single-hop: `Language.get_translation()` returns None when there is
no package for that exact pair, so Chinese->Hindi cannot resolve unless we route it
zh->en->hi ourselves and say out loud that we did.
"""
from __future__ import annotations

import pytest

from ai.interfaces import ProviderUnavailable
from ai.providers.translation import argos


class _FakeArgos:
    """Stands in for argostranslate: resolves installed pairs, returns None for the rest."""

    def __init__(self, installed):
        self.installed = installed
        self.calls: list[tuple[str, str]] = []

    def get_translation(self, src, tgt):
        self.calls.append((src, tgt))
        if (src, tgt) not in self.installed:
            # what Argos does downstream when get_translation() handed back None
            raise AttributeError("'NoneType' object has no attribute 'translate'")
        return _Recorder(f"{src}->{tgt}")


class _Recorder:
    def __init__(self, out):
        self.out = out

    def translate(self, text):
        return self.out


def _provider(monkeypatch, installed):
    fake = _FakeArgos(installed)
    monkeypatch.setattr(argos, "_get_translation", fake.get_translation)
    monkeypatch.setattr("ai.memory_guard.is_lowmem", lambda: False)
    p = argos.ArgosTranslation()
    monkeypatch.setattr(p, "supported_pairs", lambda: installed)
    return p, fake


def test_an_unshipped_pair_chains_two_installed_models(monkeypatch):
    p, fake = _provider(monkeypatch, {("zh", "en"), ("en", "hi")})

    result = p.translate("你好，世界", "zh-CN", "hi")

    assert fake.calls == [("zh", "en"), ("en", "hi")]
    assert result.text == "en->hi"          # the second hop consumed the first hop's output
    assert result.pivoted is True
    assert result.quality_flags == ["pivoted_via_intermediate"]
    assert result.model == "argos-zh-en+en-hi"
    assert result.confidence == 0.6


def test_a_shipped_pair_stays_single_hop(monkeypatch):
    p, fake = _provider(monkeypatch, {("zh", "en"), ("en", "hi")})

    result = p.translate("hello", "en", "hi")

    assert fake.calls == [("en", "hi")]
    assert result.pivoted is False
    assert result.quality_flags == []
    assert result.model == "argos-en-hi"
    assert result.confidence == 0.9


def test_no_pivot_is_invented_when_no_hub_connects_the_pair(monkeypatch):
    p, fake = _provider(monkeypatch, {("en", "hi")})

    with pytest.raises(ProviderUnavailable):
        p.translate("greetings", "fr", "de")

    assert fake.calls == [("fr", "de")], "must attempt the real pair once, then fail honestly"
