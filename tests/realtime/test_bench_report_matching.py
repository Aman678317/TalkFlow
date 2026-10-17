"""The benchmark harness's own report matcher, tested.

The Phase 4 latency number is quoted at a gate, so the thing that assembles it
has to be checked like production code. It was not, and the first baseline this
harness printed was wrong: it re-read one turn's report once per utterance, so
twelve turns printed twelve identical rows, a p50 equal to its p95, and a
server-side rollup that looked broken by comparison.
"""
from bench_latency import next_report


def _report(seq: int, utterance: str, target: str = "en") -> dict:
    return {"type": "latency.report",
            "data": {"seq": seq, "utterance_id": utterance, "target_lang": target,
                     "speech_end_to_first_audio_ms": 1000 + seq}}


def test_a_turn_is_counted_once_even_when_the_sink_still_holds_it():
    """The sink accumulates every event of the meeting; a matcher that scans it
    for "any report" hands the same report to every later utterance."""
    sink = [_report(1, "u-one")]
    taken: set[tuple[int, str]] = set()

    first = next_report(sink, hear="en", taken=taken)
    second = next_report(sink, hear="en", taken=taken)

    assert first is not None and first["seq"] == 1
    assert second is None


def test_each_turn_of_the_run_is_reported_exactly_once():
    sink = [_report(1, "u-one"), {"type": "transcript.final", "data": {}},
            _report(2, "u-two"), _report(2, "u-two"), _report(3, "u-three")]
    taken: set[tuple[int, str]] = set()

    seqs = []
    while True:
        tr = next_report(sink, hear="en", taken=taken)
        if tr is None:
            break
        seqs.append(tr["seq"])

    assert seqs == [1, 2, 3]


def test_a_report_for_another_language_is_not_this_listeners_wait():
    """A room with two target languages has two waits per turn. The harness
    measures the one its listener is hearing and leaves the other alone."""
    sink = [_report(1, "u-one", target="hi"), _report(1, "u-one", target="en")]
    taken: set[tuple[int, str]] = set()

    tr = next_report(sink, hear="en", taken=taken)

    assert tr["target_lang"] == "en"
