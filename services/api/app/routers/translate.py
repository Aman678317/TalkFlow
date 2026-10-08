"""Translation API (PDD §14): /translate (single + batch), /detect-language,
/history, /languages capability registry.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.session import get_db
from app.deps import Principal, require_scope, rl_translate
from app.errors import AuthenticationError, AuthorizationError, NotFoundError, ValidationError
from app.schemas import (
    DetectRequest, DetectResponse, LanguageOut, TranslateRequest,
    TranslateResponse, TranslationOut,
)
from app.services import audit_service
from app.services.translation_service import TranslateContext, translate_text

log = logging.getLogger("app.routers.translate")

router = APIRouter(prefix="/api/v1", tags=["translation"])


def _ctx(principal: Principal | None, body: TranslateRequest, product: str = "text") -> TranslateContext:
    return TranslateContext(
        org_id=principal.org_id if principal else None,
        user_id=principal.user_id if principal else None,
        api_key_id=principal.api_key.id if (principal and principal.api_key) else None,
        glossary_id=body.glossary_id, style_profile_id=body.style_profile_id,
        tm_id=body.translation_memory_id, domain=body.domain,
        intent=body.intent, formality=body.formality, product=product)


@router.post("/translate", response_model=TranslateResponse)
async def translate(body: TranslateRequest,
                    principal: Principal | None = Depends(rl_translate),
                    db: AsyncSession = Depends(get_db)):
    if principal is None:
        raise AuthenticationError("Authentication required.")
    if principal.kind == "api_key" and principal.api_key is not None:
        scopes = principal.api_key.scopes or []
        if "translate" not in scopes and "*" not in scopes:
            raise AuthorizationError("API key lacks scope 'translate'.")
    principal.require("use_translate")
    texts = body.text if isinstance(body.text, list) else [body.text]
    if len(texts) > 1 and not body.batch:
        raise ValidationError("Multiple texts require batch=true.")
    # Cross-tenant validation: ensure referenced resources belong to caller's org
    if principal and principal.org_id:
        if body.style_profile_id:
            sp = await db.get(M.StyleProfile, body.style_profile_id)
            if not sp or sp.org_id != principal.org_id:
                raise NotFoundError("Style profile not found.")
        if body.glossary_id:
            gl = await db.get(M.Glossary, body.glossary_id)
            if not gl or gl.org_id != principal.org_id:
                raise NotFoundError("Glossary not found.")
        if body.translation_memory_id:
            tm = await db.get(M.TranslationMemory, body.translation_memory_id)
            if not tm or tm.org_id != principal.org_id:
                raise NotFoundError("Translation memory not found.")
    # quota pre-check on characters
    from app.services import usage_service
    if principal and principal.org_id:
        await usage_service.check_quota(
            db, principal.org_id, "characters", sum(len(t) for t in texts))
    ctx = _ctx(principal, body)
    outputs = []
    for text in texts:
        out = await translate_text(db, text, body.source_language,
                                   body.target_language, ctx)
        outputs.append(TranslationOut(
            translation_id=out.translation_id,
            source_language=out.result.source_lang,
            target_language=out.result.target_lang,
            source_text=text,
            translated_text=out.result.text,
            model=out.result.model,
            provider=out.result.provider,
            latency_ms=round(out.result.latency_ms, 1),
            quality_flags=out.result.quality_flags,
            tm_match=out.tm_match,
            domain=body.domain,
            alternatives=getattr(out.result, "alternatives", []),
        ))
    from app import context
    return TranslateResponse(translations=outputs,
                             request_id=context.current().request_id)


@router.post("/detect-language", response_model=DetectResponse)
async def detect_language(body: DetectRequest,
                          principal: Principal = Depends(rl_translate),
                          _scope=Depends(require_scope("detect")),
                          db: AsyncSession = Depends(get_db)):
    from app.ai import ai
    from app.services import usage_service
    det = await ai.detect_language(body.text)
    if principal.org_id:
        await usage_service.record_usage(
            db, org_id=principal.org_id, product="text",
            unit_type="api_requests", units=1, user_id=principal.user_id,
            api_key_id=principal.api_key.id if principal.api_key else None,
            metadata={"endpoint": "detect-language", "detected": det.language})
        await db.commit()
    return DetectResponse(language=det.language, confidence=round(det.confidence, 4),
                          alternatives=[(lang, round(c, 4)) for lang, c in det.alternatives],
                          provider=det.provider)


@router.get("/languages", response_model=list[LanguageOut])
async def languages(db: AsyncSession = Depends(get_db),
                    capability: str = Query(default="",
                                            description="filter: translation|speech_input|speech_output|realtime|document")):
    """Capability registry — the ONLY source for frontend language dropdowns.

    A language is exposed as supported only per its measured capability status
    (EXPERIMENTAL < BETA < SUPPORTED < PRODUCTION), never from model metadata.
    """
    res = await db.execute(select(M.LanguageCapability).order_by(
        M.LanguageCapability.name))
    rows = res.scalars().all()
    out = []
    for r in rows:
        item = LanguageOut(
            code=r.code, name=r.name, native_name=r.native_name, script=r.script,
            rtl=r.rtl,
            translation_supported=r.translation_status in ("SUPPORTED", "PRODUCTION"),
            speech_input_supported=r.speech_input_status in ("BETA", "SUPPORTED", "PRODUCTION"),
            speech_output_supported=r.speech_output_status in ("BETA", "SUPPORTED", "PRODUCTION"),
            realtime_supported=r.realtime_status in ("BETA", "SUPPORTED", "PRODUCTION"),
            document_supported=r.document_status in ("SUPPORTED", "PRODUCTION"),
            translation_status=r.translation_status,
            speech_input_status=r.speech_input_status,
            speech_output_status=r.speech_output_status,
            realtime_status=r.realtime_status,
            document_status=r.document_status,
            tts_voices=r.tts_voices or [],
        )
        if capability:
            keep = {
                "translation": item.translation_supported,
                "speech_input": item.speech_input_supported,
                "speech_output": item.speech_output_supported,
                "realtime": item.realtime_supported,
                "document": item.document_supported,
            }.get(capability, True)
            if not keep:
                continue
        out.append(item)
    return out


@router.get("/history", response_model=dict)
async def history(principal: Principal = Depends(rl_translate),
                  db: AsyncSession = Depends(get_db),
                  limit: int = Query(default=50, le=200),
                  offset: int = Query(default=0, ge=0),
                  product: str = Query(default=""),
                  target_lang: str = Query(default="")):
    q = select(M.TranslationSegment).where(
        M.TranslationSegment.org_id == principal.org_id,
        M.TranslationSegment.product.in_(["text", "chat"] if not product else [product]))
    if principal.kind == "user":
        q = q.where(M.TranslationSegment.created_by == principal.user_id)
    if target_lang:
        q = q.where(M.TranslationSegment.target_lang == target_lang)
    res = await db.execute(q.order_by(M.TranslationSegment.created_at.desc())
                           .limit(limit).offset(offset))
    rows = res.scalars().all()
    return {
        "items": [{
            "id": str(r.id), "product": r.product,
            "source_lang": r.source_lang, "target_lang": r.target_lang,
            "source_text": r.source_text[:1000], "target_text": r.target_text[:1000],
            "model": r.model, "provider": r.provider,
            "latency_ms": round(r.latency_ms, 1),
            "quality_flags": r.quality_flags_json,
            "tm_match": r.tm_match_type,
            "created_at": r.created_at.isoformat(),
        } for r in rows],
        "limit": limit, "offset": offset,
    }


@router.delete("/history", status_code=204)
async def clear_history(principal: Principal = Depends(rl_translate),
                        db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sa_delete
    q = sa_delete(M.TranslationSegment).where(
        M.TranslationSegment.org_id == principal.org_id,
        M.TranslationSegment.product.in_(["text", "chat"]),
        M.TranslationSegment.segment_id.is_(None))
    if principal.kind == "user":
        q = q.where(M.TranslationSegment.created_by == principal.user_id)
    await db.execute(q)
    await audit_service.record(db, action="history.cleared", org_id=principal.org_id,
                               actor_id=principal.user_id)
    await db.commit()


# ---- Local Whisper STT Endpoint ----
class VoiceTranscribeRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64 encoded 16-bit PCM audio")
    sample_rate: int = Field(default=16000, description="Audio sample rate in Hz")
    language: str | None = Field(default=None, description="Optional language code")

class VoiceTranscribeResponse(BaseModel):
    text: str
    language: str

_whisper_lock = asyncio.Lock()
_whisper_instance = None

def _get_whisper_model():
    global _whisper_instance
    if _whisper_instance is None:
        try:
            from faster_whisper import WhisperModel
            _whisper_instance = WhisperModel("tiny", device="cpu", compute_type="int8")
        except Exception:
            return None
    return _whisper_instance

@router.post("/voice/transcribe", response_model=VoiceTranscribeResponse)
async def voice_transcribe(body: VoiceTranscribeRequest):
    import base64
    import numpy as np
    try:
        raw_bytes = base64.b64decode(body.audio_base64)
    except Exception as e:
        raise ValidationError(f"Invalid base64 audio data: {e}")

    if not raw_bytes or len(raw_bytes) < 320: # less than 10ms of audio
        return VoiceTranscribeResponse(text="", language=body.language or "en")

    try:
        pcm = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if body.sample_rate != 16000 and len(pcm) > 0:
            n_out = int(len(pcm) * 16000 / body.sample_rate)
            x_old = np.linspace(0, 1, len(pcm))
            x_new = np.linspace(0, 1, n_out)
            pcm = np.interp(x_new, x_old, pcm).astype(np.float32)

        async with _whisper_lock:
            try:
                model = await asyncio.to_thread(_get_whisper_model)
                if model is None:
                    raise RuntimeError("faster_whisper is not installed or available")
                lang = body.language if body.language and body.language != "auto" else None
                
                def _run():
                    segments, info = model.transcribe(pcm, language=lang, beam_size=1)
                    texts = [seg.text for seg in segments]
                    return "".join(texts).strip(), (info.language if info else None)

                text, detected_lang = await asyncio.to_thread(_run)
                return VoiceTranscribeResponse(text=text, language=detected_lang or body.language or "en")
            except Exception as w_err:
                log.warning("Local faster-whisper unavailable (%s), trying AIFacade fallback", w_err)
                from app.ai import ai
                chunk, _decision = await ai.transcribe(raw_bytes, body.sample_rate, lang_hint=body.language)
                return VoiceTranscribeResponse(text=chunk.text or "", language=chunk.language or body.language or "en")
    except Exception as e:
        log.error("Voice transcription error: %s", e)
        return VoiceTranscribeResponse(text="", language=body.language or "en")


# ---- High-Fidelity Voice TTS Endpoint ----
class VoiceTtsRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize")
    language: str = Field(default="en", description="Target language code (e.g. en, hi, de, es, fr)")
    voice: str | None = Field(default=None, description="Optional voice name")

class VoiceTtsResponse(BaseModel):
    audio_base64: str
    format: str = "mp3"
    sample_rate: int = 24000

@router.post("/voice/tts", response_model=VoiceTtsResponse)
async def voice_tts(body: VoiceTtsRequest):
    import base64
    import io

    clean_text = body.text.strip()
    if not clean_text:
        return VoiceTtsResponse(audio_base64="", format="mp3", sample_rate=24000)

    # Normalize lang (e.g., "hi-IN" -> "hi", "de-DE" -> "de")
    lang = body.language.split("-")[0].lower() if body.language else "en"

    # Tier 1: Try natural neural gTTS (handles Hindi, German, Spanish, French, English, etc.)
    from app.config import settings
    if settings.app_env != "test":
        try:
            import gtts
            def _synth_gtts():
                tts_obj = gtts.gTTS(text=clean_text, lang=lang)
                buf = io.BytesIO()
                tts_obj.write_to_fp(buf)
                return buf.getvalue()

            mp3_bytes = await asyncio.wait_for(asyncio.to_thread(_synth_gtts), timeout=3.5)
            if mp3_bytes and len(mp3_bytes) > 100:
                b64 = base64.b64encode(mp3_bytes).decode("ascii")
                return VoiceTtsResponse(audio_base64=b64, format="mp3", sample_rate=24000)
        except Exception as g_err:
            log.warning("gTTS synthesis unavailable (%s), trying AIFacade", g_err)

    # Tier 2: AIFacade / local engine (Kokoro / Piper / tts_http)
    try:
        from app.ai import ai
        chunk, _decision = await ai.synthesize(clean_text, lang, voice=body.voice)
        audio_bytes = chunk.data
        fmt = chunk.format or "wav"
        if not audio_bytes.startswith(b"RIFF") and fmt == "wav":
            from gt_ai.audio_utils import pcm16_to_wav
            audio_bytes = pcm16_to_wav(audio_bytes, sample_rate=chunk.sample_rate)
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        return VoiceTtsResponse(audio_base64=b64, format=fmt, sample_rate=chunk.sample_rate)
    except Exception as ai_err:
        log.warning("AIFacade synthesis failed (%s), trying dev_tone", ai_err)

    # Tier 3: DevTone fallback
    try:
        from gt_ai.tts.dev_tone import DevToneProvider
        provider = DevToneProvider()
        chunk = await provider.synthesize(clean_text, lang, voice=body.voice)
        b64 = base64.b64encode(chunk.data).decode("ascii")
        return VoiceTtsResponse(audio_base64=b64, format="wav", sample_rate=chunk.sample_rate)
    except Exception as dev_err:
        log.error("All TTS options failed: %s", dev_err)
        return VoiceTtsResponse(audio_base64="", format="mp3", sample_rate=24000)

