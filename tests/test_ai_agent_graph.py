"""P4 — deterministic AI-agent state graph hard guards (phone_calling_plan §6).

Every guard from §6 is unit-tested fail-closed:
- disclosure mandatory: operator configs that try to disable it fail graph build;
- identity verified before ANY account-specific statement;
- respond cites ONLY permitted org/contact documents — ungrounded/invented
  citations are dropped, an empty grounded speaker escalates;
- escalation triggers: opt-out, human request, payment/refund topics, low STT
  confidence, proposed commitments (never a graduated/prompt-solved decision),
  loop-budget exceedance, stop interrupt;
- the machine always terminates on END; later advance() raises.
"""
from __future__ import annotations

import pytest

from app.telephony.ai_agent_graph import (
    AgentGraphConfigError,
    AgentGraphDone,
    GraphConfig,
    Node,
    TurnPayload,
    build_graph,
)


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def __call__(self, event: str, data: dict) -> None:
        self.events.append((event, data))


def _graph(**overrides) -> tuple[object, _Recorder]:
    rec = _Recorder()
    cfg = GraphConfig(**{"verify_identity": False,
                         "permitted_documents": ("doc_ok",), **overrides})
    return build_graph(cfg, audit=rec), rec


async def _drive_to_respond(g, rec=_Recorder(), permitted=("doc_ok",)):
    # start → disclose → ask_purpose → (arrive at respond)
    await g.start()
    await g.advance(TurnPayload())
    await g.advance(TurnPayload())
    return g


# --------------------------------------------------------------------------- #
# Build-time fail-closed guards
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_operator_config_cannot_disable_disclosure():
    for sneaky in ({"skip_disclosure": True},
                   {"disable_disclosure": True},
                   {"no_disclosure": "1"},
                   {"disclosure": False},
                   {"disclosure": {"enabled": False}},
                   {"disclose": True}):
        with pytest.raises(AgentGraphConfigError):
            build_graph(sneaky)


@pytest.mark.asyncio
async def test_unknown_operator_keys_rejected_and_valid_config_builds():
    with pytest.raises(AgentGraphConfigError):
        build_graph({"free_form_prompt_chaining": True})
    g = build_graph({"verify_identity": False, "max_steps": 9})
    assert g.config.max_steps == 9
    assert g.config.disclosure_text  # mandatory disclosure text present


@pytest.mark.asyncio
async def test_start_speaks_mandatory_disclosure():
    g, _ = _graph()
    step = await g.start()
    assert step.node == Node.DISCLOSE
    assert step.say == g.config.disclosure_text


# --------------------------------------------------------------------------- #
# Happy path + citation grounding
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_happy_path_concludes_and_keeps_only_cited_sentences():
    g, rec = _graph()
    await g.start()
    await g.advance(TurnPayload())                      # disclose → ask
    await g.advance(TurnPayload())                      # ask → respond
    step = await g.advance(TurnPayload(
        say="We can help with your plan. Policy says upgrade is free(doc:doc_ok). "
            "This sentence has no basis at all.",
        citations=("doc_ok",)))
    # ungrounded sentences dropped, only the cited one survives
    assert step.action == "speak"
    assert "Policy says upgrade is free(doc:doc_ok)" in step.say
    assert "no basis" not in step.say
    await g.advance(TurnPayload(next_step=None))        # confirm → conclude → end
    assert g.node == Node.END
    ends = [e for _, e in rec.events if e.get("event") == "graph_end"]
    assert len(ends) == 1


@pytest.mark.asyncio
async def test_invented_document_citation_is_dropped_and_fails_closed():
    g, _ = _graph()
    await _drive_to_respond(g)
    step = await g.advance(TurnPayload(
        say="According to policy(doc:doc_invented), you are qualified.",
        citations=("doc_invented",)))  # not in permitted allowlist
    assert step.action == "escalate"
    assert step.reason == "no_grounded_response"


@pytest.mark.asyncio
async def test_background_flow_of_dict_config_equivalent_to_dataclass():
    g = build_graph({"verify_identity": False,
                     "permitted_documents": ("doc_ok",)})
    await g.start()
    assert g.node == Node.DISCLOSE


# --------------------------------------------------------------------------- #
# Identity verification before account-specific statements
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_account_statement_without_verified_identity_escalates():
    g, _ = _graph(verify_identity=False)  # verification skipped entirely
    await _drive_to_respond(g)
    step = await g.advance(TurnPayload(
        say="Your account balance is settled(doc:doc_ok).",
        citations=("doc_ok",)))
    assert step.action == "escalate"
    assert step.reason == "identity_unverified"


@pytest.mark.asyncio
async def test_account_statement_allowed_after_verified_identity():
    g, _ = _graph(verify_identity=True)
    await g.start()
    await g.advance(TurnPayload())                      # disclose → verify
    await g.advance(TurnPayload(identity_match=True))   # verified → ask
    await g.advance(TurnPayload())                      # ask → respond
    step = await g.advance(TurnPayload(
        say="Your account was updated(doc:doc_ok).",
        citations=("doc_ok",)))
    assert step.action == "speak"
    assert g.node == Node.CONFIRM_NEXT_STEP


@pytest.mark.asyncio
async def test_verify_failure_retries_then_escalates():
    g, _ = _graph(verify_identity=True)
    await g.start()
    await g.advance(TurnPayload())                            # disclose → verify
    await g.advance(TurnPayload())                            # prompt for identity
    step = await g.advance(TurnPayload(identity_match=False))  # retry allowed
    assert step.action == "speak" and g.node == Node.VERIFY_IDENTITY
    step = await g.advance(TurnPayload(identity_match=False))  # budget exhausted
    assert step.action == "escalate"
    assert step.reason == "identity_unverified"


# --------------------------------------------------------------------------- #
# Escalation triggers (§6)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_opt_out_keyword_escapes_from_any_node():
    g, _ = _graph()
    await g.start()
    await g.advance(TurnPayload())
    step = await g.advance(TurnPayload(caller_text="Please stop calling me."))
    assert step.action == "escalate" and step.reason == "opt_out"


@pytest.mark.asyncio
async def test_human_request_escapes():
    g, _ = _graph()
    await g.start()
    step = await g.advance(TurnPayload(caller_text="I want to speak to a human."))
    assert step.reason == "human_requested"


@pytest.mark.asyncio
async def test_payment_refund_topic_escapes():
    g, _ = _graph()
    await g.start()
    step = await g.advance(TurnPayload(caller_text="I need a refund today."))
    assert step.reason == "topic_requires_human"


@pytest.mark.asyncio
async def test_low_stt_confidence_escapes():
    g, _ = _graph()
    await g.start()
    step = await g.advance(TurnPayload(stt_confidence=0.2))
    assert step.reason == "low_stt_confidence"


@pytest.mark.asyncio
async def test_proposed_commitments_never_speak_and_escalate():
    g, _ = _graph()
    await _drive_to_respond(g, rec=_Recorder())
    step = await g.advance(TurnPayload(
        say="All good(doc:doc_ok).", citations=("doc_ok",),
        proposed_commitments=("give 10% lifetime discount",)))
    assert step.action == "escalate"
    assert step.reason == "human_approval_required"
    # the commitment must never be spoken by the graph
    assert "10%" not in step.say


@pytest.mark.asyncio
async def test_stop_interrupt_ends_graph_within_the_turn():
    g, _ = _graph()
    await g.start()
    await g.advance(TurnPayload())
    await g.stop()
    step = await g.advance(TurnPayload(say="whatever(doc:doc_ok)",
                                       citations=("doc_ok",)))
    assert step.action == "escalate"
    assert step.reason == "stop_or_budget_exceeded"
    with pytest.raises(AgentGraphDone):
        await g.advance(TurnPayload())


@pytest.mark.asyncio
async def test_loop_budget_exceeded_escalates():
    g, _ = _graph(max_steps=3)
    await g.start()
    await g.advance(TurnPayload())   # 1 disclose→ask
    await g.advance(TurnPayload())   # 2 ask→respond
    await g.advance(TurnPayload(say="ok(doc:doc_ok)", citations=("doc_ok",)))
    step = await g.advance(TurnPayload(next_step=None))  # 4 > budget
    assert step.reason == "stop_or_budget_exceeded"
    with pytest.raises(AgentGraphDone):
        await g.advance(TurnPayload())


# --------------------------------------------------------------------------- #
# Audit contract (integration will map these onto CallEvents)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_every_transition_is_audited_with_hashes():
    g, rec = _graph()
    await g.start()
    await g.advance(TurnPayload())                      # disclose → ask
    await g.advance(TurnPayload())                      # ask → respond
    await g.advance(TurnPayload(say="fine (doc:doc_ok)", citations=("doc_ok",)))
    await g.advance(TurnPayload(next_step=None))        # confirm → conclude → end
    node_events = [e for name, e in rec.events if name == "ai_agent.node"]
    assert all(len(e["inputs_sha256"]) == 64 for e in node_events
               if "inputs_sha256" in e)
    transitions = [e for e in node_events if "event" not in e]
    path = [e["to"] for e in transitions]
    assert path[:4] == ["ask_purpose", "respond", "confirm_next_step", "conclude"]
    assert any(e.get("event") == "graph_end" for e in node_events)
