"""The private-only guarantee must hold on EVERY task (issue #109, class 3).

Evidence behind this suite (2026-10-21, sweep #109 cluster 3):

1. ``app/ai.py`` set ``tenant_preference = req.tenant_private_only and
   "private_only" or None`` — ``tenant_preference`` is a provider NAME in
   the router (``+25`` when ``p.name == tenant_preference``), so the literal
   matched nothing and the tenant-level private flag had ZERO effect. The
   flag never reached ``intent=PRIVATE_ONLY``.
2. ``detect_language`` / ``transcribe`` / ``synthesize`` / ``summarize`` /
   ``embed`` all called ``_execute(task, {}, ...)``: no intent, so the
   private filter never applied and a cloud provider was reachable on every
   one of them. ``translate_stream`` dropped the tenant flag and
   ``synthesize_stream`` passed no intent at all.
3. The fallback ``ProviderSpec``s for STT/TTS/LANG_DETECT/SUMMARIZE/EMBED
   were built without ``private=`` and inherited the dataclass default
   ``private=True`` — the router was told a cloud provider was PRIVATE, so
   the private_only hard filter could not exclude it.
4. ``_configured_name()`` never returns ``"auto"``: with the default
   ``TRANSLATION_PROVIDER=auto`` it resolved to the CLOUD translator, which
   then received the ``priority += 2000`` boost for every MT request.
5. The seeded ``*_http`` providers were hard-seeded ``private=True`` while
   posting request content to an arbitrary ``settings.*_url`` — nothing
   verified the destination was on-tenant.
6. ``WriteRequest`` had no intent field and ``_neural_rewrite()`` called
   the LLM HTTP client DIRECTLY, bypassing the router.
7. The realtime pipeline and the telephony bridge hard-coded a latency
   intent, so a live meeting could never be routed private-only.

Pinned here: the tenant flag reaches the router as ``PRIVATE_ONLY`` on every
task (including the stream paths), the specs tell the truth about privacy,
the default configuration is local-first, the HTTP endpoints are private only
on an explicit operator opt-in, Write honours a private request, and the
realtime/telephony paths carry the meeting/call flag.
"""
from __future__ import annotations

import uuid

import pytest

from app.ai import AUTO_PROVIDER_ORDER, AIFacade
from app.config import settings
from app.errors import ProviderError
from gt_ai.model_router.router import ModelRouter, ProviderSpec, provider_is_private
from gt_ai.types import (
    AudioChunk, DetectionResult, Intent, Task, TranscriptChunk, TranslationRequest,
    TranslationResult,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _force_settings(monkeypatch, **values) -> None:
    """Force a setting on EVERY module-level binding of the settings object.

    ``tests/conftest.py``'s session ``app`` fixture reloads ``app.config``,
    which forks the module-owned ``settings`` bindings from the current
    singleton — a monkeypatch on one instance can silently miss the instance
    the code under test actually reads (the convention the Asterisk adapter
    test follows for the same reason).
    """
    import app.config
    import app.ai
    import app.seed
    import app.services.write_service as write_service_mod
    import app.routers.translate as translate_mod
    seen: set[int] = set()
    for mod in (app.config, app.ai, app.seed, write_service_mod, translate_mod):
        obj = getattr(mod, "settings", None)
        if obj is None or id(obj) in seen:
            continue
        seen.add(id(obj))
        for key, value in values.items():
            monkeypatch.setattr(obj, key, value, raising=False)


def _facade(specs: dict) -> AIFacade:
    facade = AIFacade()
    facade.router = ModelRouter(specs, gpu_available=False)
    return facade


class _RecordingProvider:
    """A provider that records every call — the cloud stand-in."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []

    def runtime_ready(self) -> bool:
        return True

    async def translate(self, req) -> TranslationResult:
        self.calls.append("translate")
        return TranslationResult(text="[cloud]", source_lang=req.source_lang,
                                 target_lang=req.target_lang, model="cloud", provider=self.name,
                                 latency_ms=1.0)

    async def transcribe(self, audio, sample_rate, lang_hint=None):
        self.calls.append("transcribe")
        return TranscriptChunk(text="[cloud]", language="en", is_final=True,
                               provider=self.name)

    async def synthesize(self, text, lang, voice=None):
        self.calls.append("synthesize")
        return AudioChunk(data=b"", sample_rate=16000, provider=self.name)

    async def detect(self, text):
        self.calls.append("detect")
        return DetectionResult(language="en", confidence=1.0, provider=self.name)

    async def summarize(self, text, instruction="", max_length=400, lang="en"):
        self.calls.append("summarize")
        return "[cloud]"

    async def extract_structured(self, text, lang="en"):
        self.calls.append("extract_structured")
        return {}

    async def embed(self, texts):
        self.calls.append("embed")
        return [[0.0] for _ in texts]


class _LocalProvider(_RecordingProvider):
    async def translate(self, req) -> TranslationResult:
        self.calls.append("translate")
        return TranslationResult(text="[local]", source_lang=req.source_lang,
                                 target_lang=req.target_lang, model="local", provider=self.name,
                                 latency_ms=1.0)


CLOUD = ProviderSpec(name="neural_online", task=Task.MT, private=False, quality_tier=99)
LOCAL = ProviderSpec(name="madlad400", task=Task.MT, private=True, quality_tier=85)


# --------------------------------------------------------------------------- #
# 1. the privacy classification itself
# --------------------------------------------------------------------------- #
def test_cloud_providers_are_not_private_and_local_ones_are():
    assert provider_is_private("neural_online") is False
    assert provider_is_private("deepl") is False
    assert provider_is_private("azure_speech") is False
    assert provider_is_private("mt_http") is False
    assert provider_is_private("madlad400") is True
    assert provider_is_private("faster_whisper") is True
    assert provider_is_private("piper") is True


def test_operator_opt_in_overrides_the_http_classification():
    assert provider_is_private("stt_http") is False
    assert provider_is_private("stt_http", {"stt_http"}) is True


def test_auto_order_is_local_first():
    """Finding 4: the default configuration is on-tenant inference."""
    for task, order in AUTO_PROVIDER_ORDER.items():
        assert order, f"{task} has no auto order"
        first = order[0]
        assert provider_is_private(first), (
            f"{task} defaults to a non-private provider ({first})")
    assert AUTO_PROVIDER_ORDER[Task.MT][0] == "madlad400"
    assert AUTO_PROVIDER_ORDER[Task.SUMMARIZE][0] == "extractive"
    # the cloud tier is still reachable — as an explicit choice, not a default
    assert "neural_online" in AUTO_PROVIDER_ORDER[Task.MT]


# --------------------------------------------------------------------------- #
# 2. the specs the router sees must tell the truth
# --------------------------------------------------------------------------- #
def test_fallback_specs_carry_the_real_privacy_flag(monkeypatch):
    facade = AIFacade()
    _force_settings(monkeypatch, stt_provider="auto")
    specs = facade._fallback_specs()
    assert specs[Task.STT][0].private is True, "the local default stays private"
    assert specs[Task.MT][0].private is True, "the local MT default stays private"


def test_a_configured_cloud_provider_is_not_marked_private(monkeypatch):
    """Finding 3: the cloud spec used to inherit private=True."""
    facade = AIFacade()
    _force_settings(monkeypatch, stt_provider="azure_speech")
    spec = facade._fallback_specs()[Task.STT][0]
    assert spec.name == "azure_speech"
    assert spec.private is False, (
        "a cloud provider must not be advertised as private")


def test_http_provider_is_not_private_without_the_opt_in(monkeypatch):
    facade = AIFacade()
    _force_settings(monkeypatch, stt_provider="stt_http")
    _force_settings(monkeypatch, stt_http_private=False)
    assert facade._fallback_specs()[Task.STT][0].private is False
    _force_settings(monkeypatch, stt_http_private=True)
    assert facade._fallback_specs()[Task.STT][0].private is True


def test_auto_is_not_an_explicit_operator_choice(monkeypatch):
    """Finding 4: only a NAMED provider counts as operator preference."""
    facade = AIFacade()
    _force_settings(monkeypatch, translation_provider="auto")
    assert facade._explicitly_configured(Task.MT) is None
    _force_settings(monkeypatch, translation_provider="neural_online")
    assert facade._explicitly_configured(Task.MT) == "neural_online"


def _seeded_mt_specs() -> list[ProviderSpec]:
    """The REAL seeded MT capability numbers (app.seed.MODEL_REGISTRY_SEED)."""
    from app.seed import MODEL_REGISTRY_SEED
    return [
        ProviderSpec(name=provider, task=Task(task), quality_tier=q, cost_tier=c,
                     latency_class=lat, private=provider_is_private(provider))
        for _name, task, provider, q, c, lat, _p, _g in MODEL_REGISTRY_SEED
        if task == "mt"
    ]


def test_the_seeded_registry_ranks_a_local_provider_first(monkeypatch):
    """The default configuration must actually serve the local provider.

    Uses the REAL seeded capability numbers, because the ranking is a score,
    not a list position.
    """
    _force_settings(monkeypatch, translation_provider="auto")
    specs = _seeded_mt_specs()
    facade = AIFacade()
    facade._apply_priority_policy({Task.MT: specs})
    router = ModelRouter({Task.MT: specs}, gpu_available=False)
    decision = router.route(Task.MT, source_lang="en", target_lang="de",
                             intent=Intent.QUALITY_OPTIMIZED)
    assert provider_is_private(decision.provider), (
        f"the default MT routing must not start at a cloud provider "
        f"(chose {decision.provider})")


def test_an_explicitly_configured_cloud_provider_still_wins(monkeypatch):
    """The operator's explicit choice is honored (that IS the opt-in)."""
    _force_settings(monkeypatch, translation_provider="neural_online")
    specs = _seeded_mt_specs()
    facade = AIFacade()
    facade._apply_priority_policy({Task.MT: specs})
    router = ModelRouter({Task.MT: specs}, gpu_available=False)
    decision = router.route(Task.MT, source_lang="en", target_lang="de",
                             intent=Intent.QUALITY_OPTIMIZED)
    assert decision.provider == "neural_online", (
        "an explicitly configured cloud provider keeps the operator's opt-in")


# --------------------------------------------------------------------------- #
# 3. the tenant flag must reach the router as PRIVATE_ONLY
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_tenant_private_flag_routes_to_the_private_provider(monkeypatch):
    facade = _facade({Task.MT: [CLOUD, LOCAL]})
    cloud, local = _RecordingProvider("neural_online"), _LocalProvider("madlad400")
    monkeypatch.setattr(facade, "provider", lambda t, n: cloud if n == "neural_online" else local)
    req = TranslationRequest(text="x", source_lang="en", target_lang="de",
                             tenant_private_only=True)
    _result, decision = await facade.translate(req)
    assert decision.provider == "madlad400", "the tenant flag must skip the cloud provider"
    assert cloud.calls == [], "the cloud provider must not be called"


@pytest.mark.asyncio
async def test_tenant_private_flag_fails_honestly_without_a_private_provider(monkeypatch):
    facade = _facade({Task.MT: [CLOUD]})
    cloud = _RecordingProvider("neural_online")
    monkeypatch.setattr(facade, "provider", lambda t, n: cloud)
    req = TranslationRequest(text="x", source_lang="en", target_lang="de",
                             tenant_private_only=True)
    with pytest.raises(ProviderError) as exc:
        await facade.translate(req)
    assert "not sent to any external service" in str(exc.value)
    assert cloud.calls == [], "the content must never reach the cloud provider"


@pytest.mark.asyncio
async def test_the_per_request_intent_still_works(monkeypatch):
    facade = _facade({Task.MT: [CLOUD, LOCAL]})
    cloud, local = _RecordingProvider("neural_online"), _LocalProvider("madlad400")
    monkeypatch.setattr(facade, "provider", lambda t, n: cloud if n == "neural_online" else local)
    req = TranslationRequest(text="x", source_lang="en", target_lang="de",
                             intent=Intent.PRIVATE_ONLY)
    _result, decision = await facade.translate(req)
    assert decision.provider == "madlad400"


@pytest.mark.asyncio
async def test_every_task_honors_the_private_intent(monkeypatch):
    """Finding 2: STT, TTS, detection, summarization and embeddings."""
    tasks = {
        Task.STT: [ProviderSpec(name="azure_speech", task=Task.STT, private=False)],
        Task.TTS: [ProviderSpec(name="azure_speech_tts", task=Task.TTS, private=False)],
        Task.LANG_DETECT: [ProviderSpec(name="stt_http", task=Task.LANG_DETECT, private=False)],
        Task.SUMMARIZE: [ProviderSpec(name="llm_http", task=Task.SUMMARIZE, private=False)],
        Task.EMBED: [ProviderSpec(name="sentence_transformers", task=Task.EMBED, private=True)],
    }
    facade = _facade(tasks)
    cloud = _RecordingProvider("cloud")
    monkeypatch.setattr(facade, "provider", lambda t, n: cloud)

    with pytest.raises(ProviderError):
        await facade.transcribe(b"\x00\x01", 16000, intent=Intent.PRIVATE_ONLY)
    with pytest.raises(ProviderError):
        await facade.synthesize("hi", "en", intent=Intent.PRIVATE_ONLY)
    with pytest.raises(ProviderError):
        await facade.detect_language("hello", intent=Intent.PRIVATE_ONLY)
    with pytest.raises(ProviderError):
        await facade.summarize("hello", intent=Intent.PRIVATE_ONLY)
    assert cloud.calls == [], "no cloud provider may be called for a private request"


@pytest.mark.asyncio
async def test_translate_stream_honors_the_tenant_flag(monkeypatch):
    """Finding 2: the stream path dropped the tenant flag entirely."""
    facade = _facade({Task.MT: [CLOUD]})
    cloud = _RecordingProvider("neural_online")
    monkeypatch.setattr(facade, "provider", lambda t, n: cloud)
    req = TranslationRequest(text="x", source_lang="en", target_lang="de",
                             tenant_private_only=True)
    with pytest.raises(ProviderError) as exc:
        await facade.translate_stream(req)
    assert "not sent to any external service" in str(exc.value)
    assert cloud.calls == [], "the stream path must not reach the cloud provider"


@pytest.mark.asyncio
async def test_synthesize_stream_honors_the_private_intent(monkeypatch):
    facade = _facade({Task.TTS: [
        ProviderSpec(name="azure_speech_tts", task=Task.TTS, private=False)]})
    cloud = _RecordingProvider("cloud")
    monkeypatch.setattr(facade, "provider", lambda t, n: cloud)
    with pytest.raises(ProviderError) as exc:
        await facade.synthesize_stream("hi", "en", intent=Intent.PRIVATE_ONLY)
    assert "not sent to any external service" in str(exc.value)
    assert cloud.calls == [], "the stream path must not reach the cloud provider"


# --------------------------------------------------------------------------- #
# 4. the seeded HTTP providers follow the operator's privacy flag
# --------------------------------------------------------------------------- #
class _FakeRow:
    def __init__(self, private: bool) -> None:
        self.private = private


class _FakeResult:
    def __init__(self, row) -> None:
        self._row = row

    def scalars(self):
        return self

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, row=None) -> None:
        self.row = row
        self.added: list = []

    async def execute(self, *args, **kwargs):  # noqa: ARG002
        return _FakeResult(self.row)

    def add(self, obj) -> None:
        self.added.append(obj)


@pytest.mark.asyncio
async def test_seed_inserts_the_http_rows_with_the_flag_privacy(monkeypatch):
    from app.seed import seed_model_registry
    _force_settings(monkeypatch, mt_http_private=False)
    db = _FakeDB(row=None)
    await seed_model_registry(db)
    mt_rows = [r for r in db.added if getattr(r, "provider", "") == "mt_http"]
    assert mt_rows, "the mt_http registry row must be seeded"
    assert mt_rows[0].private is False, (
        "an operator HTTP endpoint is not private without the explicit opt-in")


@pytest.mark.asyncio
async def test_seed_reapplies_the_flag_to_existing_rows(monkeypatch):
    """The seed is insert-only; an existing row must still be corrected."""
    from app.seed import seed_model_registry
    _force_settings(monkeypatch, mt_http_private=False)
    row = _FakeRow(private=True)
    db = _FakeDB(row=row)
    await seed_model_registry(db)
    assert row.private is False, (
        "a stale private=True on the HTTP row must be corrected by the seed")


@pytest.mark.asyncio
async def test_seed_marks_the_http_row_private_with_the_opt_in(monkeypatch):
    from app.seed import seed_model_registry
    _force_settings(monkeypatch, llm_http_private=True)
    db = _FakeDB(row=None)
    await seed_model_registry(db)
    llm_rows = [r for r in db.added if getattr(r, "provider", "") == "llm_http"]
    assert llm_rows and llm_rows[0].private is True, (
        "the operator opt-in must mark the endpoint private")


# --------------------------------------------------------------------------- #
# 5. Write must not post the text to an unclassified endpoint
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_private_write_skips_the_llm_http_tier(monkeypatch):
    from app.services import write_service
    _force_settings(monkeypatch, llm_http_url="https://llm.example.invalid/v1")
    _force_settings(monkeypatch, llm_http_private=False)
    constructed: list = []

    class _Boom:
        def __init__(self, *a, **k) -> None:
            constructed.append(1)
            raise AssertionError("the LLM HTTP tier must not be constructed")

    import gt_ai.summarize.llm_http as llm_http
    monkeypatch.setattr(llm_http, "LlmHttpSummarizer", _Boom)
    out = await write_service._neural_rewrite("some text", language="en", style="business",
                                              tone="professional", corrections_only=False,
                                              private_only=True)
    assert out is None, "a private write must fall back to the offline rule engine"
    assert constructed == [], "the endpoint must not be contacted at all"


@pytest.mark.asyncio
async def test_non_private_write_still_uses_the_llm_tier(monkeypatch):
    from app.services import write_service
    _force_settings(monkeypatch, llm_http_url="https://llm.example.invalid/v1")
    _force_settings(monkeypatch, llm_http_private=False)
    used: list = []

    class _Fake:
        def __init__(self, *a, **k) -> None:
            used.append(1)

        async def _chat(self, system, user):  # noqa: ARG002
            return "improved text"

    import gt_ai.summarize.llm_http as llm_http
    monkeypatch.setattr(llm_http, "LlmHttpSummarizer", _Fake)
    out = await write_service._neural_rewrite("some text", language="en", style="business",
                                              tone="professional", corrections_only=False)
    assert out is not None, "a normal write keeps using the neural tier"
    assert used == [1]


# --------------------------------------------------------------------------- #
# 6. a live meeting / call can be routed private-only
# --------------------------------------------------------------------------- #
def test_realtime_translate_context_carries_the_meeting_flag():
    from app.realtime.pipeline import MeetingPipeline
    from app.realtime.session_manager import RtSession
    session = RtSession(session_id="s", meeting_id=uuid.uuid4(), org_id=uuid.uuid4(),
                        room_name="r", mode="ws", tenant_private_only=True)
    pipeline = MeetingPipeline.__new__(MeetingPipeline)
    pipeline.session = session
    ctx = pipeline._translate_context("seg", ["hello"])
    assert ctx.tenant_private_only is True, (
        "the meeting's private flag must reach the translation context")


def test_a_meeting_session_carries_the_private_flag():
    from app.realtime.session_manager import RtSession
    session = RtSession(session_id="s", meeting_id=uuid.uuid4(), org_id=uuid.uuid4(),
                        room_name="r", mode="ws")
    assert session.tenant_private_only is False
    session.tenant_private_only = True
    assert session.tenant_private_only is True


@pytest.mark.asyncio
async def test_bridge_translate_uses_the_private_intent(monkeypatch):
    from app.telephony import bidirectional_bridge as bridge_mod
    captured: list = []

    class _FakeAi:
        async def translate(self, req):
            captured.append(req)
            raise AssertionError("the private request must not reach the provider")

    monkeypatch.setattr(bridge_mod, "ai", _FakeAi())
    bridge = bridge_mod.BidirectionalTranslationBridge(
        call_id=uuid.uuid4(), caller_language="hi", receiver_language="en",
        tenant_private_only=True)
    with pytest.raises(AssertionError):
        await bridge._bridge_translate("hello", "hi", "en")
    assert captured and captured[0].intent == Intent.PRIVATE_ONLY, (
        "a private call must translate with the private intent")


# --------------------------------------------------------------------------- #
# 7. the translator adapter must not silently downgrade the intent
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_translator_carries_the_callers_intent():
    from gt_ai.translation.translator import IndicTranslator
    captured: list = []

    class _Provider:
        async def translate(self, req):
            captured.append(req)
            return TranslationResult(text="[x]", source_lang=req.source_lang,
                                     target_lang=req.target_lang, model="m", provider="p",
                                     latency_ms=1.0)

    translator = IndicTranslator(_Provider())
    await translator.translate("hello", "en", "hi", intent=Intent.PRIVATE_ONLY)
    assert captured[0].intent == Intent.PRIVATE_ONLY, (
        "the caller's intent must reach the provider request")


# --------------------------------------------------------------------------- #
# 8. the voice TTS tier 1 (gTTS) is a cloud service outside the router
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_private_voice_tts_skips_the_cloud_gtts_tier(monkeypatch):
    import sys
    import types as _types
    from app.routers import translate as translate_router

    constructed: list = []

    class _FakeGtts:
        class gTTS:  # noqa: N801
            def __init__(self, *a, **k) -> None:
                constructed.append(1)
                raise AssertionError("gTTS must not be used for a private request")

    monkeypatch.setitem(sys.modules, "gtts", _FakeGtts)
    _force_settings(monkeypatch, app_env="production")

    class _FakeAi:
        async def synthesize(self, text, lang, voice=None, intent=None):
            from gt_ai.types import RouteDecision
            return (AudioChunk(data=b"", sample_rate=16000, provider="local"),
                    RouteDecision(provider="local", model="local", task=Task.TTS,
                                  reason="test"))

    import app.ai as ai_mod
    monkeypatch.setattr(ai_mod, "ai", _FakeAi())
    body = translate_router.VoiceTtsRequest(text="hello", language="en", private_only=True)
    await translate_router.voice_tts(body)
    assert constructed == [], "the gTTS tier talks to a third party — a private request skips it"
