"""Agent-graph ↔ media turn loop (plan §6 integration).

Drives one per-call :class:`~app.telephony.ai_agent_graph.AgentGraph` against
a live caller audio stream — the piece that was still unbuilt when the graph
shipped (PR #70 :: "integration into the bridge turn loop + CallEvent
persistence = follow-up PR")::

    graph.start()  ── disclosure
    loop:
        utterance  = await source.next_utterance()      # caller turn (or gone)
        payload    = policy.to_payload(utterance)        # LLM-shaped inputs
        step       = await graph.advance(payload)        # deterministic guard
        renderer.render(step.say)                        # text → audio frames
    until end / escalate / channel gone / operator stop

Seams (all injectable, all deterministic for tests):

- ``UtteranceSource``  — caller turns. The product default (a media session
  without a wired recognizer) yields ONE empty, zero-confidence utterance and
  then ``None``: the graph's own ``low_stt_confidence`` escalation rule
  fail-closes the call. No recognizer, no fabricated speech.
- ``SpeechRenderer``   — text → audio frames. Without real TTS the agent's
  words are still decided, guarded, and audited (``call_events``), but
  ``frames_rendered=0``/``tts="absent"`` is recorded honestly. The paced frame
  push itself is proven live (lab §P3 spike 7/7); speech *quality* is not
  claimed anywhere.
- ``TurnEventSink``    — persistence. The product implementation writes
  ``call_events`` rows (see ``agent_media_session.MediaCallEventSink``).
- ``TurnPayloadPolicy``— utterance → :class:`TurnPayload`. The default policy
  NEVER derives ``identity_match`` from caller text: identity may only be
  asserted by a dedicated verified backend, so it stays ``None`` and the
  graph re-prompts/escalates (fail-closed).

Persistence failures never kill the media path (plan §7: a voice-transport
failure must not kill the call): sink errors are logged and swallowed.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from app.telephony.ai_agent_graph import (
    AgentGraph,
    AgentGraphDone,
    TurnPayload,
)

log = logging.getLogger("app.telephony.media")

#: Event names persisted through ``TurnEventSink`` (``call_events.event_type``,
#: column is VARCHAR(64) — keep these short and stable).
EVENT_UTTERANCE = "agent_turn_utterance"
EVENT_SPOKEN = "agent_turn_said"
EVENT_OUTCOME = "agent_turn_outcome"

TERMINAL_ESCALATED = "escalated"
TERMINAL_CONCLUDED = "concluded"
TERMINAL_CALLER_GONE = "caller_gone"
TERMINAL_STOPPED = "stopped"
TERMINAL_FAILED = "failed"


# --------------------------------------------------------------------------- #
# value types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Utterance:
    """One finalized caller turn (what a recognizer would produce)."""

    text: str = ""
    confidence: float = 0.0
    frame_count: int = 0


def text_fingerprint(text: str) -> dict[str, Any]:
    """Caller-speech hash for the audit ledger: length + sha256, never raw.

    Caller speech is the privacy-sensitive side (consent, account data); only
    the agent's own spoken lines are recorded verbatim (org-authored content).
    """
    stripped = (text or "").strip()
    return {
        "text_len": len(stripped),
        "text_sha256": hashlib.sha256(stripped.encode("utf-8")).hexdigest(),
    }


@dataclass(frozen=True)
class TurnLoopOutcome:
    terminal: str = TERMINAL_STOPPED
    escalation_reason: str | None = None
    summary: str = ""
    turns: int = 0

    def as_payload(self) -> dict[str, Any]:
        return {
            "terminal": self.terminal,
            "escalation_reason": self.escalation_reason,
            "summary": self.summary,
            "turns": self.turns,
        }


# --------------------------------------------------------------------------- #
# seams
# --------------------------------------------------------------------------- #


class UtteranceSource(Protocol):
    """Next caller turn, or ``None`` once the audio channel is gone."""

    async def next_utterance(self) -> Utterance | None: ...


class SpeechRenderer(Protocol):
    """Text → audio frames pushed toward the PBX (see ``agent_media_session``)."""

    wired: bool  # False ⇒ honest "tts absent" bookkeeping on every segment

    async def render(self, text: str) -> int: ...


class TurnEventSink(Protocol):
    async def record(
        self, event_type: str, payload: dict[str, Any]
    ) -> None: ...


class TurnPayloadPolicy(Protocol):
    def to_payload(self, utterance: Utterance, node: Any) -> TurnPayload: ...


async def safe_record(
    sink: TurnEventSink, event_type: str, payload: dict[str, Any]
) -> None:
    """Best-effort persistence: a sink failure is logged, never raised.

    The audit ledger is important but the live caller path outranks it (§7 —
    a voice-transport failure never kills the call).
    """
    try:
        await sink.record(event_type, payload)
    except Exception:  # noqa: BLE001 — persistence is best-effort by contract
        log.exception("turn event %s could not be recorded", event_type)


@dataclass
class DefaultTurnPolicy:
    """Fail-closed utterance → payload mapping.

    Only ``caller_text`` + ``stt_confidence`` cross the boundary. Anything an
    operator-verifiable backend must assert (``identity_match``), anything a
    knowledge pipeline must propose (``citations``, ``proposed_commitments``)
    stays empty: this loop can never fabricate them from raw microphone text.
    """

    granularity_notes: str = "caller text + confidence only (fail-closed)"

    def to_payload(self, utterance: Utterance, node: Any) -> TurnPayload:
        return TurnPayload(
            caller_text=utterance.text,
            stt_confidence=utterance.confidence,
        )


# --------------------------------------------------------------------------- #
# the loop
# --------------------------------------------------------------------------- #


class AgentTurnLoop:
    """One driver instance per live call; holds the per-call graph."""

    def __init__(
        self,
        graph: AgentGraph,
        *,
        source: UtteranceSource,
        renderer: SpeechRenderer,
        events: TurnEventSink,
        policy: TurnPayloadPolicy | None = None,
    ) -> None:
        self.graph = graph
        self._source = source
        self._renderer = renderer
        self._events = events
        self._policy = policy if policy is not None else DefaultTurnPolicy()
        self._stopped = asyncio.Event()
        self.spoken_segments: list[str] = []
        # Audit hook wiring: the graph's sha256 transition audit flows into the
        # same sink (the §6 integration contract; see ai_agent_graph docstring).
        graph.attach_audit(self._graph_audit)

    # -- control ------------------------------------------------------------ #

    def stop(self) -> None:
        """Operator stop interrupt; the CURRENT turn may finish (§6)."""
        self._stopped.set()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    # -- main loop ---------------------------------------------------------- #

    async def run(self) -> TurnLoopOutcome:
        step = await self.graph.start()
        await self._speak(step)
        turns = 0

        while not self._stopped.is_set():
            utterance = await self._source.next_utterance()
            if self._stopped.is_set():
                break
            if utterance is None:
                return await self._finish(TurnLoopOutcome(
                    terminal=TERMINAL_CALLER_GONE,
                    summary=self._last_summary(step),
                    turns=turns,
                ))
            turns += 1
            await safe_record(
                self._events,
                EVENT_UTTERANCE,
                {
                    "turn": turns,
                    **text_fingerprint(utterance.text),
                    "confidence": utterance.confidence,
                    "frames": utterance.frame_count,
                },
            )

            try:
                step = await self.graph.advance(
                    self._policy.to_payload(utterance, self.graph.node)
                )
            except AgentGraphDone:
                break
            await self._speak(step)

            if step.action == "end":
                return await self._finish(TurnLoopOutcome(
                    terminal=TERMINAL_CONCLUDED,
                    summary=self._last_summary(step),
                    turns=turns,
                ))
            if step.action == "escalate":
                return await self._finish(TurnLoopOutcome(
                    terminal=TERMINAL_ESCALATED,
                    escalation_reason=step.reason,
                    summary=self._last_summary(step),
                    turns=turns,
                ))

        return await self._finish(TurnLoopOutcome(
            terminal=TERMINAL_STOPPED,
            summary=self._last_summary(step),
            turns=turns,
        ))

    async def _finish(self, outcome: TurnLoopOutcome) -> TurnLoopOutcome:
        await safe_record(self._events, EVENT_OUTCOME, outcome.as_payload())
        return outcome

    # -- internals ---------------------------------------------------------- #

    async def _speak(self, step: Any) -> None:
        say = (getattr(step, "say", "") or "").strip()
        if not say:
            return  # await_input steps only re-emit the previous prompt
        rendered = 0
        try:
            rendered = await self._renderer.render(say)
        except Exception:  # noqa: BLE001 — renderer failure must not kill the call
            log.exception("speech renderer failed (segment recorded unrendered)")
            rendered = 0
        self.spoken_segments.append(say)
        await safe_record(
            self._events,
            EVENT_SPOKEN,
            {
                "node": getattr(step.node, "value", str(step.node)),
                "action": step.action,
                "text": say,
                "frames_rendered": rendered,
                "tts": "wired" if self._renderer.wired else "absent",
            },
        )

    async def _graph_audit(self, kind: str, data: dict[str, Any]) -> None:
        await safe_record(self._events, kind, dict(data))

    def _last_summary(self, step: Any) -> str:
        context = getattr(step, "context", None) or {}
        return str(context.get("summary", ""))
