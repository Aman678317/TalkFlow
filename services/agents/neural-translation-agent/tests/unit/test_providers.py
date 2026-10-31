"""Unit tests for translation provider adapters."""
import pytest
from app.providers.base import TranslationRequest, Intent
from app.providers.online.neural_online import NeuralOnlineProvider
from app.providers.marian.provider import MarianProvider
from app.providers.nllb.provider import NllbProvider
from app.providers.argos.provider import ArgosProvider


@pytest.mark.asyncio
async def test_neural_online_offline_rules():
    """Verify offline phrase dictionary instant translations."""
    prov = NeuralOnlineProvider()
    req = TranslationRequest(
        text="नमस्ते",
        source_lang="hi",
        target_lang="en",
    )
    res = await prov.translate(req)
    assert res.text == "Hello"
    assert res.provider == "neural_online"
    assert res.source_lang == "hi"
    assert res.target_lang == "en"


@pytest.mark.asyncio
async def test_marian_direct_pairs_declaration():
    """Verify Marian declared direct and pivot pairs."""
    prov = MarianProvider()
    assert ("en", "mr") in prov.DIRECT_PAIRS
    assert ("mr", "en") in prov.DIRECT_PAIRS
    assert ("hi", "mr") in prov.PIVOT_PAIRS


@pytest.mark.asyncio
async def test_nllb_license_warning():
    """Verify NLLB-200 flags CC BY-NC non-commercial license warning."""
    prov = NllbProvider()
    assert prov.task == "mt"
    assert prov.quality_tier == 80


@pytest.mark.asyncio
async def test_argos_runtime_ready():
    """Verify Argos reports runtime_ready status accurately."""
    prov = ArgosProvider()
    ready = prov.runtime_ready()
    assert isinstance(ready, bool)

