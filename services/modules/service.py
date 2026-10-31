"""FastAPI APIRouter exposing endpoints for TalkFlow Advanced Product Expansion (Modules A - K)."""
from __future__ import annotations

import base64
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Module imports
from modules.conversation_experience import conversation_experience_engine
from modules.developer_platform import developer_platform_engine
from modules.enterprise_privacy import enterprise_privacy_engine, RetentionPolicy
from modules.glossary_tm import glossary_tm_engine, GlossaryTerm, UserCorrectionSubmission
from modules.meeting_fanout import (
    fanout_engine,
    Participant,
    ParticipantLanguagePreference,
    SourceUtterance,
    fanout_cache,
)
from modules.meeting_intelligence import (
    meeting_intelligence_engine,
    AskMeetingAIQuery,
    TranscriptTurn,
)
from modules.model_router import dynamic_model_router, RoutingConstraint
from modules.quality_confidence import quality_confidence_engine, SegmentQualityAudit
from modules.telemetry import telemetry_engine
from modules.video_studio import video_studio_engine
from modules.voice_expression import (
    AcousticFeatures,
    DEFAULT_VOICE_CONFIG,
    ExpressiveSynthesisRequest,
    ExpressiveSynthesisResponse,
    PronunciationRule,
    ProsodyTransferPlan,
    SpeakerProsodyProfile,
    TalkFlowVoiceConfig,
    VoiceConsentAuditRecord,
    VoiceConsentRecord,
    VoiceEnrollmentRequest,
    VoiceGenerationMode,
    voice_expression_engine,
)

router = APIRouter(prefix="/api/v1", tags=["Advanced Product Expansion"])


# ==========================================
# MODULE A: MULTI-LANGUAGE MEETING FAN-OUT
# ==========================================

class CreateRoomRequest(BaseModel):
    room_id: str
    title: str = "TalkFlow Multilingual Meeting"


class JoinRoomRequest(BaseModel):
    room_id: str
    participant_id: str
    name: str = "Participant"
    spoken_language: str = "auto"
    preferred_listen_language: str = "en"
    understood_languages: Optional[List[str]] = None
    playback_mode: str = "translated"  # 'translated', 'original', 'both'


class PlanFanoutRequest(BaseModel):
    room_id: str
    speaker_id: str
    text: str
    detected_source_lang: str


@router.post("/meetings/rooms/create", summary="Create or retrieve room session")
async def create_room(req: CreateRoomRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    room = fanout_engine.get_or_create_room(req.room_id, title=req.title, tenant_id=x_tenant_id)
    return {"status": "ok", "room": room}


@router.post("/meetings/rooms/join", summary="Join or update participant in meeting room")
async def join_room(req: JoinRoomRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    p = Participant(
        participant_id=req.participant_id,
        name=req.name,
        tenant_id=x_tenant_id,
        spoken_language=req.spoken_language,
        preferred_listen_language=req.preferred_listen_language,
        understood_languages=req.understood_languages if req.understood_languages is not None else [req.preferred_listen_language],
        playback_mode=req.playback_mode,
        audio_mode=req.playback_mode,
    )
    room = fanout_engine.join_room(req.room_id, p, tenant_id=x_tenant_id)
    return {"status": "ok", "room_id": req.room_id, "active_participants": len(room.participants)}


@router.post("/meetings/rooms/{room_id}/leave", summary="Leave meeting room")
async def leave_room(room_id: str, participant_id: str = Query(...), x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    fanout_engine.leave_room(room_id, participant_id)
    return {"status": "ok", "left": participant_id}


class IngestUtteranceRequest(BaseModel):
    source_participant_id: str
    source_track_id: str = "mic_01"
    source_language: str = "en"
    transcript: str
    start_time: float = 0.0
    end_time: float = 0.0
    utterance_id: Optional[str] = None


@router.post("/meetings/rooms/{room_id}/utterance/ingest", summary="Ingest single speaker committed utterance")
async def ingest_utterance(
    room_id: str,
    req: IngestUtteranceRequest = Body(...),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    utt = fanout_engine.ingest_source_utterance(
        room_id=room_id,
        source_participant_id=req.source_participant_id,
        source_track_id=req.source_track_id,
        source_language=req.source_language,
        transcript=req.transcript,
        start_time=req.start_time,
        end_time=req.end_time,
        utterance_id=req.utterance_id,
        tenant_id=x_tenant_id,
    )
    return utt


@router.post("/meetings/rooms/fanout/plan", summary="Compute optimal 1-to-N translation fan-out dispatch")
async def plan_fanout(req: PlanFanoutRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    plan = fanout_engine.plan_fanout(
        room_id=req.room_id,
        speaker_id=req.speaker_id,
        text=req.text,
        detected_source_lang=req.detected_source_lang,
        tenant_id=x_tenant_id,
    )
    return plan


class UpdateLanguageRequest(BaseModel):
    new_language: str
    audio_mode: Optional[str] = None


class ExecuteUtteranceFanoutRequest(BaseModel):
    source_participant_id: str
    source_language: str
    transcript: str
    translations: Dict[str, str] = {}
    audio_artifacts: Optional[Dict[str, str]] = None
    source_track_id: str = "mic_01"
    utterance_id: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0


@router.post("/meetings/rooms/preferences", summary="Set or update participant language & audio mode preference")
async def set_room_participant_preference(
    pref: ParticipantLanguagePreference = Body(...),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    pref.tenant_id = x_tenant_id
    p = fanout_engine.set_participant_preference(pref.room_id, pref, tenant_id=x_tenant_id)
    return {"status": "ok", "participant": p}


@router.put("/meetings/rooms/{room_id}/participants/{participant_id}/language", summary="Change participant language dynamically without room restart")
async def update_language_dynamic(
    room_id: str,
    participant_id: str,
    req: UpdateLanguageRequest = Body(...),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    try:
        sub = fanout_engine.update_participant_language(
            room_id=room_id,
            participant_id=participant_id,
            new_language=req.new_language,
            audio_mode=req.audio_mode,
            tenant_id=x_tenant_id,
        )
        return {"status": "ok", "subscription": sub}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/meetings/rooms/{room_id}/utterance/execute", summary="Execute full end-to-end fan-out across audio, TTS, and subtitles")
async def execute_fanout_utterance(
    room_id: str,
    req: ExecuteUtteranceFanoutRequest = Body(...),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    res = fanout_engine.execute_complete_fanout(
        room_id=room_id,
        source_participant_id=req.source_participant_id,
        source_language=req.source_language,
        transcript=req.transcript,
        translations=req.translations,
        audio_artifacts=req.audio_artifacts,
        source_track_id=req.source_track_id,
        utterance_id=req.utterance_id,
        start_time=req.start_time,
        end_time=req.end_time,
        tenant_id=x_tenant_id,
    )
    return res


@router.get("/meetings/rooms/{room_id}/telemetry", summary="Get room-level fan-out and savings telemetry")
async def get_room_telemetry(room_id: str, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    telemetry = fanout_engine.get_room_telemetry(room_id, tenant_id=x_tenant_id)
    return telemetry


@router.get("/meetings/fanout/global-telemetry", summary="Get global cross-room fan-out diagnostics")
async def get_fanout_global_telemetry():
    return fanout_engine.get_global_telemetry()



# ==========================================
# MODULE B: VOICE EXPRESSION & CONSENT
# ==========================================

class VoiceConsentRequest(BaseModel):
    speaker_id: str
    speaker_name: str
    purpose: str = "realtime_meeting_translation"
    expires_in_days: int = 90


@router.post("/voice/consent/register", summary="Explicitly register speaker voice consent")
async def register_voice_consent(req: VoiceConsentRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    rec = voice_expression_engine.register_consent(
        tenant_id=x_tenant_id,
        speaker_id=req.speaker_id,
        speaker_name=req.speaker_name,
        purpose=req.purpose,
        expires_in_days=req.expires_in_days,
    )
    return rec


@router.post("/voice/consent/revoke", summary="Revoke speaker consent immediately")
async def revoke_voice_consent(speaker_id: str, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    ok = voice_expression_engine.revoke_consent(x_tenant_id, speaker_id)
    return {"revoked": ok, "fallback": "normal_synthetic_voice_enforced"}


@router.get("/voice/consent/verify", summary="Verify speaker consent status")
async def verify_voice_consent(speaker_id: str, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    active = voice_expression_engine.verify_consent(x_tenant_id, speaker_id)
    return {"speaker_id": speaker_id, "consent_active": active}


@router.post("/voice/pronunciation/rule", summary="Add custom terminology pronunciation rule")
async def add_pronunciation_rule(rule: PronunciationRule = Body(...), x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    rules = voice_expression_engine._pronunciations.setdefault(x_tenant_id, [])
    rules.append(rule)
    return {"status": "ok", "total_rules": len(rules)}


@router.get("/voice/consistent-voice", summary="Resolve consistent speaker voice for target language")
async def resolve_consistent_voice(speaker_id: str, target_lang: str, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    v = voice_expression_engine.resolve_consistent_voice(x_tenant_id, speaker_id, target_lang)
    return {"speaker_id": speaker_id, "target_lang": target_lang, "resolved_voice": v}


class AnalyzeAudioRequest(BaseModel):
    audio_base64: Optional[str] = None
    transcript: str = ""
    language: str = "hi"
    sample_rate: int = 24000


@router.post("/voice/expressive/analyze", response_model=AcousticFeatures, summary="Extract acoustic, prosody, and emotional delivery features")
async def analyze_expressive_speech(req: AnalyzeAudioRequest):
    audio_bytes = None
    if req.audio_base64:
        try:
            audio_bytes = base64.b64decode(req.audio_base64)
        except Exception:
            pass
    return voice_expression_engine.analyze_audio_signal(
        audio_bytes=audio_bytes,
        sample_rate=req.sample_rate,
        transcript=req.transcript,
        language=req.language,
    )


class PlanProsodyRequest(BaseModel):
    source_features: AcousticFeatures
    source_text: str
    target_text: str
    source_lang: str = "hi"
    target_lang: str = "en"
    voice_mode: VoiceGenerationMode = VoiceGenerationMode.EXPRESSIVE
    speaker_id: str = "speaker_001"


@router.post("/voice/expressive/plan", response_model=ProsodyTransferPlan, summary="Plan target prosody, pitch, rate, and SSML markup")
async def plan_prosody_endpoint(req: PlanProsodyRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    return voice_expression_engine.plan_prosody_transfer(
        source_features=req.source_features,
        source_text=req.source_text,
        target_text=req.target_text,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        voice_mode=req.voice_mode,
        speaker_id=req.speaker_id,
        tenant_id=x_tenant_id,
    )


@router.post("/voice/expressive/synthesize", response_model=ExpressiveSynthesisResponse, summary="Synthesize expressive speech across Modes 1, 2, and 3")
async def synthesize_expressive_speech(req: ExpressiveSynthesisRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    req.tenant_id = x_tenant_id
    return await voice_expression_engine.synthesize_expressive(req)


@router.post("/voice/expressive/enroll", summary="Enroll speaker voice with biometric consent statement")
async def enroll_speaker_voice(req: VoiceEnrollmentRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    rec = voice_expression_engine.register_consent(
        tenant_id=x_tenant_id,
        speaker_id=req.speaker_id,
        speaker_name=req.speaker_name,
        purpose=req.purpose,
        consent_statement=req.consent_statement,
        expires_in_days=req.expires_in_days,
        reference_audio_base64=req.reference_audio_base64,
    )
    return rec


@router.get("/voice/config/default", response_model=TalkFlowVoiceConfig, summary="Get canonical default TalkFlow voice configuration")
async def get_default_voice_config():
    """Returns the default TalkFlow voice configuration (Rules 1, 8)."""
    return voice_expression_engine.get_default_configuration()


@router.get("/voice/consent/audit-log", response_model=List[VoiceConsentAuditRecord], summary="Get auditable database records for consent events")
async def get_consent_audit_log(
    speaker_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    """Retrieves auditable database records strictly isolated by tenant (Rules 6, 7)."""
    return voice_expression_engine.get_audit_log(tenant_id=x_tenant_id, speaker_id=speaker_id, limit=limit)


class SecureProfileAccessRequest(BaseModel):
    speaker_id: str
    requester_id: str


@router.post("/voice/profile/secure", response_model=SpeakerProsodyProfile, summary="Securely access speaker profile with authorization")
async def get_secure_voice_profile(
    req: SecureProfileAccessRequest,
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
    x_requester_tenant: str = Header("org_default", alias="X-Requester-Tenant"),
):
    """Securely resolves voice profile with multi-tenant and cross-user authorization (Rules 4, 7)."""
    try:
        return voice_expression_engine.get_profile_secure(
            tenant_id=x_tenant_id,
            speaker_id=req.speaker_id,
            requester_id=req.requester_id,
            requester_tenant=x_requester_tenant,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ==========================================
# MODULE C: AI MEETING INTELLIGENCE
# ==========================================

class GenerateIntelligenceRequest(BaseModel):
    meeting_id: str
    title: str = "Multilingual Project Meeting"
    turns: List[TranscriptTurn]
    target_notes_lang: str = "en"


@router.post("/meetings/intelligence/generate", summary="Synthesize meeting intelligence dossier")
async def generate_meeting_intelligence(req: GenerateIntelligenceRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    rep = await meeting_intelligence_engine.generate_intelligence(
        meeting_id=req.meeting_id,
        turns=req.turns,
        title=req.title,
        tenant_id=x_tenant_id,
        target_notes_lang=req.target_notes_lang,
    )
    return rep


@router.post("/meetings/ai/ask", summary="Ask Meeting AI grounded in transcript citations")
async def ask_meeting_ai(req: AskMeetingAIQuery, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    req.tenant_id = x_tenant_id
    try:
        ans = await meeting_intelligence_engine.ask_meeting_ai(req)
        return ans
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/meetings/history", summary="List searchable meeting history")
async def list_meeting_history(x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    return meeting_intelligence_engine.list_meetings(x_tenant_id)


@router.get("/meetings/{meeting_id}", summary="Retrieve meeting intelligence report")
async def get_meeting_report(meeting_id: str, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    rep = meeting_intelligence_engine.get_report(x_tenant_id, meeting_id)
    if not rep:
        raise HTTPException(status_code=404, detail="Meeting report not found.")
    return rep


# ==========================================
# MODULE D: VIDEO LOCALIZATION STUDIO
# ==========================================

class CreateStudioProjectRequest(BaseModel):
    project_id: str
    video_filename: str
    video_path: str = ""
    source_language: str = "auto"
    target_languages: List[str] = ["en"]
    duration_sec: float = 0.0
    segments_manifest: Optional[List[Dict[str, Any]]] = None


@router.post("/studio/projects", summary="Create or initialize video studio project")
async def create_studio_project(req: CreateStudioProjectRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    proj = video_studio_engine.create_project(
        project_id=req.project_id,
        video_filename=req.video_filename,
        video_path=req.video_path,
        source_language=req.source_language,
        target_languages=req.target_languages,
        duration_sec=req.duration_sec,
        tenant_id=x_tenant_id,
    )
    if req.segments_manifest:
        for t_lang in req.target_languages:
            video_studio_engine.populate_from_orchestrator(
                project_id=req.project_id,
                segments_manifest=req.segments_manifest,
                video_path=req.video_path,
                target_lang=t_lang,
                tenant_id=x_tenant_id,
            )
    return proj


class UpdateSegmentRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None


@router.get("/studio/projects/{project_id}", summary="Get studio project state and segments")
async def get_studio_project(project_id: str, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    proj = video_studio_engine.get_project(project_id, tenant_id=x_tenant_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Studio project not found.")
    return proj


@router.put("/studio/projects/{project_id}/segments/{segment_id}", summary="Edit segment text and re-synthesize audio")
async def update_studio_segment(
    project_id: str,
    segment_id: str,
    req: UpdateSegmentRequest,
    target_lang: str = Query("en", description="Target language"),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    try:
        updated = await video_studio_engine.update_segment(
            project_id=project_id,
            target_lang=target_lang,
            segment_id=segment_id,
            new_text=req.text,
            voice_id=req.voice_id,
            tenant_id=x_tenant_id,
        )
        return updated
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/studio/projects/{project_id}/subtitles", summary="Export SRT/VTT subtitles")
async def get_studio_subtitles(
    project_id: str,
    target_lang: str = Query("en"),
    format: str = Query("srt", description="Subtitle format: srt or vtt"),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    proj = video_studio_engine.get_project(project_id, tenant_id=x_tenant_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found.")
    content = proj.subtitles_srt.get(target_lang, "") if format == "srt" else proj.subtitles_vtt.get(target_lang, "")
    media_type = "text/plain" if format == "srt" else "text/vtt"
    return Response(content=content, media_type=media_type)


# ==========================================
# MODULE E: TRANSLATION MEMORY & GLOSSARY
# ==========================================

@router.post("/glossary/terms", summary="Add terminology or glossary term")
async def add_glossary_term(term: GlossaryTerm = Body(...), x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    term.tenant_id = x_tenant_id
    saved = glossary_tm_engine.add_term(term)
    return saved


@router.get("/glossary/terms", summary="List terminology for tenant")
async def list_glossary_terms(
    source_lang: Optional[str] = None,
    target_lang: Optional[str] = None,
    domain: Optional[str] = None,
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID"),
):
    return glossary_tm_engine.list_terms(x_tenant_id, source_lang=source_lang, target_lang=target_lang, domain=domain)


@router.post("/glossary/corrections", summary="Submit approved user correction to TM")
async def submit_user_correction(sub: UserCorrectionSubmission = Body(...), x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    sub.tenant_id = x_tenant_id
    saved = glossary_tm_engine.submit_user_correction(sub)
    return saved


class GlossaryLookupRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str
    domain: str = "general"


@router.post("/glossary/lookup", summary="Lookup exact/fuzzy TM and apply glossary pre-translation")
async def lookup_glossary_and_tm(req: GlossaryLookupRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    res = glossary_tm_engine.lookup(
        text=req.text,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        tenant_id=x_tenant_id,
        domain=req.domain,
    )
    return res


# ==========================================
# MODULE F: DYNAMIC MODEL ROUTER
# ==========================================

@router.get("/models/list", summary="List available model profiles across tasks")
async def list_models(task: Optional[str] = Query(None, description="stt, mt, tts, diarization, vad, enhancement")):
    return dynamic_model_router.list_models(task=task)


@router.post("/models/route", summary="Dynamically select primary model and fallback chain")
async def route_model(constraint: RoutingConstraint = Body(...)):
    try:
        res = dynamic_model_router.route_model(constraint)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================
# MODULE G: AUDIO QUALITY & CONFIDENCE SYSTEM
# ==========================================

@router.post("/quality/audit", summary="Record segment audit trail")
async def record_segment_audit(audit: SegmentQualityAudit = Body(...)):
    saved = quality_confidence_engine.record_audit(audit)
    return saved


@router.get("/quality/audits", summary="List segment quality audits")
async def list_segment_audits(limit: int = 50, requires_review_only: bool = False):
    return quality_confidence_engine.list_audits(limit=limit, requires_review_only=requires_review_only)


class ManualCorrectionRequest(BaseModel):
    corrected_text: str
    reviewed_by: str = "human_reviewer"


@router.put("/quality/audits/{segment_id}/correct", summary="Submit manual review correction")
async def manual_correct_segment(segment_id: str, req: ManualCorrectionRequest):
    updated = quality_confidence_engine.submit_manual_correction(
        segment_id=segment_id,
        corrected_text=req.corrected_text,
        reviewed_by=req.reviewed_by,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Audit record not found.")
    return updated


# ==========================================
# MODULE H: CONVERSATION EXPERIENCE
# ==========================================

class SpeechBoundaryRequest(BaseModel):
    room_id: str
    speaker_id: str
    timestamp_ms: int
    text: Optional[str] = ""
    duration_ms: int = 0


@router.post("/conversation/speech-start", summary="Handle speech onset and detect barge-in")
async def on_speech_start(req: SpeechBoundaryRequest):
    return conversation_experience_engine.handle_speech_start(
        room_id=req.room_id,
        speaker_id=req.speaker_id,
        timestamp_ms=req.timestamp_ms,
    )


@router.post("/conversation/speech-end", summary="Handle speech offset and detect backchannel")
async def on_speech_end(req: SpeechBoundaryRequest):
    return conversation_experience_engine.handle_speech_end(
        room_id=req.room_id,
        speaker_id=req.speaker_id,
        text=req.text or "",
        timestamp_ms=req.timestamp_ms,
        duration_ms=req.duration_ms,
    )


@router.get("/conversation/room-state", summary="Get room acoustic and ducking state")
async def get_room_acoustic_state(room_id: str):
    return conversation_experience_engine.get_or_create_state(room_id)


# ==========================================
# MODULE I: DEVELOPER PLATFORM & API
# ==========================================

class CreateKeyRequest(BaseModel):
    name: str = "My Developer Key"
    role: str = "developer"
    quota_minutes: float = 1000.0


@router.post("/developer/keys/create", summary="Generate new developer API key")
async def create_developer_key(req: CreateKeyRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    token, rec = developer_platform_engine.create_api_key(
        name=req.name,
        tenant_id=x_tenant_id,
        role=req.role,
        quota_minutes=req.quota_minutes,
    )
    return {"api_key": token, "record": rec}


@router.get("/developer/keys/validate", summary="Authenticate API key")
async def validate_developer_key(x_api_key: str = Header(..., alias="X-API-Key")):
    rec = developer_platform_engine.authenticate_key(x_api_key)
    if not rec:
        raise HTTPException(status_code=401, detail="Invalid, revoked, or expired API key.")
    return {"authenticated": True, "key_id": rec.key_id, "role": rec.role, "used_minutes": rec.total_minutes_used}


class RegisterWebhookRequest(BaseModel):
    target_url: str
    event_types: List[str] = ["job.completed", "meeting.intelligence.ready"]


@router.post("/developer/webhooks", summary="Register webhook endpoint")
async def register_webhook(req: RegisterWebhookRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    wh = developer_platform_engine.register_webhook(
        target_url=req.target_url,
        event_types=req.event_types,
        tenant_id=x_tenant_id,
    )
    return wh


@router.get("/developer/downloads", summary="Download localized media via signed HMAC token")
async def download_file_signed(file: str = Query(...), expires: int = Query(...), sig: str = Query(...)):
    valid = developer_platform_engine.verify_download_signature(file_path=file, expires=expires, signature=sig)
    if not valid:
        raise HTTPException(status_code=403, detail="Signature invalid or download URL expired.")
    p = Path(file)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(p, filename=p.name)


# ==========================================
# MODULE J: ENTERPRISE PRIVACY & SECURITY
# ==========================================

@router.post("/enterprise/retention-policy", summary="Configure tenant retention and training consent")
async def set_enterprise_retention(policy: RetentionPolicy = Body(...), x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    policy.tenant_id = x_tenant_id
    saved = enterprise_privacy_engine.set_retention_policy(policy)
    return saved


@router.get("/enterprise/retention-policy", summary="Get tenant retention policy")
async def get_enterprise_retention(x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    return enterprise_privacy_engine.get_retention_policy(x_tenant_id)


class AssignRoleRequest(BaseModel):
    user_id: str
    role: str


@router.post("/enterprise/roles/assign", summary="Assign user RBAC role")
async def assign_user_role(req: AssignRoleRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    assignment = enterprise_privacy_engine.assign_role(req.user_id, x_tenant_id, req.role)
    return assignment


@router.get("/enterprise/audit-logs", summary="Query enterprise compliance audit trail")
async def query_audit_logs(limit: int = 50, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    return enterprise_privacy_engine.query_audit_logs(x_tenant_id, limit=limit)


class DeleteRecordingRequest(BaseModel):
    file_path: str
    user_id: str = "user_admin"


@router.delete("/enterprise/recordings", summary="User-controlled secure recording deletion")
async def delete_enterprise_recording(req: DeleteRecordingRequest, x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")):
    try:
        deleted = enterprise_privacy_engine.delete_recording(
            file_path=req.file_path,
            tenant_id=x_tenant_id,
            user_id=req.user_id,
        )
        return {"deleted": deleted, "file_path": req.file_path}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ==========================================
# MODULE K: TELEMETRY & SLA MONITORING
# ==========================================

@router.get("/telemetry/summary", summary="System SLA, RTF, latency, hardware, and cost metrics")
async def get_telemetry_summary():
    return telemetry_engine.get_system_summary()


class RecordJobTelemetryRequest(BaseModel):
    job_id: str
    audio_minutes: float
    ttfa_ms: float
    end_to_end_ms: float
    stt_provider: str = "faster-whisper"
    mt_provider: str = "google-gtx"
    tts_provider: str = "edge_tts"
    is_success: bool = True
    retries: int = 0


@router.post("/telemetry/record-job", summary="Record job telemetry and calculate costs")
async def record_job_telemetry(req: RecordJobTelemetryRequest):
    return telemetry_engine.record_job_metrics(
        job_id=req.job_id,
        audio_minutes=req.audio_minutes,
        ttfa_ms=req.ttfa_ms,
        end_to_end_ms=req.end_to_end_ms,
        stt_provider=req.stt_provider,
        mt_provider=req.mt_provider,
        tts_provider=req.tts_provider,
        is_success=req.is_success,
        retries=req.retries,
    )
