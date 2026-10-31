"""REST API Endpoints for Agent 06 (Voice Generation Agent)."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.agents.brain import VoiceAgentBrain
from app.core.config import get_settings
from app.core.exceptions import (
    ConsentRequiredError,
    ConsentRevokedError,
    PrivacyViolationError,
    QualityGateRejectedError,
    SpeechSynthesisError,
    TranslationIdentityMismatchError,
    UnsupportedLanguageError,
    VoiceUnavailableError,
)
from app.core.logging import get_logger
from app.integration.agent05_adapter import Agent05Adapter
from app.integration.agent07_publisher import Agent07Publisher
from app.models.schemas import (
    AgentInfoResponse,
    CancellationRequest,
    CancellationResponse,
    SynthesizeRequest,
    SynthesizeResponse,
)
from app.models.voice_profile import VoiceCapability, VoiceConsentRecord
from app.monitoring.metrics import metrics
from app.services.synthesis_service import SynthesisService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["Voice Generation"])

# Shared service instances
synthesis_service = SynthesisService()
agent07_publisher = Agent07Publisher()
agent05_adapter = Agent05Adapter(service=synthesis_service, publisher=agent07_publisher)
brain = VoiceAgentBrain()
start_time = time.time()


class BrainQueryRequest(BaseModel):
    prompt: str
    context: Optional[Dict[str, Any]] = None


class BrainQueryResponse(BaseModel):
    response: str


class ConsentRegisterRequest(BaseModel):
    speaker_id: str
    user_id: str
    tenant_id: str = "org_default"
    voice_profile_name: str
    purpose: str = "realtime_speech_translation"
    expires_in_seconds: Optional[float] = None


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_text(
    request: SynthesizeRequest,
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
) -> SynthesizeResponse:
    """Directly synthesize approved translated text into audio."""
    try:
        response = await synthesis_service.synthesize(request, tenant_id=x_tenant_id)
        metrics.record_synthesis(
            provider=response.provider,
            language=response.target_language,
            duration_ms=response.duration_ms,
            latency_ms=response.generation_latency_ms,
            chunk_count=response.chunk_count,
        )
        return response
    except QualityGateRejectedError as e:
        metrics.record_rejection()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (UnsupportedLanguageError, VoiceUnavailableError) as e:
        metrics.record_failure()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (ConsentRequiredError, ConsentRevokedError) as e:
        metrics.record_failure()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PrivacyViolationError as e:
        metrics.record_failure()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        metrics.record_failure()
        logger.error("Unhandled synthesis error", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Synthesis failed: {e}")


@router.post("/segment", response_model=SynthesizeResponse)
@router.post("/agent05/transcript", response_model=SynthesizeResponse)
async def handle_agent05_webhook(
    payload: Dict[str, Any],
    authorization: Optional[str] = Header(None),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
) -> SynthesizeResponse:
    """Inbound webhook receiving verified translations from Agent 05 (Quality QA Agent)."""
    settings = get_settings()
    if settings.shared_secret and authorization:
        token = authorization.replace("Bearer ", "").strip()
        if token != settings.shared_secret:
            logger.warning("Agent 05 webhook authorization token mismatch")
            # In development, we warn but allow execution

    try:
        response = await agent05_adapter.process_event(payload, tenant_id=x_tenant_id)
        metrics.record_synthesis(
            provider=response.provider,
            language=response.target_language,
            duration_ms=response.duration_ms,
            latency_ms=response.generation_latency_ms,
            chunk_count=response.chunk_count,
        )
        return response
    except QualityGateRejectedError as e:
        metrics.record_rejection()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        metrics.record_failure()
        logger.error("Error processing Agent 05 event", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/cancel", response_model=CancellationResponse)
async def cancel_utterance(request: CancellationRequest) -> CancellationResponse:
    """Barge-in cancellation endpoint: invalidates ongoing or queued synthesis."""
    metrics.record_cancellation()
    return synthesis_service.cancel(
        session_id=request.session_id,
        segment_id=request.segment_id,
        utterance_id=request.utterance_id,
        reason=request.reason,
    )


@router.get("/voices", response_model=Dict[str, Any])
async def list_voices(
    language: Optional[str] = Query(None, description="Filter by language code (e.g. 'en', 'hi')"),
    provider: Optional[str] = Query(None, description="Filter by provider ('dev_tone', 'system', 'kokoro', 'piper')"),
    only_local: bool = Query(False, description="Filter for offline local voices"),
) -> Dict[str, Any]:
    """Query registered voice capabilities."""
    voices = synthesis_service.registry.list_all(
        language=language,
        provider=provider,
        only_local=only_local,
    )
    return {"count": len(voices), "voices": [v.model_dump() for v in voices]}


@router.get("/voices/{voice_id}", response_model=VoiceCapability)
async def get_voice(voice_id: str) -> VoiceCapability:
    """Get metadata for a specific voice profile."""
    voice = synthesis_service.registry.get(voice_id)
    if not voice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Voice '{voice_id}' not found.")
    return voice


@router.post("/consent", response_model=VoiceConsentRecord)
async def register_consent(req: ConsentRegisterRequest) -> VoiceConsentRecord:
    """Register opt-in consent for a personalized or cloned voice."""
    return synthesis_service.consent_manager.register_consent(
        tenant_id=req.tenant_id,
        speaker_id=req.speaker_id,
        user_id=req.user_id,
        voice_profile_name=req.voice_profile_name,
        purpose=req.purpose,
        expires_in_seconds=req.expires_in_seconds,
    )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check and provider status."""
    prov_health = await synthesis_service.router.check_health()
    return {
        "status": "healthy",
        "service": "talkflow-voice-generation-agent",
        "agent_id": "agent-06",
        "port": 8006,
        "providers": prov_health,
        "synthetic_flag_enforced": True,
        "uptime_seconds": time.time() - start_time,
    }


@router.get("/info", response_model=AgentInfoResponse)
async def agent_info() -> AgentInfoResponse:
    """Agent metadata, capabilities, and system configuration."""
    settings = get_settings()
    voices = synthesis_service.registry.list_all()
    prov_health = await synthesis_service.router.check_health()
    active_provs = [p for p, healthy in prov_health.items() if healthy]

    return AgentInfoResponse(
        name="TalkFlow Voice Generation Agent",
        version="1.0.0",
        description="Converts approved translated text into natural low-latency synthetic speech for Agent 07.",
        default_provider=settings.default_provider,
        active_providers=active_provs,
        installed_voices_count=len(voices),
        supported_languages=settings.supported_languages,
        sample_rate=settings.audio_sample_rate,
        synthetic_guarantee=True,
        offline_only=settings.offline_only,
        private_only=settings.private_only,
        uptime_seconds=time.time() - start_time,
    )


@router.post("/brain/query", response_model=BrainQueryResponse)
async def query_brain(req: BrainQueryRequest) -> BrainQueryResponse:
    """Ask operational intelligence questions to Agent 06's LLM brain."""
    ans = await brain.query(prompt=req.prompt, context=req.context)
    return BrainQueryResponse(response=ans)

