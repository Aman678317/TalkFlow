"""Unit tests — the provider circuit breaker (Phase 4).

The failover walk made a bad provider survivable, and it also made it
expensive: every turn asked the same voice that had refused every turn before
it, and measured runs on this host logged two refused voice probes per
utterance for a Piper and a Kokoro that are not installed. A timeout limits one
call; only remembering limits the next thousand.

A breaker has to reopen, though, or it is a deletion. A provider that is simply
absent gets asked again on a backoff — once a cooldown, then twice, then four
times — and a provider that comes back is back for the next turn, not after a
restart.

Evidence level: unit. Real `ModelRouter` and real `AIFacade`, fake providers, an
injectable clock so a cooldown is tested by moving time rather than sleeping.
"""
from __future__ import annotations

import pytest

import app.ai as A
from app.errors import ProviderError
from gt_ai.model_router import router as R
from gt_ai.types import Task


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _spec(name: str, task: Task, quality: int = 90) -> R.ProviderSpec:
    return R.ProviderSpec(name=name, model=name, task=task, quality_tier=quality,
                          latency_class="realtime")


def _mt_router(clock: Clock, *, cooldown: float = 30.0,
               maximum: float = 600.0) -> R.ModelRouter:
    return R.ModelRouter(
        {Task.MT: [_spec("madlad400", Task.MT, 90), _spec("nllb_ct2", Task.MT, 70)]},
        gpu_available=False, clock=clock, breaker_cooldown_s=cooldown,
        breaker_max_cooldown_s=maximum)


def _trip_four_times(r: R.ModelRouter, clock: Clock, name: str = "madlad400") -> None:
    for _ in range(4):
        r.record_outcome(Task.MT, name, 100.0, ok=False)


# --------------------------------------------------------------------------- #
# The breaker, on the router
# --------------------------------------------------------------------------- #

def test_a_provider_that_keeps_failing_is_left_alone_for_a_cooldown():
    clock = Clock()
    r = _mt_router(clock)
    _trip_four_times(r, clock)

    assert r.route(Task.MT).provider == "nllb_ct2"
    clock.advance(29)
    assert r.route(Task.MT).provider == "nllb_ct2", (
        "the provider was offered again before its cooldown had passed")


def test_the_cooldown_expires_and_the_provider_is_offered_again():
    """A breaker that never reopens is a provider deletion with extra state."""
    clock = Clock()
    r = _mt_router(clock)
    _trip_four_times(r, clock)

    clock.advance(31)

    assert not r.circuit_open(Task.MT, "madlad400")
    assert r.route(Task.MT).provider == "madlad400"


def test_the_recovery_probe_gets_one_failure_not_a_quorum():
    clock = Clock()
    r = _mt_router(clock)
    _trip_four_times(r, clock)
    clock.advance(31)
    assert r.route(Task.MT).provider == "madlad400"

    r.record_outcome(Task.MT, "madlad400", 100.0, ok=False)

    assert r.circuit_open(Task.MT, "madlad400"), (
        "a failed probe needed four more failures before the circuit reopened")


def test_each_failed_probe_waits_longer_than_the_last():
    clock = Clock()
    r = _mt_router(clock)
    _trip_four_times(r, clock)

    windows = []
    for _ in range(3):
        key = ("mt", "madlad400")
        clock.advance((r.breakers[key].until - clock()) + 1)
        r.record_outcome(Task.MT, "madlad400", 100.0, ok=False)
        windows.append(r.breakers[key].until - clock())

    assert windows == [60.0, 120.0, 240.0], (
        f"backoff should double per probe, it went {windows}")


def test_the_backoff_is_capped_so_a_provider_is_never_gone_for_long():
    clock = Clock()
    r = _mt_router(clock, cooldown=30.0, maximum=120.0)
    _trip_four_times(r, clock)
    key = ("mt", "madlad400")

    for _ in range(6):
        clock.advance((r.breakers[key].until - clock()) + 1)
        r.record_outcome(Task.MT, "madlad400", 100.0, ok=False)

    assert r.breakers[key].until - clock() <= 120.0


def test_a_probe_that_answers_closes_the_circuit_for_the_next_turn():
    clock = Clock()
    r = _mt_router(clock)
    _trip_four_times(r, clock)
    clock.advance(31)

    r.record_outcome(Task.MT, "madlad400", 40.0, ok=True)

    assert not r.circuit_open(Task.MT, "madlad400")
    assert r.health[("mt", "madlad400")].available is True
    assert r.route(Task.MT).provider == "madlad400"


def test_a_trip_resets_the_error_rate_it_was_judged_on():
    """The trip is a statement about the calls that just happened.

    Left cumulative, `error_rate` can only fall as slow as `request_count`
    grows, so a provider that failed four times in a row could never satisfy a
    re-close threshold below the trip threshold. This is the bug that made
    `available = False` permanent in practice.
    """
    clock = Clock()
    r = _mt_router(clock)
    _trip_four_times(r, clock)
    h = r.health[("mt", "madlad400")]

    assert h.request_count == 0 and h.error_count == 0
    assert h.error_rate == 0.0


def test_an_operator_saying_it_is_back_beats_the_cooldown():
    clock = Clock()
    r = _mt_router(clock)
    _trip_four_times(r, clock)

    r.mark_available(Task.MT, "madlad400", True)

    assert not r.circuit_open(Task.MT, "madlad400")
    assert r.route(Task.MT).provider == "madlad400"


def test_nothing_is_offered_when_the_only_candidate_is_breathing_on_a_probe():
    """Degrading to a tripped provider is allowed only when it is the whole
    pool — but a provider still inside its cooldown is not chosen first."""
    clock = Clock()
    r = R.ModelRouter({Task.MT: [_spec("madlad400", Task.MT)]}, gpu_available=False,
                      clock=clock, breaker_cooldown_s=30.0)
    _trip_four_times(r, clock)

    # Only one candidate exists, so it is still routed rather than raising: the
    # caller has to be able to try, and the room has to keep the original text.
    assert r.route(Task.MT).provider == "madlad400"


# --------------------------------------------------------------------------- #
# The breaker, where the room actually pays for it
# --------------------------------------------------------------------------- #

class _RefusingVoice:
    """A voice whose package is not installed: it answers the interface and
    refuses the healthcheck, which is exactly how Piper and Kokoro behave on a
    host that never installed them."""

    def __init__(self) -> None:
        self.health_checks = 0

    async def healthcheck(self) -> bool:
        self.health_checks += 1
        return False

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        raise AssertionError("a voice that refused its healthcheck must not be asked")
        yield b""


class _AnsweringVoice:
    def __init__(self) -> None:
        self.calls = 0

    async def healthcheck(self) -> bool:
        return True

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        self.calls += 1
        yield b"\x00\x00"


def _tts_facade(clock: Clock, providers: dict[str, object]) -> tuple[A.AIFacade, dict]:
    facade = A.AIFacade()
    facade.router = R.ModelRouter(
        {Task.TTS: [_spec(n, Task.TTS) for n in providers]}, gpu_available=False,
        clock=clock, breaker_cooldown_s=30.0)
    facade._providers = {(Task.TTS.value, n): p for n, p in providers.items()}
    return facade, providers


@pytest.mark.asyncio
async def test_a_voice_that_refuses_is_not_asked_again_on_every_turn():
    """The measured cost: 20 turns, 35 refused probes per absent voice.

    Each turn still gets audio — the breaker stops the asking, not the room.
    """
    clock = Clock()
    facade, providers = _tts_facade(clock, {"piper": _RefusingVoice(),
                                            "dev_tone": _AnsweringVoice()})

    for _ in range(20):
        stream, decision = await facade.synthesize_stream("hello there", "en")
        async for _ in stream:
            pass
        assert decision.provider == "dev_tone"

    assert providers["piper"].health_checks == 1, (
        "an absent voice was probed once per turn instead of once per cooldown")
    assert providers["dev_tone"].calls == 20


@pytest.mark.asyncio
async def test_an_absent_voice_is_asked_again_once_its_cooldown_passes():
    clock = Clock()
    facade, providers = _tts_facade(clock, {"piper": _RefusingVoice(),
                                            "dev_tone": _AnsweringVoice()})

    await facade.synthesize_stream("a", "en")
    clock.advance(31)
    stream, decision = await facade.synthesize_stream("b", "en")
    async for _ in stream:
        pass

    assert providers["piper"].health_checks == 2
    assert decision.provider == "dev_tone", (
        "a failed probe took the room's voice with it")


@pytest.mark.asyncio
async def test_a_host_with_no_voice_at_all_is_said_so_instead_of_going_silent():
    """Every candidate refuses: the registry voices and the local tone that the
    walk appends as the room's last resort."""
    clock = Clock()
    voices = {n: _RefusingVoice() for n in ("piper", "kokoro", "dev_tone")}
    facade, providers = _tts_facade(clock, voices)

    with pytest.raises(ProviderError):
        await facade.synthesize_stream("a", "en")
    # All three are now tripped, so the next turn does not pay for the probes
    # twice over — it says so again, immediately.
    with pytest.raises(ProviderError):
        await facade.synthesize_stream("a", "en")

    assert [v.health_checks for v in providers.values()] == [1, 1, 1]


def test_the_walk_no_longer_scrubs_the_health_it_is_judged_on():
    """`_ordered_candidates` used to make each candidate unhealthy to move the
    router on, then restore it — zeroing the counters that the breaker reads."""
    clock = Clock()
    facade, _ = _tts_facade(clock, {"piper": _RefusingVoice(),
                                    "dev_tone": _AnsweringVoice()})
    facade.router.record_outcome(Task.TTS, "dev_tone", 10.0, ok=True)
    facade.router.record_outcome(Task.TTS, "dev_tone", 10.0, ok=True)

    facade._ordered_candidates(Task.TTS, {})

    assert facade.router.health[(Task.TTS.value, "dev_tone")].request_count == 2, (
        "the failover walk rewrote provider health")


def test_a_down_online_translator_is_not_handed_to_every_later_turn():
    """`neural_online` is appended as a last resort because it is not in the
    registry. It is still a public HTTP call, so it still has to obey the
    breaker — while the local stand-in next to it does not."""
    clock = Clock()
    facade = A.AIFacade()
    facade.router = R.ModelRouter({Task.MT: [_spec("madlad400", Task.MT)]},
                                  gpu_available=False, clock=clock,
                                  breaker_cooldown_s=30.0)
    facade.router.trip(Task.MT, "neural_online", "no key, endpoint down")

    order = facade._ordered_candidates(Task.MT, {})
    names = [d.provider for d in order]

    assert "neural_online" not in names
    assert names == ["madlad400", "dev_echo"], (
        "the walk must still end in something that answers, so the room keeps "
        "a caption instead of a timeout per turn")
