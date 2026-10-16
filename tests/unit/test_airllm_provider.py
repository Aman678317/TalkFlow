from __future__ import annotations

import pytest

from gt_ai.translation.airllm import AirLLMTranslationProvider
from gt_ai.types import Intent, ProviderUnavailable, TranslationRequest


@pytest.mark.asyncio
async def test_airllm_fails_closed_when_optional_package_is_missing(monkeypatch):
    provider = AirLLMTranslationProvider(
        model_id="meta-llama/Llama-3.1-70B-Instruct",
        layer_shards_saving_path="",
    )

    async def missing_optional_dependency():
        raise ProviderUnavailable("AirLLM is not installed")

    monkeypatch.setattr(provider, "_load_model", missing_optional_dependency)
    # This test stays offline and never downloads weights.
    with pytest.raises(ProviderUnavailable, match="AirLLM"):
        await provider.translate(TranslationRequest(
            text="Hello world",
            source_lang="en",
            target_lang="hi",
            intent=Intent.QUALITY_OPTIMIZED,
        ))
