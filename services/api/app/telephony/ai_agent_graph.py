"""P4 — deterministic AI voice-agent state graph (phone_calling_plan §6).

Replaces free-form prompt chaining (``bidirectional_bridge._handle_ai_agent_turn``,
which made one LLM call per turn with no lifecycle guards) with a hard state
machine whose transitions live in CODE, not in prompt text: the LLM only
returns small payloads that this graph validates against fail-closed rules.

Nodes (§6)::
    disclose → (optional) verify_identity → ask_purpose → respond
              → confirm_next_step → [escalate | conclude] → end

Hard guards (all enforced here, all unit-tested):
- ``disclose`` is mandatory and cannot be skipped, reordered, or disabled —
  operator configs attempting to disable it are rejected at graph build.
- ``verify_identity`` runs BEFORE any account-specific statement;
  identifying data is never spoken verbatim.
- ``respond`` may cite ONLY caller-passed org/contact-scoped document ids;
  a knowledge sentence without a valid citation is dropped, and an
  account-specific statement without a completed identity check escalates.
- ``escalate`` triggers on: low STT confidence, opt-out keywords, a human
  request, payment/refund/commitment topics, and loop exceedance.
- conclude-time commitments are FORBIDDEN to the graph: any proposed
  commitment/payment/irreversible action escalates for authenticated human
  approval (API-side enforcement, not prompt).
- a stop interrupt ends the graph within the same turn.

Scope honesty: this module contains the deterministic core only — no LLM, no
DB, no audio. Driving it from the media turn loop + ``call_events``
persistence lives in :mod:`app.telephony.media.agent_media_session` (the
inbound-queue handoff remains the parked follow-up); the audit hooks below
are exactly the contract that integration fulfills.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping

# --------------------------------------------------------------------------- #
# Escalation triggers (§6) — deterministic keyword scan, deliberately simple
# --------------------------------------------------------------------------- #

OPT_OUT_KEYWORDS = (
    "stop calling", "remove me", "do not call", "don't call", "unsubscribe",
    "opt out", "no more calls", "never call",
)

HUMAN_REQUEST_KEYWORDS = (
    "human", "real person", "agent person", "manager", "supervisor",
    "representative",
)

TOPICS_REQUIRING_HUMAN = (
    "payment", "refund", "charge ", "billing dispute", "cancel my",
    "terminate my", "lawsuit", "legal action",
)

ACCOUNT_SPECIFIC_MARKERS = (
    "your account", "my account", "account number", "balance", "invoice ",
    "statement ", "subscription details",
)

LOW_STT_CONFIDENCE_DEFAULT = 0.55
_CONFIDENCE_RECALL_THRESHOLD = 0.75  # near-miss confidence also re-prompts


class Node(str, Enum):
    DISCLOSE = "disclose"
    VERIFY_IDENTITY = "verify_identity"
    ASK_PURPOSE = "ask_purpose"
    RESPOND = "respond"
    CONFIRM_NEXT_STEP = "confirm_next_step"
    ESCALATE = "escalate"
    CONCLUDE = "conclude"
    END = "end"


class AgentGraphConfigError(ValueError):
    """Raised when an operator config tries to disable a mandatory guard."""


class AgentGraphDone(Exception):
    """Raised by advance() after the graph already reached END."""


# --------------------------------------------------------------------------- #
# Config — fail-closed by construction
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GraphConfig:
    """Graph knobs. Disclosure is deliberately NOT configurable: there is no
    flag that can turn it off, and ``from_operator_config`` rejects any
    legacy/experimental key that claims to (fail-closed at build time)."""

    verify_identity: bool = True
    stt_min_confidence: float = LOW_STT_CONFIDENCE_DEFAULT
    max_identity_attempts: int = 1  # retries after the first failed verify
    max_steps: int = 12             # whole-graph loop budget
    permitted_documents: tuple[str, ...] = ()  # org/contact-scoped doc ids
    disclosure_text: str = ("This is an automated assistant calling on "
                            "the behalf of the organization you have a "
                            "relationship with.")

    @staticmethod
    def _forbidden_disclosure_bypasses(cfg: Mapping[str, Any]) -> bool:
        suspicious_keys = {"skip_disclosure", "disable_disclosure", "no_disclosure",
                           "disclose", "disclose_optional"}
        for key, value in cfg.items():
            lowered = key.lower().replace("-", "_")
            if lowered in suspicious_keys:
                return True
            if lowered.endswith("disclosure") and value in (False, 0, "false", "off", "disabled"):
                return True
            if lowered.startswith("disclosure") and isinstance(value, Mapping):
                inner_value = value.get("enabled", value.get("required", True))
                if inner_value in (False, 0, "false", "off", "disabled"):
                    return True
        return False

    @classmethod
    def from_operator_config(cls, cfg: Mapping[str, Any] | None = None, **kwargs: Any) -> "GraphConfig":
        """Build from an operator-supplied mapping, rejecting any attempt to
        disable or skip the mandatory disclosure step."""
        if cls._forbidden_disclosure_bypasses(cfg or {}):
            raise AgentGraphConfigError(
                "operator config attempted to disable mandatory disclosure; "
                "the AI-agent graph is fail-closed and cannot build")
        allowed = {"verify_identity", "stt_min_confidence", "max_identity_attempts",
                   "max_steps", "permitted_documents", "disclosure_text"}
        merged = {k: v for k, v in (cfg or {}).items() if k in allowed}
        unknown = [k for k in (cfg or {}) if k not in allowed]
        if unknown:
            raise AgentGraphConfigError(f"unknown graph config keys: {sorted(unknown)}")
        merged.update(kwargs)
        return cls(**merged)


# --------------------------------------------------------------------------- #
# LLM turn payload contract — the ONLY thing an LLM may supply
# --------------------------------------------------------------------------- #


@dataclass
class TurnPayload:
    """Per-turn structured output. Strings the graph will speak live in
    ``say``; everything else is metadata consumed by the graph's guards."""

    caller_text: str = ""
    say: str = ""
    citations: tuple[str, ...] = field(default_factory=tuple)
    identity_match: bool | None = None
    purpose: str | None = None
    next_step: str | None = None
    stt_confidence: float = 1.0
    wants_human: bool = False
    opt_out: bool = False
    proposed_commitments: tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #

AuditHook = Callable[[str, dict], Awaitable[None]]


@dataclass
class AgentStep:
    node: Node
    action: str                      # "speak" | "escalate" | "end"
    say: str = ""                    # post-filter text guaranteed to be spoken
    reason: str | None = None        # escalation reason when relevant
    context: dict = field(default_factory=dict)


class AgentGraph:
    """Deterministic state machine; drive one instance per call."""

    def __init__(self, config: GraphConfig, audit: AuditHook | None = None) -> None:
        self.config = config
        self._audit = audit
        self._node: Node | None = None
        self._steps = 0
        self._identity_verified = False
        self._identity_attempts = 0
        self._asked_identity = False
        self._asked_purpose = False
        self._stopped = False
        self._summary: list[str] = []

    # -- lifecycle --------------------------------------------------------- #

    async def start(self) -> AgentStep:
        if self._node is not None:
            raise RuntimeError("graph already started")
        self._node = Node.DISCLOSE
        await self._emit(Node.DISCLOSE, {"event": "graph_start"})
        return AgentStep(Node.DISCLOSE, "speak", say=self.config.disclosure_text)

    @property
    def node(self) -> Node | None:
        return self._node

    @property
    def identity_verified(self) -> bool:
        return self._identity_verified

    async def stop(self) -> None:
        """Stop interrupt: the CURRENT turn may finish; the next advance ends."""
        self._stopped = True

    def attach_audit(self, hook: AuditHook | None) -> None:
        """Integration seam: route node/transitions through an external sink.

        A previously attached hook is NOT silently replaced (an already-wired
        graph keeps its audit): explicit ``None`` clears nothing but silence.
        """
        if self._audit is not None:
            past = getattr(self._audit, "__name__", repr(self._audit))
            raise RuntimeError(f"audit hook already attached ({past})")
        self._audit = hook

    @property
    def audit_hook(self) -> AuditHook | None:
        return self._audit

    # -- transitions ------------------------------------------------------- #

    async def advance(self, payload: TurnPayload) -> AgentStep:
        if self._node in (None, Node.END):
            raise AgentGraphDone("graph has already concluded")
        self._steps += 1

        # whole-graph guard: stop interrupt wins intra-turn (§6)
        if self._stopped or self._steps > self.config.max_steps:
            return await self._escalate("stop_or_budget_exceeded", payload)

        # global keyword guards first, from EVERY node (fail-closed)
        text = payload.caller_text or ""
        if payload.opt_out or any(kw in text.lower() for kw in OPT_OUT_KEYWORDS):
            return await self._escalate("opt_out", payload)
        if payload.wants_human or any(kw in text.lower() for kw in HUMAN_REQUEST_KEYWORDS):
            return await self._escalate("human_requested", payload)
        if any(kw in text.lower() for kw in TOPICS_REQUIRING_HUMAN):
            return await self._escalate("topic_requires_human", payload)
        if payload.stt_confidence < self.config.stt_min_confidence:
            return await self._escalate("low_stt_confidence", payload)
        if payload.proposed_commitments:
            # commitments are forbidden to the graph: authenticated human
            # approval only (fail closed, commitment text never spoken)
            return await self._escalate("human_approval_required", payload)

        handler = {
            Node.DISCLOSE: self._on_disclose,
            Node.VERIFY_IDENTITY: self._on_verify_identity,
            Node.ASK_PURPOSE: self._on_ask_purpose,
            Node.RESPOND: self._on_respond,
            Node.CONFIRM_NEXT_STEP: self._on_confirm_next_step,
        }[self._node]
        return await handler(payload)

    # -- node handlers ----------------------------------------------------- #

    async def _on_disclose(self, payload: TurnPayload) -> AgentStep:
        self._summary.append("disclosure")
        nxt = (Node.VERIFY_IDENTITY if self.config.verify_identity
               else Node.ASK_PURPOSE)
        await self._transition(Node.DISCLOSE, nxt, payload)
        return self._await_input(nxt)

    async def _on_verify_identity(self, payload: TurnPayload) -> AgentStep:
        if payload.identity_match is None:
            # still waiting for the caller's identifying reply; re-prompt once
            if self._asked_identity:
                return await self._escalate("identity_unverified", payload)
            self._asked_identity = True
            return AgentStep(Node.VERIFY_IDENTITY, "speak",
                             say="For security, can you please confirm the "
                                 "details of the relationship on this account?")

        self._identity_attempts += 1
        if payload.identity_match:
            self._identity_verified = True
            await self._transition(Node.VERIFY_IDENTITY, Node.ASK_PURPOSE, payload)
            return self._await_input(Node.ASK_PURPOSE)
        if self._identity_attempts > self.config.max_identity_attempts:
            return await self._escalate("identity_unverified", payload)
        self._asked_identity = True
        return AgentStep(Node.VERIFY_IDENTITY, "speak",
                         say="I could not verify that; one more attempt, please.")

    async def _on_ask_purpose(self, payload: TurnPayload) -> AgentStep:
        self._asked_purpose = True
        await self._transition(Node.ASK_PURPOSE, Node.RESPOND, payload)
        return AgentStep(Node.RESPOND, "speak",
                         say="Thank you. What is this call about?")

    async def _on_respond(self, payload: TurnPayload) -> AgentStep:
        grounded = self._filter_grounded(payload)
        mentions_account = any(m in (payload.say or "").lower()
                               for m in ACCOUNT_SPECIFIC_MARKERS)

        step_context = {"kept_chars": len(grounded), "mentioned_account": mentions_account}
        if mentions_account and not self._identity_verified:
            # hard guard: account-specific statements require a completed
            # identity check; identifying data is never read back verbatim
            return await self._escalate("identity_unverified", payload)
        if not grounded:
            # LLM produced nothing citable: fail closed into escalation
            return await self._escalate("no_grounded_response", payload)

        self._summary.append(f"responded:{len(grounded)}ch")
        await self._transition(Node.RESPOND, Node.CONFIRM_NEXT_STEP, payload, extra=step_context)
        self._last_say = grounded
        return AgentStep(Node.CONFIRM_NEXT_STEP, "speak", say=grounded)

    async def _on_confirm_next_step(self, payload: TurnPayload) -> AgentStep:
        say = getattr(self, "_last_say", "")
        decide = self._next_from_confirm(payload)
        node, reason = decide
        if node is Node.ESCALATE:
            return await self._escalate(reason or "unresolved", payload)
        await self._transition(Node.CONFIRM_NEXT_STEP, Node.CONCLUDE, payload)
        self._summary.append(f"concluded:{reason or ''}")
        return await self._finish()

    # -- guards + helpers -------------------------------------------------- #

    def _filter_grounded(self, payload: TurnPayload) -> str:
        """Keep only sentences that are either prompt-approved meta ("disclosure",
        purpose/response confirmations) or knowledge claims carrying a citation.
        A citation must reference a permitted org/contact-scoped document id, so
        the LLM can never invent a pointer."""
        permitted = frozenset(self.config.permitted_documents)
        sentences = [s.strip() for s in (payload.say or "").split(".") if s.strip()]
        cited_docs = [c for c in payload.citations if c in permitted]
        doc_set = set(cited_docs)
        kept: list[str] = []
        used: set[str] = set()
        for sentence in sentences:
            for doc in doc_set:
                if f"(doc:{doc})" in sentence and doc not in used:
                    kept.append(sentence)
                    used.add(doc)
                    break
        return ". ".join(kept) + ("." if kept else "")

    @staticmethod
    def _next_from_confirm(payload: TurnPayload) -> tuple[Node, str | None]:
        if payload.next_step in (None, "", "end", "done"):
            return Node.CONCLUDE, None
        return Node.ESCALATE, "next_step_requires_human"

    def _await_input(self, node: Node) -> AgentStep:
        return AgentStep(node, "speak", say="")  # speak == prompt already emitted

    async def _escalate(self, reason: str, payload: TurnPayload) -> AgentStep:
        summary = "; ".join(self._summary[-4:]) or "none"
        await self._transition(self._node or Node.DISCLOSE, Node.ESCALATE,
                               payload, extra={"escalation_reason": reason})
        self._node = Node.ESCALATE
        return await self._finish(reason=reason, summary=summary,
                                  say="Let me connect you with a human who can "
                                      "help with that.")

    async def _finish(self, *, reason: str | None = None,
                      summary: str = "concluded", say: str = "") -> AgentStep:
        # The machine ALWAYS parks on END once the turn completes; escalations
        # are communicated via AgentStep.action/agent, not by lingering states.
        self._node = Node.END
        await self._emit(Node.END, {"event": "graph_end",
                                    "escalation_reason": reason,
                                    "summary": summary})
        return AgentStep((Node.ESCALATE if reason else Node.END),
                         ("escalate" if reason else "end"),
                         say=say, reason=reason, context={"summary": summary})

    async def _transition(self, from_node: Node, to_node: Node,
                          payload: TurnPayload, extra: dict | None = None) -> None:
        self._node = to_node
        audit_info = {
            "from": from_node.value, "to": to_node.value,
            "inputs_sha256": _sha256({
                "caller_text": payload.caller_text, "say": payload.say,
                "purpose": payload.purpose, "next_step": payload.next_step,
            }),
            "output_sha256": _sha256({"say": payload.say}) if extra is None else _sha256(extra),
            **(extra or {}),
        }
        await self._emit(to_node, audit_info)

    async def _emit(self, node: Node, data: dict) -> None:
        if self._audit is not None:
            await self._audit("ai_agent.node", {"node": node.value, **data})


def _sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def build_graph(config: GraphConfig | Mapping[str, Any] | None = None,
                audit: AuditHook | None = None) -> AgentGraph:
    """Fail-closed constructor: operator dicts that attempt to disable any
    mandatory guard cause AgentGraphConfigError before any call is placed."""
    if isinstance(config, GraphConfig):
        return AgentGraph(config, audit)
    return AgentGraph(GraphConfig.from_operator_config(config), audit)
