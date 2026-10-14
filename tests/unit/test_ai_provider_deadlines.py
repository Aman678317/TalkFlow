"""Unit tests — provider deadlines and the bounded failover walk (Phase 4).

Before this, nothing in the AI facade put a clock on a provider call. A provider
that accepts a request and then stalls is indistinguishable, from the caller's
side, from a slow one, and the failover loop only moves on when the current
attempt *raises* — so one wedged provider meant the meeting's fan-out task never
got to the candidate behind it, and the listener's translated caption never
arrived while the original stayed up.

Evidence level: unit. Real `AIFacade`, real `ModelRouter`, fake providers.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

import app.ai as A
from app.config import settings
from app.errors import ProviderError
from gt_ai.model_router import router as R
from gt_ai.types import AudioChunk, ProviderUnavailable, Task


def _facade(task: Task, specs: list[R.ProviderSpec],
            providers: dict[str, object]) -> A.AIFacade:
    """A facade whose candidates are all fakes we control.

    One spec is named after the task's dev fallback so `_ordered_candidates`
    does not append a real registry provider we would have to reach through
    `create()` — the point of these tests is the walk, not the catalog.
    """
    facade = A.AIFacade()
    facade.router = R.ModelRouter({task: specs}, gpu_available=False, health={})
    fallback = {Task.TTS: "dev_tone", Task.MT: "dev_echo"}[task]
    facade._providers = {(task.value, name): providers[name] for name in providers}
    assert fallback in providers, (
        f"include the {fallback} candidate, or the router will append a real one")
    return facade


class _Stall:
    """Answers never — the failure mode a timeout exists to cut."""

    def __init__(self, delay: float = 30.0) -> None:
        self.delay = delay
        self.calls = 0

    async def synthesize(self, text: str, lang: str, voice: str | None = None):
        self.calls += 1
        await asyncio.sleep(self.delay)
        raise AssertionError("a stalled provider must not get to answer")

    async def healthcheck(self) -> bool:
        return True


class _Answer:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.calls = 0

    async def synthesize(self, text: str, lang: str, voice: str | None = None):
        self.calls += 1
        await asyncio.sleep(0)
        return AudioChunk(data=b"\x01\x02" * 8, sample_rate=24000, encoding="pcm_s16le",
                          format="wav", provider=self.provider, model=self.provider,
                          duration_ms=40.0)

    async def healthcheck(self) -> bool:
        return True

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        """An async generator, the way every real voice provider is one."""
        self.calls += 1
        for _ in range(3):
            yield AudioChunk(data=b"\x01\x02" * 8, sample_rate=24000,
                             encoding="pcm_s16le", format="wav",
                             provider=self.provider, model=self.provider,
                             duration_ms=40.0)


class _DyingStream:
    """Opens a stream and fails on the first frame: what a missing model does.

    `gt_ai.tts.kokoro` behaves exactly like this on a host without
    `gt-ai[tts]` — its constructor succeeds, calling `synthesize_stream` returns
    an async generator without running anything, and the first pull raises
    `ProviderUnavailable`. By then the caller has committed to this voice.
    """

    def __init__(self, provider: str = "broken_tts") -> None:
        self.provider = provider
        self.stream_calls = 0
        self.health_checks = 0

    async def healthcheck(self) -> bool:
        self.health_checks += 1
        return False

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        self.stream_calls += 1
        raise ProviderUnavailable(f"{self.provider} requires `pip install gt-ai[tts]`")
        yield  # pragma: no cover


def _spec(name: str) -> R.ProviderSpec:
    return R.ProviderSpec(name=name, model=name, task=Task.TTS,
                          latency_class="realtime")


@pytest.fixture
def tight(monkeypatch):
    """Deadlines short enough that a test would notice a missing one."""
    monkeypatch.setattr(settings, "ai_timeout_s", 0.05, raising=False)
    monkeypatch.setattr(settings, "ai_retry_budget_s", 1.0, raising=False)
    monkeypatch.setattr(settings, "rt_translate_timeout_s", 0.05, raising=False)
    return settings


# --------------------------------------------------------------------------- #
# the per-attempt deadline
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_stalled_provider_is_cut_so_the_next_candidate_gets_tried(tight):
    slow, good = _Stall(), _Answer("dev_tone")
    facade = _facade(Task.TTS, [_spec("broken_voice"), _spec("dev_tone")],
                     {"broken_voice": slow, "dev_tone": good})

    chunk, decision = await asyncio.wait_for(facade.synthesize("hello", "en"), 2.0)

    assert chunk.provider == "dev_tone", "failover never reached the working voice"
    assert decision.provider == "dev_tone"
    health = facade.router.health[("tts", "broken_voice")]
    assert health.error_count == 1 and health.request_count == 1, (
        "a timeout is an outcome the router should learn from, not a silent retry")


@pytest.mark.asyncio
async def test_the_failover_walk_stops_at_its_budget(tight):
    """Attempts are finite in *time*, not only in count.

    Twenty candidates at the per-attempt cap is twenty caps: the budget is what
    keeps a total outage from turning into a twenty-second wait per turn.
    """
    stalls = {f"voice_{i}": _Stall(delay=30.0) for i in range(12)}
    stalls["dev_tone"] = _Stall(delay=30.0)
    names = list(stalls)
    facade = _facade(Task.TTS, [_spec(n) for n in names], stalls)
    tight.ai_timeout_s = 0.02
    tight.ai_retry_budget_s = 0.1

    started = time.perf_counter()
    with pytest.raises(ProviderError):
        await facade.synthesize("hello", "en")
    elapsed = time.perf_counter() - started

    tried = sum(p.calls for p in stalls.values())
    assert tried > 1, "the walk should have moved past the first candidate"
    assert tried < len(names), "every candidate tried means the budget did nothing"
    assert elapsed < 1.0, f"budget not enforced: took {elapsed:.2f}s for {tried} tries"


@pytest.mark.asyncio
async def test_a_provider_that_refuses_fast_is_still_failed_over(tight):
    """The pre-existing behaviour has to survive the new deadline."""
    class _Refuses:
        def __init__(self) -> None:
            self.calls = 0

        async def synthesize(self, text, lang, voice=None):
            self.calls += 1
            raise ProviderUnavailable("no model on disk")

        async def healthcheck(self) -> bool:
            return True

    refuses, good = _Refuses(), _Answer("dev_tone")
    facade = _facade(Task.TTS, [_spec("no_model"), _spec("dev_tone")],
                     {"no_model": refuses, "dev_tone": good})

    chunk, _ = await facade.synthesize("hello", "en")
    assert chunk.provider == "dev_tone"
    assert refuses.calls == 1


# --------------------------------------------------------------------------- #
# streaming selection
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_a_stream_provider_that_cannot_answer_is_not_handed_to_the_room(tight):
    """The choice is made where it can still be checked.

    Handing out a stream that raises on the first frame leaves the caller with no
    candidate left to try: by then the fan-out has committed to this voice.
    """
    broken, good = _DyingStream(), _Answer("dev_tone")
    facade = _facade(Task.TTS, [_spec("broken_voice"), _spec("dev_tone")],
                     {"broken_voice": broken, "dev_tone": good})

    stream, decision = await facade.synthesize_stream("hello there", "en")
    assert decision.provider == "dev_tone", (
        "a provider that failed its healthcheck was still selected")
    assert broken.health_checks == 1, "the candidate was never asked whether it works"
    assert broken.stream_calls == 0, "selection should not open a doomed stream"

    chunks = [c async for c in stream]
    assert len(chunks) == 3
    assert good.calls == 1


@pytest.mark.asyncio
async def test_with_no_voice_available_the_caller_is_told_rather_than_left_hanging(
        tight):
    dead = {"broken_voice": _DyingStream("broken_voice"),
            "dev_tone": _DyingStream("dev_tone")}
    facade = _facade(Task.TTS, [_spec(n) for n in dead], dead)

    with pytest.raises(ProviderError):
        await facade.synthesize_stream("hello there", "en")
    assert all(p.stream_calls == 0 for p in dead.values()), (
        "a dead stream handed back looks like success until somebody pulls a frame")


# --------------------------------------------------------------------------- #
# the meeting's own budget, at the realtime boundary
# --------------------------------------------------------------------------- #
class _Session:
    def __init__(self, sink: list[str]) -> None:
        self.sink = sink

    async def __aenter__(self):
        return SimpleNamespace(id="db-session")

    async def __aexit__(self, *exc):
        self.sink.append("closed")
        return False


@pytest.mark.asyncio
async def test_the_realtime_translator_gives_up_on_its_own_deadline(tight):
    """Agent 2 waits for the meeting, not for the provider.

    The pipeline's failure path is what keeps the original caption on screen, so
    the adapter has to reach it on time rather than sit inside a translation that
    is no longer wanted.
    """
    from app.realtime.agents.translation import RealtimeTranslatorProvider

    closed: list[str] = []

    async def slow_translate(db, text, src, tgt, ctx):
        await asyncio.sleep(30)

    provider = RealtimeTranslatorProvider(
        lambda: _Session(closed), lambda *a: None, translate_fn=slow_translate)

    with pytest.raises(asyncio.TimeoutError):
        await provider.translate("नमस्ते", "hi", "en")
    assert closed == ["closed"], "the DB session outlived a cancelled translation"
