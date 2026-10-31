"""Outbound event dispatcher for Agent 06 (TTS) and TalkFlow orchestrator."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.models.events import (
    QualityAssessmentFinalEvent,
    QualityAssessmentHoldEvent,
    QualityAssessmentRejectedEvent,
    QualityAssessmentRetryEvent,
    QualityAssessmentWarningEvent,
)
from app.models.quality_report import QualityReport
from app.models.schemas import QualityDecision

log = get_logger("integration.agent06_publisher")


class Agent06Publisher:
    """Dispatches QA decisions and verified translations to Agent 06 (Voice Generation Agent)."""

    def __init__(self, agent06_url: str = settings.integration.agent06_url):
        self.agent06_url = agent06_url.rstrip("/")

    async def dispatch_report(self, report: QualityReport) -> Optional[Dict[str, Any]]:
        """Constructs appropriate TalkFlow event envelope and dispatches to Agent 06 / orchestrator."""
        # 1. Accepted Translations (Eligible for TTS Voice Synthesis)
        if report.decision == QualityDecision.ACCEPT:
            event = QualityAssessmentFinalEvent(
                evaluation_id=report.evaluation_id,
                candidate_hash=report.candidate_hash,
                session_id=report.session_id,
                conversation_id=report.conversation_id,
                speaker_id=report.speaker_id,
                utterance_id=report.utterance_id,
                segment_id=report.segment_id,
                translation_id=report.translation_id,
                source_lang=report.source_lang,
                target_lang=report.target_lang,
                source_text=report.source_text,
                target_text=report.target_text,
                decision=report.decision,
                quality_status=report.quality_status,
                overall_score=report.overall_score,
                scores={
                    "semantic": report.semantic_score,
                    "data_integrity": report.data_integrity_score,
                    "completeness": report.completeness_score,
                    "terminology": report.terminology_score,
                    "fluency": report.fluency_score,
                },
                checks={c.name: c.status for c in report.checks},
                issues=report.issues,
                provider_provenance={"provider": report.provider, "model": report.model},
            )
            return await self._send_to_agent06(event.model_dump())

        # 2. Accepted With Warnings (Eligible for TTS with diagnostics)
        elif report.decision == QualityDecision.ACCEPT_WITH_WARNINGS:
            event = QualityAssessmentFinalEvent(
                evaluation_id=report.evaluation_id,
                candidate_hash=report.candidate_hash,
                session_id=report.session_id,
                conversation_id=report.conversation_id,
                speaker_id=report.speaker_id,
                utterance_id=report.utterance_id,
                segment_id=report.segment_id,
                translation_id=report.translation_id,
                source_lang=report.source_lang,
                target_lang=report.target_lang,
                source_text=report.source_text,
                target_text=report.target_text,
                decision=report.decision,
                quality_status="warning",
                overall_score=report.overall_score,
                scores={"semantic": report.semantic_score, "data_integrity": report.data_integrity_score},
                checks={c.name: c.status for c in report.checks},
                issues=report.issues,
                provider_provenance={"provider": report.provider, "model": report.model},
            )
            return await self._send_to_agent06(event.model_dump())

        # 3. Retry Recommendation (Do not generate audio yet)
        elif report.decision == QualityDecision.RETRY_WITH_ALTERNATE_PROVIDER:
            log.info(
                f"[Agent 05 -> Agent 04] Recommended retry for segment {report.segment_id}: "
                f"{report.retry_recommendation}"
            )
            return None

        # 4. Rejection or Hold (Blocked from Agent 06)
        else:
            log.warning(
                f"[Agent 05] Blocked segment {report.segment_id} from Agent 06: "
                f"decision={report.decision} issues={len(report.issues)}"
            )
            return None

    async def _send_to_agent06(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        target = f"{self.agent06_url}/api/v1/tts/segment"
        headers = {"Authorization": f"Bearer {settings.integration.shared_secret}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(target, json=payload, headers=headers)
                if resp.status_code == 200:
                    log.info(f"[Agent 05 -> Agent 06] Successfully delivered accepted translation to TTS")
                    return resp.json()
        except Exception:
            # Agent 06 may not be running yet if user hasn't built Agent 06
            pass
        return None


publisher_to_agent06 = Agent06Publisher()

