"""Agent-to-Agent Language Bridge (section 22).

Human source → canonical representation → INDEPENDENT per-agent-language outputs.

Anti-chain enforcement: each agent receives ONLY the canonical human text translated into
its own working language. Agent responses are translated back from the agent's output into
the human's language (again from that agent turn's canonical text — agent outputs become
canonical for *their own turn*, tagged source_kind='agent'). Agents never see, and can never
build on, another agent's translation. Deterministic infrastructure owns sequencing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from globaltalk.core.logging import get_logger
from globaltalk.services.translation import (TranslateOptions, detect_text_language,
                                              translate_text)

log = get_logger("bridge")


@dataclass
class AgentSpec:
    name: str
    language: str
    system_role: str = "assistant"


def run_bridge_turn(db: Session, *, org_id: str, text: str, source_language: str,
                    agents: list[dict], user_id: str | None = None) -> dict:
    started = time.perf_counter()
    if not source_language or source_language.upper() == "AUTO":
        source_language, _ = detect_text_language(db, text)

    # 1) Canonical representation of the human turn (immutable)
    canonical = {"text": text, "language": source_language,
                 "kind": "human", "canonical": True}

    # 2) Independent per-agent-language projections FROM the canonical source.
    #    Never agent_A_output → agent_B_input.
    projections = []
    for spec in agents:
        lang = spec["language"]
        if lang == source_language:
            projections.append({"agent": spec["name"], "language": lang, "text": text,
                                "provider": "identity", "from_canonical_source": True})
            continue
        outcome = translate_text(
            db, org_id=org_id, text=text,
            opts=TranslateOptions(source_language=source_language, target_language=lang,
                                  intent="quality_optimized"),
            user_id=user_id, persist_history=True, kind="bridge")
        projections.append({
            "agent": spec["name"], "language": lang, "text": outcome.translated_text,
            "provider": outcome.provider, "from_canonical_source": True,
            "quality_flags": outcome.quality_flags})

    # 3) Human-language projection back for display (each agent reply would be translated
    #    from THAT agent's canonical reply text; simulated replies are out of scope here —
    #    this endpoint powers the bridge contract, real agents plug in via /bridge/turn
    #    responses or the agents runtime).
    result = {
        "canonical_source": canonical,
        "agent_projections": projections,
        "chain_prevented": True,
        "note": ("Each projection is derived independently from the canonical human source. "
                 "No projection was used as input to another projection."),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    log.info("bridge_turn", extra={"agents": len(projections),
                                   "source_language": source_language})
    return result
