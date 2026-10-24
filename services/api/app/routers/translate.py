"""Translation API (PDD §14): /translate (single + batch), /detect-language,
/history, /languages capability registry.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.session import db_session, get_db
from app.deps import Principal, require_permission, require_scope, rl_translate, rl_translate_stream
from app.errors import (
    AppError, AuthenticationError, AuthorizationError, NotFoundError,
    ProviderError, UnsupportedLanguageError, ValidationError,
)
from app.schemas import (
    DetectRequest, DetectResponse, LanguageOut, PageTranslateRequest,
    PageTranslateResponse, TranslateRequest, TranslateResponse,
    TranslateStreamRequest, TranslationOut,
)
from app.services import audit_service
from gt_ai.translation.nllb_languages import normalize_lang
from gt_ai.types import Intent
from app.services.page_fetch import PageFetchError, fetch_page
from app.services.translation_service import (
    TranslateContext, split_stable_prefix, translate_text, validate_pair,
)

log = logging.getLogger("app.routers.translate")

router = APIRouter(prefix="/api/v1", tags=["translation"])

# Beyond this length a "no stable prefix yet" full-text draft would re-decode
# the tail twice per edit on the CPU model, so it only covers the
# typing-your-first-sentence window; long documents always have a stable
# prefix for split_stable_prefix to draft.
_FULL_DRAFT_MAX_CHARS = 400


def _ctx(principal: Principal | None, body: TranslateRequest, product: str = "text") -> TranslateContext:
    return TranslateContext(
        org_id=principal.org_id if principal else None,
        user_id=principal.user_id if principal else None,
        api_key_id=principal.api_key.id if (principal and principal.api_key) else None,
        glossary_id=body.glossary_id, style_profile_id=body.style_profile_id,
        tm_id=body.translation_memory_id, domain=body.domain,
        intent=body.intent, formality=body.formality, product=product)


async def _authorize_translate(principal: Principal | None, body: TranslateRequest,
                               db: AsyncSession, texts: list[str]) -> None:
    """Shared auth/scope/quota/resource checks for /translate and its stream."""
    if principal is None:
        if body.glossary_id or body.style_profile_id or body.translation_memory_id:
            raise AuthenticationError("Authentication required for custom glossaries, styles, and memory.")
        if len(texts) > 1 and not body.batch:
            raise ValidationError("Multiple texts require batch=true.")
        return
    if principal.kind == "api_key" and principal.api_key is not None:
        scopes = principal.api_key.scopes or []
        if "translate" not in scopes and "*" not in scopes:
            raise AuthorizationError("API key lacks scope 'translate'.")
    principal.require("use_translate")
    if len(texts) > 1 and not body.batch:
        raise ValidationError("Multiple texts require batch=true.")
    # Cross-tenant validation: ensure referenced resources belong to caller's org
    if principal.org_id:
        if body.style_profile_id:
            sp = await db.get(M.StyleProfile, body.style_profile_id)
            # Global profiles (org_id NULL) are intentionally listable and usable by every org.
            if not sp or (sp.org_id is not None and sp.org_id != principal.org_id):
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
    if principal.org_id:
        await usage_service.check_quota(
            db, principal.org_id, "characters", sum(len(t) for t in texts))
        # the translation volume is metered as "translation_requests" — the
        # limit was never checked against it, so the request quota could not
        # trip (issue #109 class 4)
        await usage_service.check_quota(
            db, principal.org_id, "translation_requests", len(texts))


def _translation_out(body: TranslateRequest, text: str, out) -> TranslationOut:
    return TranslationOut(
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
        glossary_note=out.glossary_note,
    )


@router.post("/translate", response_model=TranslateResponse)
async def translate(body: TranslateRequest,
                    principal: Principal | None = Depends(rl_translate),
                    db: AsyncSession = Depends(get_db)):
    texts = body.text if isinstance(body.text, list) else [body.text]
    await _authorize_translate(principal, body, db, texts)
    ctx = _ctx(principal, body)
    outputs = []
    for text in texts:
        out = await translate_text(db, text, body.source_language,
                                   body.target_language, ctx)
        outputs.append(_translation_out(body, text, out))
    from app import context
    return TranslateResponse(translations=outputs,
                             request_id=context.current().request_id)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


async def _run_translation(text: str, source: str, target: str, ctx: TranslateContext):
    # Own session: FastAPI may tear down the request-scoped dependency before
    # a StreamingResponse generator finishes.
    async with db_session() as db:
        return await translate_text(db, text, source, target, ctx)


async def _translate_stream_events(request: Request, body: TranslateStreamRequest,
                                   ctx: TranslateContext, request_id: str):
    """SSE producer for live translation.

    Emits a fast provisional draft of the stable prefix, then the final
    translation produced by the normal pipeline (TM, glossary, QA, persist).
    Every provider call is cancelled when the client aborts, so superseded
    keystrokes do not occupy workers.
    """
    import dataclasses

    from app.ai import ai

    started = time.perf_counter()
    target = normalize_lang(body.target_language)
    resolved = normalize_lang(body.source_language or "AUTO") or "auto"
    confidence: float | None = None
    ttfd_ms: float | None = None
    draft_used = False

    def elapsed_ms() -> float:
        return round((time.perf_counter() - started) * 1000, 1)

    try:
        if resolved in ("auto", ""):
            yield _sse("meta", {
                "request_id": request_id,
                "source_language": resolved,
                "target_language": target,
                "detected_confidence": None,
                "phase": "detecting",
            })
            detection = await ai.detect_language(body.text)
            resolved = detection.language
            confidence = detection.confidence

        yield _sse("meta", {
            "request_id": request_id,
            "source_language": resolved,
            "target_language": target,
            "detected_confidence": confidence,
            "phase": "ready",
        })

        if resolved == target:
            raise UnsupportedLanguageError(
                "Detected source language equals the target language.",
                details={"detected": resolved}, recoverable=True)
        async with db_session() as check_db:
            await validate_pair(check_db, resolved, target)

        prefix, _tail = split_stable_prefix(body.text) if body.draft else ("", body.text)
        # A provisional pass only helps when it can beat the final pass: it
        # runs with the latency-optimized intent (nllb_ct2 decodes beam-1 for
        # that intent — at full quality the draft's own decode always lost the
        # race with the final pass and shipped nothing early, measured
        # 2026-10-24), never persists and never meters. ai.translate applies
        # tenant_private_only AFTER the context intent, so privacy routing is
        # unaffected. While the first sentence is still being typed there is
        # no stable prefix at all; a DeepL-style editor still shows something,
        # so the unrevised full text is drafted then too.
        draft_text = prefix
        if (body.draft and not draft_text
                and len(body.text) <= _FULL_DRAFT_MAX_CHARS):
            draft_text = body.text
        draft_ctx = dataclasses.replace(
            ctx, persist=False, meter=False, intent="latency_optimized")

        final_task = asyncio.create_task(
            _run_translation(body.text, resolved, target, ctx))
        draft_task = (
            asyncio.create_task(_run_translation(draft_text, resolved, target, draft_ctx))
            if draft_text else None
        )
        pending = {final_task} | ({draft_task} if draft_task is not None else set())

        try:
            while pending:
                if await request.is_disconnected():
                    return
                done, pending = await asyncio.wait(
                    pending, timeout=10, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    yield _sse("ping", {"elapsed_ms": elapsed_ms()})
                    continue

                if draft_task is not None and draft_task in done:
                    try:
                        draft_out = draft_task.result()
                    except Exception as exc:  # draft failure must not kill the final pass
                        log.debug("live translation draft failed: %s", exc)
                    else:
                        if final_task not in done:
                            draft_used = True
                            if ttfd_ms is None:
                                ttfd_ms = elapsed_ms()
                            yield _sse("draft", {
                                "request_id": request_id,
                                "text": draft_out.result.text,
                                "source_language": draft_out.result.source_lang,
                                "target_language": draft_out.result.target_lang,
                                "model": draft_out.result.model,
                                "provider": draft_out.result.provider,
                                "quality_flags": draft_out.result.quality_flags,
                                "latency_ms": round(draft_out.result.latency_ms, 1),
                                "elapsed_ms": elapsed_ms(),
                            })

                if final_task in done:
                    out = final_task.result()
                    final = _translation_out(body, body.text, out)
                    yield _sse("done", {
                        "request_id": request_id,
                        "translations": [final.model_dump(mode="json")],
                        "detected_confidence": confidence,
                        "ttfd_ms": ttfd_ms,
                        "total_ms": elapsed_ms(),
                        "draft_used": draft_used,
                    })
                    return
        finally:
            # Client aborts, superseded streams and exceptions must not leave
            # provider calls running past the request.
            for task in (final_task, draft_task):
                if task is not None and not task.done():
                    task.cancel()
            for task in (final_task, draft_task):
                if task is not None:
                    with contextlib.suppress(BaseException):
                        await task
    except asyncio.CancelledError:
        raise
    except AppError as exc:
        yield _sse("error", {
            "request_id": request_id,
            "code": exc.code,
            "message": exc.message,
            "recoverable": exc.recoverable,
            "details": exc.details,
        })
    except Exception as exc:
        log.exception("live translation failed: %s", exc)
        yield _sse("error", {
            "request_id": request_id,
            "code": "internal_error",
            "message": "Translation failed. Please retry.",
            "recoverable": True,
        })


@router.post("/translate/stream")
async def translate_stream(body: TranslateStreamRequest,
                           request: Request,
                           principal: Principal | None = Depends(rl_translate_stream),
                           db: AsyncSession = Depends(get_db)):
    """Live translation over Server-Sent Events.

    Mirrors DeepL's while-you-type contract: translate before the sentence is
    finished, revise the result as more text arrives, and never require a
    submit button. The client aborts on the next edit; only the final pass is
    persisted and metered.
    """
    await _authorize_translate(principal, body, db, [body.text])
    ctx = _ctx(principal, body)
    # Capture the id while the request middleware's context is still active:
    # a StreamingResponse body runs after that context may have unwound.
    from app import context as req_context
    request_id = req_context.current().request_id
    return StreamingResponse(
        _translate_stream_events(request, body, ctx, request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/translate/page", response_model=PageTranslateResponse)
async def translate_page(body: PageTranslateRequest,
                         principal: Principal | None = Depends(rl_translate),
                         db: AsyncSession = Depends(get_db)):
    """Translate the readable text of a public web page.

    The page is fetched server-side with strict guards (public addresses only,
    size cap, timeout, content-type check) — see `app.services.page_fetch`.
    The result is the **text** of the page, not a mirrored page: images,
    layout and scripts are not reproduced.
    """
    if principal is None:
        raise AuthenticationError("Authentication required.")
    if principal.kind == "api_key" and principal.api_key is not None:
        scopes = principal.api_key.scopes or []
        if "translate" not in scopes and "*" not in scopes:
            raise AuthorizationError("API key lacks scope 'translate'.")
    principal.require("use_translate")

    try:
        page = await fetch_page(body.url)
    except PageFetchError as exc:
        raise ValidationError(str(exc)) from exc

    if principal and principal.org_id:
        from app.services import usage_service
        await usage_service.check_quota(
            db, principal.org_id, "characters", len(page.text))
        await usage_service.check_quota(
            db, principal.org_id, "translation_requests", 1)

    ctx = _ctx(principal, body, product="page")
    out = await translate_text(db, page.text, body.source_language,
                               body.target_language, ctx)
    from app import context
    return PageTranslateResponse(
        url=page.url,
        final_url=page.final_url,
        title=page.title,
        source_text=page.text,
        translated_text=out.result.text,
        source_language=out.result.source_lang,
        target_language=out.result.target_lang,
        model=out.result.model,
        provider=out.result.provider,
        latency_ms=round(out.result.latency_ms, 1),
        quality_flags=out.result.quality_flags,
        truncated=page.truncated,
        glossary_note=out.glossary_note,
    )


@router.post("/detect-language", response_model=DetectResponse)
async def detect_language(body: DetectRequest,
                          principal: Principal = Depends(rl_translate),
                          _scope=Depends(require_scope("detect")),
                          db: AsyncSession = Depends(get_db)):
    from app.ai import ai
    from app.services import usage_service
    if principal.org_id:
        # the api-request limit was never checked against the dimension it is
        # metered in (issue #109 class 4)
        await usage_service.check_quota(db, principal.org_id, "api_requests", 1)
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

    Translation adds a second, tighter test: the status is the operator's
    policy, and a model has to be installed to serve it. `served_languages` is
    the union of what the runtime-ready MT providers decode on this machine, so
    a language the checkpoint cannot produce never reaches a dropdown — the
    picker shows what works, not what a paper claims.
    """
    from app.ai import ai
    from gt_ai.types import Task
    from gt_ai.translation.nllb_languages import PICKER_VARIANTS

    served = ai.served_languages(Task.MT)
    res = await db.execute(select(M.LanguageCapability).order_by(
        M.LanguageCapability.name))
    rows = res.scalars().all()
    out = []
    for r in rows:
        translatable = (r.translation_status in ("SUPPORTED", "PRODUCTION")
                        and (served is None or r.code in served))
        item = LanguageOut(
            code=r.code, name=r.name, native_name=r.native_name, script=r.script,
            rtl=r.rtl,
            translation_supported=translatable,
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

    # DeepL-style regional rows ("English (British)", "French (Canadian)", …).
    # They alias a served base language: the request resolves through
    # LOCALE_VARIANTS before a model sees it, and a variant is advertised only
    # while its base is served — the picker cannot out-promise the runtime.
    if not capability or capability == "translation":
        by_code = {i.code: i for i in out}
        for variant_code, base_code, display_name in PICKER_VARIANTS:
            base = by_code.get(base_code)
            if base is None or not base.translation_supported:
                continue
            out.append(LanguageOut(
                code=variant_code, name=display_name, native_name="",
                script=base.script, rtl=base.rtl,
                translation_supported=True,
                speech_input_supported=False,
                speech_output_supported=False,
                realtime_supported=False,
                document_supported=base.document_supported,
                translation_status=base.translation_status,
                speech_input_status="EXPERIMENTAL",
                speech_output_status="EXPERIMENTAL",
                realtime_status="EXPERIMENTAL",
                document_status=base.document_status,
                tts_voices=[],
            ))
        # Stable "DeepL order": base and its variants cluster alphabetically
        # (English, English (American), English (British), …).
        out.sort(key=(lambda i: i.name))
    return out


@router.get("/history", response_model=dict)
async def history(principal: Principal = Depends(rl_translate),
                  db: AsyncSession = Depends(get_db),
                  limit: int = Query(default=50, le=200),
                  offset: int = Query(default=0, ge=0),
                  product: str = Query(default=""),
                  target_lang: str = Query(default=""),
                  source_lang: str = Query(default=""),
                  q: str = Query(default="", max_length=200)):
    if principal is None or not principal.org_id:
        return {"items": [], "limit": limit, "offset": offset}
    q_stmt = select(M.TranslationSegment).where(
        M.TranslationSegment.org_id == principal.org_id,
        M.TranslationSegment.product.in_(["text", "chat"] if not product else [product]))
    if principal.kind == "user":
        q_stmt = q_stmt.where(M.TranslationSegment.created_by == principal.user_id)
    if target_lang:
        q_stmt = q_stmt.where(M.TranslationSegment.target_lang == target_lang)
    if source_lang:
        q_stmt = q_stmt.where(M.TranslationSegment.source_lang == source_lang)
    if q:
        # The history page's search box sends `q`; it used to be ignored.
        needle = f"%{q.strip()}%"
        q_stmt = q_stmt.where(
            M.TranslationSegment.source_text.ilike(needle)
            | M.TranslationSegment.target_text.ilike(needle))
    res = await db.execute(q_stmt.order_by(M.TranslationSegment.created_at.desc())
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


@router.delete("/history/{segment_id}", status_code=204)
async def delete_history_entry(segment_id: uuid.UUID,
                               principal: Principal = Depends(rl_translate),
                               db: AsyncSession = Depends(get_db)):
    """Delete one history row (the page had a per-row Delete that 404'd)."""
    if principal is None or not principal.org_id:
        raise AuthenticationError("Authentication required.")
    stmt = select(M.TranslationSegment).where(
        M.TranslationSegment.id == segment_id,
        M.TranslationSegment.org_id == principal.org_id)
    if principal.kind == "user":
        stmt = stmt.where(M.TranslationSegment.created_by == principal.user_id)
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise NotFoundError("History entry not found.")
    await db.delete(row)
    await db.commit()


@router.delete("/history", status_code=204)
async def clear_history(principal: Principal = Depends(rl_translate),
                        db: AsyncSession = Depends(get_db)):
    if principal is None or not principal.org_id:
        raise AuthenticationError("Authentication required.")
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
    # Private-only (issue #109 class 3): the local whisper tier is on-tenant,
    # but the AIFacade fallback may be a cloud provider — the private intent
    # keeps that fallback on private providers (or fails honestly).
    private_only: bool = Field(default=False, description="Route to private providers only")

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
            from gt_ai.translation import model_fetch
            from app.config import settings
            cache_root = str(settings.model_cache_path)  # same basis app/ai.py passes to the provider
            weights_cached = model_fetch.hf_artifact_cached(
                "Systran/faster-whisper-tiny", cache_root, ("model.bin",))
            if not (weights_cached or model_fetch.downloads_allowed()):
                return None  # caller falls back to the AIFacade chain; never download behind a request
            if not weights_cached:
                log.warning("voice transcribe: whisper-tiny not cached; downloading because an opt-in env allows it")
            _whisper_instance = WhisperModel("tiny", device="cpu", compute_type="int8",
                                             download_root=cache_root)
        except Exception:
            return None
    return _whisper_instance

@router.post(
    "/voice/transcribe",
    response_model=VoiceTranscribeResponse,
    dependencies=[Depends(rl_translate), Depends(require_permission("use_voice"))],
)
async def voice_transcribe(body: VoiceTranscribeRequest):
    import base64
    import numpy as np
    from app.config import settings
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
                intent = Intent.PRIVATE_ONLY if body.private_only else None
                chunk, decision = await ai.transcribe(raw_bytes, body.sample_rate,
                                                      lang_hint=body.language, intent=intent)
                if settings.is_production and (
                    getattr(chunk, "is_dev", False)
                    or str(getattr(decision, "provider", "")).startswith("dev_")
                ):
                    raise ProviderError(
                        "Speech recognition is unavailable. Try again later.",
                        details={"capability": "stt"},
                        recoverable=True,
                    )
                return VoiceTranscribeResponse(text=chunk.text or "", language=chunk.language or body.language or "en")
    except ProviderError:
        raise
    except Exception as e:
        log.error("Voice transcription error: %s", e)
        return VoiceTranscribeResponse(text="", language=body.language or "en")


# ---- High-Fidelity Voice TTS Endpoint ----
class VoiceTtsRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize")
    language: str = Field(default="en", description="Target language code (e.g. en, hi, de, es, fr)")
    voice: str | None = Field(default=None, description="Optional voice name")
    # Private-only (issue #109 class 3): the gTTS tier talks to Google's
    # service OUTSIDE the router, so a private request skips it and stays on
    # the on-tenant providers behind the private intent.
    private_only: bool = Field(default=False, description="Use on-tenant providers only")

class VoiceTtsResponse(BaseModel):
    audio_base64: str
    format: str = "mp3"
    sample_rate: int = 24000

@router.post(
    "/voice/tts",
    response_model=VoiceTtsResponse,
    dependencies=[Depends(rl_translate), Depends(require_permission("use_voice"))],
)
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
    if settings.app_env != "test" and not body.private_only:
        # gTTS is a third-party (Google) service outside the router — a
        # private-only request must not send the text there (issue #109
        # class 3).
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
        intent = Intent.PRIVATE_ONLY if body.private_only else None
        chunk, decision = await ai.synthesize(clean_text, lang, voice=body.voice, intent=intent)
        if settings.is_production and (
            getattr(chunk, "is_dev", False) or decision.provider.startswith("dev_")
        ):
            raise ProviderError(
                "Speech output is unavailable. Captions remain available.",
                details={"capability": "tts", "language": lang},
                recoverable=True,
            )
        audio_bytes = chunk.data
        fmt = chunk.format or "wav"
        if not audio_bytes.startswith(b"RIFF") and fmt == "wav":
            from gt_ai.audio_utils import pcm16_to_wav
            audio_bytes = pcm16_to_wav(audio_bytes, sample_rate=chunk.sample_rate)
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        return VoiceTtsResponse(audio_base64=b64, format=fmt, sample_rate=chunk.sample_rate)
    except Exception as ai_err:
        log.warning("AIFacade synthesis failed (%s), trying dev_tone", ai_err)

    # A generated development tone is useful for local pipeline tests, but it is
    # not translated speech and must never be presented as production audio.
    if not settings.is_production:
        try:
            from gt_ai.tts.dev_tone import DevToneProvider
            provider = DevToneProvider()
            chunk = await provider.synthesize(clean_text, lang, voice=body.voice)
            b64 = base64.b64encode(chunk.data).decode("ascii")
            return VoiceTtsResponse(audio_base64=b64, format="wav", sample_rate=chunk.sample_rate)
        except Exception as dev_err:
            log.warning("Development TTS tone unavailable: %s", dev_err)

    raise ProviderError(
        "Speech output is unavailable. Captions remain available.",
        details={"capability": "tts", "language": lang},
        recoverable=True,
    )

