"""The Phase 3 voice benchmark measures voices; it never imagines them.

``gt_ai.evaluation.tts`` exists because the capability registry says its quality
numbers are "filled by the evaluation harness, not marketing" while speech
*output* had never been measured at all. The dangerous failure mode for a
benchmark is not a slow voice — it is a report that looks like evidence:
digital silence scored as speech, a missing model timed as a fast one, or a
voice quietly swapped for another language's.

These tests run the harness against a provider that produces exactly what the
test describes, so the arithmetic and the honesty rules are covered even on a
machine with no TTS weights installed (this one).
"""
from __future__ import annotations

import asyncio
import io
import wave

import pytest
from gt_ai.evaluation.tts import (
    GATES, bench_case, bench_voice, candidate_voices, load_texts, run_bench,
)
from gt_ai.tts.piper import PiperProvider
from gt_ai.types import AudioChunk, ProviderUnavailable

HI = "नमस्ते, आप कैसे हैं?"


def _wav(samples: int, rate: int = 24000, amplitude: int = 4000) -> bytes:
    """A WAV of exactly `samples` frames — real audio at a known length."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frame = amplitude.to_bytes(2, "little", signed=True)
        wf.writeframes(frame * samples)
    return buf.getvalue()


class FakeTts:
    """Shaped exactly like the real adapters: an async generator that raises
    ``ProviderUnavailable`` on the first iteration when its weights are absent."""

    name = "fake"

    def __init__(self, *, chunks: int = 2, frames_per_chunk: int = 4800,
                 first_delay: float = 0.0, rest_delay: float = 0.0,
                 amplitude: int = 4000, wav: bool = True,
                 fail: Exception | None = None, silence_stream: bool = False,
                 voices: dict[str, list[str]] | None = None) -> None:
        self.chunks = chunks
        self.frames_per_chunk = frames_per_chunk
        self.first_delay = first_delay
        self.rest_delay = rest_delay
        self.amplitude = amplitude
        self.wav = wav
        self.fail = fail
        self.silence_stream = silence_stream
        self._voices = voices or {}
        self.calls: list[tuple[str, str | None]] = []

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        self.calls.append((lang, voice))
        if self.fail is not None:
            raise self.fail
        if self.silence_stream:
            return
        for i in range(self.chunks):
            await asyncio.sleep(self.first_delay if i == 0 else self.rest_delay)
            body = _wav(self.frames_per_chunk, amplitude=self.amplitude)
            yield AudioChunk(
                data=body if self.wav else body[44:],
                sample_rate=24000,
                encoding="pcm_s16le", format="wav" if self.wav else "pcm_s16le",
                provider=self.name, model=f"fake/{voice or 'default'}",
                duration_ms=(self.frames_per_chunk / 24000 * 1000) if self.wav else 0.0)


# --------------------------------------------------------------------------- #
# the corpus is the curated one
# --------------------------------------------------------------------------- #
def test_hindi_sentences_come_from_the_golden_dataset() -> None:
    cases = load_texts("hi")
    assert cases, "the benchmark has no Hindi sentences to speak"
    assert all(any("ऀ" <= ch <= "ॿ" for ch in t) for _, t in cases)
    assert len(cases) <= 3


def test_a_language_absent_from_the_dataset_reports_that_instead_of_passing() -> None:
    assert load_texts("zz") == []


# --------------------------------------------------------------------------- #
# measurement
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_first_audio_and_real_time_factor_are_measured_not_assumed() -> None:
    fake = FakeTts(chunks=3, frames_per_chunk=7200,   # 300 ms of audio each
                   first_delay=0.02, rest_delay=0.001)
    report = await bench_voice(fake, "hi", "hf_alpha", [("c1", HI), ("c2", HI)])
    assert report.available and report.n_cases == 2
    assert report.first_audio_p50_ms >= 15            # the 20 ms sleep happened
    assert report.audio_ms_total == pytest.approx(1800.0, abs=1)
    # ~22 ms of synthesis bought 900 ms of audio per sentence.
    assert 0 < report.realtime_factor < 0.2
    assert report.passed_gates is True


@pytest.mark.asyncio
async def test_a_voice_that_produces_digital_silence_is_failed_not_scored() -> None:
    """The failure this harness exists to catch: output that looks like a pass."""
    fake = FakeTts(amplitude=0)
    report = await bench_voice(fake, "hi", "hf_alpha", [("c1", HI)])
    assert report.available
    assert report.silent_cases == 1
    assert report.failure_rate == 1.0
    assert report.passed_gates is False
    assert report.cases[0].error == "digital silence"


@pytest.mark.asyncio
async def test_a_missing_model_is_reported_as_unmeasured_with_no_numbers() -> None:
    """Not a slow score, not a zero, not a skip: an explicit non-result naming
    the file that is absent."""
    fake = FakeTts(fail=ProviderUnavailable("piper voice missing: hi_IN-x.onnx"))
    report = await bench_voice(fake, "hi", "hi_IN-x", [("c1", HI)])
    assert report.available is False
    assert report.n_cases == 0 and report.cases == []
    assert report.first_audio_p95_ms == 0.0 and report.realtime_factor == 0.0
    assert "hi_IN-x.onnx" in report.unavailable_reason
    assert report.passed_gates is False


@pytest.mark.asyncio
async def test_a_stream_that_yields_nothing_is_a_failure_not_a_zero() -> None:
    fake = FakeTts(silence_stream=True)
    case = await bench_case(fake, "hi", "hf_alpha", "c1", HI)
    assert case.ok is False and case.error == "provider streamed no audio"


@pytest.mark.asyncio
async def test_a_voice_too_slow_for_live_meeting_fails_the_gate_but_stays_measured() -> None:
    """Slowness is a result; unavailability is not. Only the first case can turn
    a voice into "unmeasured"."""
    fake = FakeTts(chunks=1, frames_per_chunk=2400, first_delay=0.0)
    fake.chunks = 1
    report = await bench_voice(
        fake, "hi", "hf_alpha", [("c1", HI)],
        gates={**GATES, "max_realtime_factor": 0.0000001})
    assert report.available and report.passed_gates is False
    assert report.gate_details["realtime_ok"] is False


@pytest.mark.asyncio
async def test_pcm_without_a_declared_duration_is_still_measured_by_length() -> None:
    fake = FakeTts(chunks=2, frames_per_chunk=2400, wav=False)
    report = await bench_voice(fake, "hi", None, [("c1", HI)])
    assert report.audio_ms_total == pytest.approx(200.0, abs=1)


# --------------------------------------------------------------------------- #
# asking a provider what it has
# --------------------------------------------------------------------------- #
class Named(FakeTts):
    """A provider that can answer `voices_for`, as the benchmark asks it to."""

    def voices_for(self, lang: str) -> list[str]:
        return self._voices.get(lang, [])


def test_candidate_voices_asks_the_provider_and_tolerates_one_that_cannot_answer() -> None:
    named = Named(voices={"hi": ["hf_alpha", "hm_omega"]})
    assert candidate_voices(named, "hi") == ["hf_alpha", "hm_omega"]
    assert candidate_voices(named, "ta") == []
    assert candidate_voices(FakeTts(), "hi") == []      # provider cannot answer


def test_piper_lists_the_voices_installed_for_a_language(tmp_path) -> None:
    for stem in ("hi_IN-pratham-medium", "hi_IN-priyamvada-medium", "en_US-lessac-medium"):
        (tmp_path / f"{stem}.onnx").write_bytes(b"x")
    p = PiperProvider(model_dir=str(tmp_path))
    assert p.voices_for("hi") == ["hi_IN-pratham-medium",        # default first
                                  "hi_IN-priyamvada-medium"]
    assert p.voices_for("en") == ["en_US-lessac-medium"]


def test_piper_offers_no_voice_for_a_language_the_dataset_has_none_for(tmp_path) -> None:
    """Tamil: the upstream voice manifest ships none, and the benchmark must say
    so rather than invent a candidate."""
    unconfigured = PiperProvider(model_dir=str(tmp_path), voice_map={})
    assert unconfigured.voices_for("ta") == []


@pytest.mark.asyncio
async def test_the_bench_walks_every_voice_the_provider_offers() -> None:
    """A provider that can name its voices gets each of them timed — and its
    default is already in that list, so it is not measured twice."""
    reports = await run_bench([Named(voices={"hi": ["hf_alpha", "hm_omega"]})], ["hi"])
    assert [r.voice for r in reports] == ["hf_alpha", "hm_omega"]
    assert all(r.available for r in reports)


async def test_a_provider_that_offers_no_voice_is_still_measured_once() -> None:
    """That single measurement is exactly what the room would hear, so the report
    has to say what happens rather than say nothing."""
    reports = await run_bench([FakeTts()], ["hi"])
    assert [r.voice for r in reports] == ["(provider default)"]
    assert reports[0].available is True


@pytest.mark.asyncio
async def test_a_language_with_no_corpus_is_reported_not_silently_dropped() -> None:
    reports = await run_bench([FakeTts()], ["zz"])
    assert len(reports) == 1 and reports[0].available is False
    assert "zz sentences" in reports[0].unavailable_reason
