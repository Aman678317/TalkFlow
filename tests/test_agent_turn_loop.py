"""Agent turn loop determinism (plan §6 integration) — no network, no DB.

Covers the fail-closed contract of the media↔graph integration:
- the loop drives the graph through disclosure → verify → purpose → respond →
  confirm → conclude with scripted turns and records every transition;
- without a recognizer the graph's own low-confidence rule escalates (the
  loop invents nothing);
- guarded escalations (opt-out, low STT, ungrounded response) surface as
  outcomes with the graph's reason;
- channel-gone and operator-stop terminate cleanly;
- persistence failures never kill the call (best-effort recording).

Graph turn accounting (one utterance per advance): turn 1 lands on
``disclose``, turn 2 on ``verify_identity``/``ask_purpose``, turn 3 on
``respond``, turn 4 on ``confirm_next_step`` → end.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from app.telephony.ai_agent_graph import GraphConfig, TurnPayload, build_graph
from app.telephony.media.agent_turn_loop import (
    EVENT_OUTCOME,
    EVENT_SPOKEN,
    EVENT_UTTERANCE,
    AgentTurnLoop,
    DefaultTurnPolicy,
    TurnLoopOutcome,
    Utterance,
    text_fingerprint,
)


class RecordingSink:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.records.append((event_type, dict(payload)))

    def events(self, kind: str) -> list[dict[str, Any]]:
        return [payload for event, payload in self.records if event == kind]

    def kinds(self) -> list[str]:
        return [event for event, _ in self.records]


class BrokenSink(RecordingSink):
    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.records.append((event_type, dict(payload)))
        raise RuntimeError("db unavailable")


class ScriptedSource:
    """Utterances list then ``None`` (channel gone), like the real source."""

    def __init__(self, utterances: list[Utterance]) -> None:
        self._utterances = list(utterances)

    async def next_utterance(self) -> Utterance | None:
        if self._utterances:
            return self._utterances.pop(0)
        return None


class OfflineSource(ScriptedSource):
    """Mimics the production default without a recognizer: one empty turn."""

    @classmethod
    def unavailable(cls) -> "OfflineSource":
        return cls([Utterance(text="", confidence=0.0, frame_count=0)])


class ScriptedRenderer:
    def __init__(self, *, wired: bool = False, frames_per_text: int = 3) -> None:
        self.wired = wired
        self._frames = frames_per_text
        self.rendered: list[str] = []

    async def render(self, text: str) -> int:
        self.rendered.append(text)
        return self._frames if self.wired else 0


class ScriptedPolicy:
    """Per-turn payload overrides merged over DefaultTurnPolicy defaults.

    ``payloads[i]`` is applied to turn i+1 — the same seam a real LLM driver
    or identity backend occupies later. Turns beyond the list fall back to the
    fail-closed default policy.
    """

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = list(payloads)

    def to_payload(self, utterance: Utterance, node: Any) -> TurnPayload:
        base = DefaultTurnPolicy().to_payload(utterance, node)
        if self._payloads:
            override = dict(self._payloads.pop(0))
            merged = {
                "caller_text": utterance.text,
                "stt_confidence": utterance.confidence,
            }
            merged.update(override)
            args = list(merged.items())
            return TurnPayload(**dict(args))  # type: ignore[arg-type]
        return base


def _graph_config(**overrides: Any) -> GraphConfig:
    defaults = dict(verify_identity=True, permitted_documents=("doc-1",))
    defaults.update(overrides)
    return GraphConfig(**defaults)


def graph_node(loop: AgentTurnLoop) -> str | None:
    node = loop.graph.node
    return node.value if node is not None else None


# --------------------------------------------------------------------------- #
# outcomes
# --------------------------------------------------------------------------- #


async def test_disclosure_then_fail_closed_on_empty_turn() -> None:
    sink = RecordingSink()
    graph = build_graph(_graph_config())
    loop = AgentTurnLoop(
        graph, source=OfflineSource.unavailable(),
        renderer=ScriptedRenderer(), events=sink)
    outcome = await loop.run()
    assert outcome.terminal == "escalated"
    assert outcome.escalation_reason == "low_stt_confidence"
    spoke = [payload["text"] for payload in sink.events(EVENT_SPOKEN)]
    assert graph.config.disclosure_text in spoke
    assert any("human who can" in text for text in spoke)  # escalation line
    outcome_events = sink.events(EVENT_OUTCOME)
    assert outcome_events[-1]["terminal"] == "escalated"
    assert outcome_events[-1]["escalation_reason"] == "low_stt_confidence"


async def test_full_conversation_with_verified_identity_and_citations() -> None:
    sink = RecordingSink()
    graph = build_graph(_graph_config())
    source_utterances = [
        Utterance(text="let me think about the details", confidence=0.9),
        Utterance(text="doc details again", confidence=0.9),
        Utterance(text="I want to know about my plan", confidence=0.9),
        Utterance(text="okay tell me", confidence=0.9),
        Utterance(text="add the assert detail", confidence=0.9),
    ]
    # policy consumption begins with turn 1: payloads[0] lands on the disclose
    # advance (ignored there), so identity/purpose/response/confirm land on
    # turns 2/3/4/5.
    policy = ScriptedPolicy([
        {},                                              # turn 1: disclose
        {"identity_match": True},                        # turn 2: verified
        {"purpose": "plan question"},                    # turn 3: purpose
        {"say": "Your plan is monthly. (doc:doc-1)",
         "citations": ("doc-1",)},                       # turn 4: grounded
        {},                                              # turn 5: confirm end
    ])
    loop = AgentTurnLoop(graph,
                         source=ScriptedSource(source_utterances),
                         renderer=ScriptedRenderer(), events=sink,
                         policy=policy)
    await loop.run()
    outcome_events = sink.events(EVENT_OUTCOME)
    assert outcome_events[-1]["turns"] == 5
    assert outcome_events[-1]["terminal"] == "concluded"
    spoke = [payload["text"] for payload in sink.events(EVENT_SPOKEN)]
    assert graph.config.disclosure_text in spoke
    assert any("(doc:doc-1)" in text for text in spoke)
    node_events = sink.events("ai_agent.node")
    transitions = [(event["from"], event["to"]) for event in node_events
                   if "to" in event]
    assert ("verify_identity", "ask_purpose") in transitions
    assert ("respond", "confirm_next_step") in transitions
    # §6: every graph transition carries its sha256 audit pair
    assert all("inputs_sha256" in event and "output_sha256" in event
               for event in node_events if "to" in event)
    # utterance events carry the caller fingerprint: hash + length, not text
    utter_events = sink.events(EVENT_UTTERANCE)
    assert len(utter_events) == 5
    expected_hashes = [
        hashlib.sha256(u.text.strip().encode()).hexdigest()
        for u in source_utterances
    ]
    assert [event["text_sha256"] for event in utter_events] == expected_hashes
    for event, utterance in zip(utter_events, source_utterances):
        assert event["text_len"] == len(utterance.text)
        assert event["confidence"] == 0.9
        assert set(event) == {"turn", "text_len", "text_sha256",
                              "confidence", "frames"}
    # outcome recorded exactly once
    assert sink.kinds().count(EVENT_OUTCOME) == 1


async def test_opt_out_keyword_escalates_mid_flow() -> None:
    sink = RecordingSink()
    loop = AgentTurnLoop(
        build_graph(_graph_config(verify_identity=False)),
        source=ScriptedSource([Utterance(text="remove me", confidence=0.9)]),
        renderer=ScriptedRenderer(), events=sink)
    outcome = await loop.run()
    assert outcome.terminal == "escalated"
    assert outcome.escalation_reason == "opt_out"


async def test_human_request_escalates() -> None:
    sink = RecordingSink()
    loop = AgentTurnLoop(
        build_graph(_graph_config(verify_identity=False)),
        source=ScriptedSource([
            Utterance(text="let me talk to a human", confidence=0.9)
        ]),
        renderer=ScriptedRenderer(), events=sink)
    outcome = await loop.run()
    assert outcome.terminal == "escalated"
    assert outcome.escalation_reason == "human_requested"


async def test_ungrounded_response_escalates_fail_closed() -> None:
    sink = RecordingSink()
    policy = ScriptedPolicy([
        {},                                          # turn 1: disclose consumes
        {"purpose": "generic"},                      # turn 2: purpose prompt
        {"say": "Trust me, everything is fine.",
         "citations": ()},                           # turn 3: ungrounded
    ])
    loop = AgentTurnLoop(
        build_graph(_graph_config(verify_identity=False)),
        source=ScriptedSource([
            Utterance(text="hello", confidence=0.9),
            Utterance(text="what's the plan", confidence=0.9),
            Utterance(text="is that so", confidence=0.9),
        ]),
        renderer=ScriptedRenderer(), events=sink, policy=policy)
    outcome = await loop.run()
    assert outcome.terminal == "escalated"
    assert outcome.escalation_reason == "no_grounded_response"


async def test_caller_gone_after_disclosure_ends_cleanly() -> None:
    sink = RecordingSink()
    loop = AgentTurnLoop(
        build_graph(_graph_config()),
        source=ScriptedSource([]),   # channel never produces any turn
        renderer=ScriptedRenderer(), events=sink)
    outcome = await loop.run()
    assert outcome.terminal == "caller_gone"
    assert outcome.turns == 0
    assert graph_node(loop) == "disclose"  # no advance fabricated


async def test_operator_stop_interrupts_within_the_waiting_turn() -> None:
    sink = RecordingSink()
    loop = AgentTurnLoop(
        build_graph(_graph_config()),
        source=BlockingSource(), renderer=ScriptedRenderer(), events=sink)

    async def _stop_soon() -> None:
        await asyncio.sleep(0)
        loop.stop()

    asyncio.create_task(_stop_soon())
    outcome = await loop.run()
    assert outcome.terminal == "stopped"
    assert graph_node(loop) == "disclose"


class BlockingSource:
    """Holds the turn open long enough for a stop interrupt to land."""

    async def next_utterance(self) -> Utterance | None:
        try:
            await asyncio.wait_for(asyncio.sleep(0.5), timeout=0.5)
        except (TimeoutError, asyncio.TimeoutError):
            return None
        return None


async def test_renderer_failure_records_segment_and_continues() -> None:
    class ExplodingRenderer(ScriptedRenderer):
        async def render(self, text: str) -> int:
            raise RuntimeError("osc garbage")

    sink = RecordingSink()
    policy = ScriptedPolicy([
        {},                                         # turn 1: disclose
        {"purpose": "generic"},                     # turn 2: purpose prompt
        {"say": "Monthly plan. (doc:doc-1)",
         "citations": ("doc-1",)},                  # turn 3: grounded speak
        {"say": "Monthly plan. (doc:doc-1)",
         "citations": ("doc-1",)},                  # turn 4: confirm repeats say
    ])
    loop = AgentTurnLoop(
        build_graph(_graph_config(verify_identity=False)),
        source=ScriptedSource([
            Utterance(text="h1", confidence=0.9),
            Utterance(text="h2", confidence=0.9),
            Utterance(text="h3", confidence=0.9),
            Utterance(text="h4", confidence=0.9),
        ]),
        renderer=ExplodingRenderer(wired=True), events=sink, policy=policy)
    outcome = await loop.run()
    assert outcome.terminal == "concluded"
    spoken = sink.events(EVENT_SPOKEN)
    assert len(spoken) >= 2
    assert all(payload["frames_rendered"] == 0 for payload in spoken)
    assert all(payload["tts"] == "wired" for payload in spoken)


async def test_tts_absent_flag_is_honest_bookkeeping() -> None:
    sink = RecordingSink()
    loop = AgentTurnLoop(
        build_graph(_graph_config()),
        source=OfflineSource.unavailable(),
        renderer=ScriptedRenderer(wired=False), events=sink)
    await loop.run()
    spoken = sink.events(EVENT_SPOKEN)
    assert spoken and all(payload["tts"] == "absent" for payload in spoken)
    assert all(payload["frames_rendered"] == 0 for payload in spoken)


async def test_sink_failure_never_kills_the_media_call() -> None:
    sink = BrokenSink()
    policy = ScriptedPolicy([
        {},                                         # turn 1: disclose
        {"purpose": "generic"},                     # turn 2: purpose
        {"say": "Monthly plan. (doc:doc-1)",
         "citations": ("doc-1",)},                  # turn 3: grounded
        {},                                         # turn 4: confirm → end
    ])
    loop = AgentTurnLoop(
        build_graph(_graph_config(verify_identity=False)),
        source=ScriptedSource([
            Utterance(text="hello", confidence=0.9),
            Utterance(text="next", confidence=0.9),
            Utterance(text="tell me", confidence=0.9),
            Utterance(text="done", confidence=0.9),
        ]),
        renderer=ScriptedRenderer(), events=sink, policy=policy)
    outcome = await loop.run()  # persistence fails every record; loop survives
    assert outcome.terminal == "concluded"
    assert len(sink.records) >= 5  # records still reached the failing sink


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #


def test_text_fingerprint_never_reveals_raw_text() -> None:
    secret = "my card is 4111 1111 1111 1111"
    fingerprint = text_fingerprint(secret)
    serialized = repr(fingerprint)
    assert "4111" not in serialized and secret not in serialized
    assert fingerprint["text_len"] == len(secret)
    assert fingerprint["text_sha256"] == hashlib.sha256(
        secret.strip().encode()).hexdigest()


def test_default_policy_never_derives_identity_from_text() -> None:
    policy = DefaultTurnPolicy()
    payload = policy.to_payload(Utterance("this is my account and balance", 0.99),
                                node=None)
    assert payload.caller_text == "this is my account and balance"
    assert payload.stt_confidence == 0.99
    assert payload.identity_match is None      # text may NEVER assert identity
    assert payload.proposed_commitments == ()
    assert payload.citations == ()
    assert payload.purpose is None


def test_turn_loop_outcome_payload_is_flat_dict() -> None:
    outcome = TurnLoopOutcome(terminal="escalated", escalation_reason="opt_out",
                              summary="disclosure;responded:12ch", turns=2)
    assert outcome.as_payload() == {
        "terminal": "escalated", "escalation_reason": "opt_out",
        "summary": "disclosure;responded:12ch", "turns": 2}


async def test_outcome_event_recorded_once_per_run() -> None:
    for source_setup, expected in (
        (lambda: OfflineSource.unavailable(), "escalated"),
        (lambda: ScriptedSource([]), "caller_gone"),
    ):
        sink = RecordingSink()
        loop = AgentTurnLoop(
            build_graph(_graph_config()), source=source_setup(),
            renderer=ScriptedRenderer(), events=sink)
        outcome = await loop.run()
        assert outcome.terminal == expected
        events = sink.events(EVENT_OUTCOME)
        assert len(events) == 1 and events[0]["terminal"] == expected
