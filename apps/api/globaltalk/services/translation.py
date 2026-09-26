"""Translation service — the single business-logic path for ALL translation (text, realtime,
documents, chat). Order of operations (section 86):

Glossary → Translation Memory (exact → fuzzy/semantic) → Model Router → provider chain
→ post-processing (glossary enforcement) → metering → history.

Canonical-source rule: this service only ever translates FROM a canonical source text;
results are derivative artifacts carrying source references.
"""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ai.bootstrap import get_router
from ai.interfaces import ProviderUnavailable
from ai.model_router.router import RouteRequest
from ai.providers.embeddings import cosine
from globaltalk.core.errors import UpstreamAIError, ValidationError
from globaltalk.core.logging import get_logger
from globaltalk.core.metrics import metrics
from globaltalk.models import (Glossary, GlossaryTerm, StyleProfile, TranslationHistory,
                               TranslationMemory)

log = get_logger("translation")

MAX_TEXT_CHARS = 25_000
FUZZY_THRESHOLD = 0.82


@dataclass
class TranslateOptions:
    source_language: str = "AUTO"
    target_language: str = "en"
    glossary_id: str | None = None
    style_profile_id: str | None = None
    translation_memory_id: str | None = None   # TM namespace id (falls back to org default)
    domain: str = "general"
    intent: str = "quality_optimized"
    allow_pivot: bool = True


@dataclass
class TranslateOutcome:
    translation_id: str
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    model: str
    provider: str
    latency_ms: float
    quality_flags: list[str] = field(default_factory=list)
    from_tm: bool = False
    tm_confidence: float = 0.0
    detected_confidence: float = 0.0


def normalize_for_match(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[^\w\s]", "", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def tm_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_match(text).encode()).hexdigest()


# --------------------------------------------------------------------- glossary

def load_glossary(db: Session, glossary_id: str | None, org_id: str,
                  source: str, target: str) -> tuple[dict[str, str], str | None]:
    """Returns (source_term → target_term mapping, glossary version tag)."""
    if not glossary_id:
        return {}, None
    g = (db.query(Glossary).filter(Glossary.id == glossary_id, Glossary.org_id == org_id,
                                   Glossary.status == "active").first())
    if not g:
        return {}, None
    terms = db.query(GlossaryTerm).filter(GlossaryTerm.glossary_id == g.id).all()
    mapping: dict[str, str] = {}
    for t in terms:
        if t.do_not_translate:
            mapping[t.source_term] = t.source_term
        else:
            mapping[t.source_term] = t.target_term
    return mapping, f"{g.id}@v{g.version}"


def apply_glossary_post(text: str, mapping: dict[str, str], target_text: str) -> tuple[str, bool]:
    """Enforce glossary: substitute the mandated target term where the engine's output
    diverges for a known source term. Deterministic, case-aware, whole-word matching."""
    if not mapping:
        return target_text, False
    changed = False
    for src, tgt in mapping.items():
        if not tgt or tgt == src:
            continue
        # If the source term appears in the input and the engine produced a different casing /
        # left it untranslated in a detectable way, we cannot blindly rewrite arbitrary text —
        # we enforce only exact known variants (spoken variants + case differences).
        pattern = re.compile(r"(?<!\w)" + re.escape(src) + r"(?!\w)", re.IGNORECASE)
        if pattern.search(text):
            new_text, n = pattern.subn(tgt, target_text)
            if n and new_text != target_text:
                target_text, changed = new_text, True
    return target_text, changed


# --------------------------------------------------------------------- language detection

def detect_text_language(db: Session, text: str) -> tuple[str, float]:
    router = get_router()
    try:
        result, route = router.execute(
            RouteRequest(task="langid"), lambda p: p.detect(text))
        if result.language:
            return result.language, result.confidence
    except ProviderUnavailable:
        pass
    return "en", 0.0


# --------------------------------------------------------------------- translation memory

def tm_lookup(db: Session, org_id: str, source_text: str, source_lang: str, target_lang: str,
              namespace: str = "default", domain: str = "general") -> tuple[str, float] | None:
    """Exact match first; then fuzzy via embedding cosine over same-pair entries."""
    h = tm_hash(source_text)
    exact = (db.query(TranslationMemory)
             .filter(TranslationMemory.org_id == org_id,
                     TranslationMemory.source_norm_hash == h,
                     TranslationMemory.source_language == source_lang,
                     TranslationMemory.target_language == target_lang)
             .order_by(TranslationMemory.approved.desc(), TranslationMemory.usage_count.desc())
             .first())
    if exact:
        exact.usage_count += 1
        db.commit()
        return exact.target_text, 1.0
    # fuzzy: only worthwhile above a small corpus and for texts with enough signal
    if len(source_text.strip()) < 12:
        return None
    try:
        router = get_router()
        emb, _ = router.execute(RouteRequest(task="embedding"),
                                lambda p: p.embed([normalize_for_match(source_text)]))
        qvec = emb[0]
    except ProviderUnavailable:
        return None
    cands = (db.query(TranslationMemory)
             .filter(TranslationMemory.org_id == org_id,
                     TranslationMemory.source_language == source_lang,
                     TranslationMemory.target_language == target_lang,
                     TranslationMemory.embedding.isnot(None))
             .limit(500).all())
    best, best_sim = None, 0.0
    for c in cands:
        sim = cosine(qvec, c.embedding or [])
        if sim > best_sim:
            best, best_sim = c, sim
    if best and best_sim >= FUZZY_THRESHOLD:
        best.usage_count += 1
        db.commit()
        return best.target_text, round(best_sim, 4)
    return None


def tm_store(db: Session, org_id: str, source_text: str, target_text: str, source_lang: str,
             target_lang: str, *, domain: str = "general", approved: bool = False,
             created_by: str | None = None, namespace: str = "default",
             confidence: float = 1.0) -> TranslationMemory:
    router = get_router()
    emb = None
    try:
        res, _ = router.execute(RouteRequest(task="embedding"),
                                lambda p: p.embed([normalize_for_match(source_text)]))
        emb = res[0]
    except ProviderUnavailable:
        emb = None
    existing = (db.query(TranslationMemory)
                .filter(TranslationMemory.org_id == org_id,
                        TranslationMemory.source_norm_hash == tm_hash(source_text),
                        TranslationMemory.source_language == source_lang,
                        TranslationMemory.target_language == target_lang,
                        TranslationMemory.tm_namespace == namespace)
                .first())
    if existing:
        existing.target_text = target_text
        existing.version += 1
        existing.confidence = confidence
        if emb:
            existing.embedding = emb
        db.commit()
        return existing
    row = TranslationMemory(
        org_id=org_id, tm_namespace=namespace, source_language=source_lang,
        target_language=target_lang, source_text=source_text, target_text=target_text,
        source_norm_hash=tm_hash(source_text), domain=domain, approved=approved,
        created_by=created_by, confidence=confidence, embedding=emb)
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------- style profiles

def load_style(db: Session, style_profile_id: str | None, org_id: str) -> tuple[str, str | None]:
    if not style_profile_id:
        return "", None
    sp = (db.query(StyleProfile)
          .filter(StyleProfile.id == style_profile_id,
                  (StyleProfile.org_id == org_id) | (StyleProfile.is_system.is_(True)))
          .first())
    if not sp:
        return "", None
    return sp.prompt_fragment or "", f"{sp.id}@v{sp.version}"


# --------------------------------------------------------------------- main entry point

def translate_text(db: Session, *, org_id: str, text: str, opts: TranslateOptions,
                   user_id: str | None = None, api_key_id: str | None = None,
                   persist_history: bool = True, kind: str = "text") -> TranslateOutcome:
    if not text or not text.strip():
        raise ValidationError("text must not be empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValidationError(f"text exceeds {MAX_TEXT_CHARS} characters; use /documents",
                              code="text_too_long")
    started = time.perf_counter()

    src = opts.source_language
    detected_conf = 0.0
    if not src or src.upper() == "AUTO":
        src, detected_conf = detect_text_language(db, text)
        if not src:
            src = "en"
    src = src.split("-")[0]
    tgt = opts.target_language.split("-")[0]
    if not tgt:
        raise ValidationError("target_language is required")

    quality_flags: list[str] = []
    if detected_conf and detected_conf < 0.5:
        quality_flags.append("low_language_detection_confidence")

    glossary_map, glossary_version = load_glossary(db, opts.glossary_id, org_id, src, tgt)
    style_hint, style_version = load_style(db, opts.style_profile_id, org_id)

    # 1) Translation memory (approved entries win; fuzzy above threshold)
    tm_hit = tm_lookup(db, org_id, text, src, tgt, domain=opts.domain)
    if tm_hit:
        tm_text, tm_conf = tm_hit
        outcome = TranslateOutcome(
            translation_id=hashlib.sha1(f"{text}{tm_text}{time.time_ns()}".encode()).hexdigest()[:24],
            source_language=src, target_language=tgt, source_text=text,
            translated_text=tm_text, model="translation-memory", provider="tm",
            latency_ms=(time.perf_counter() - started) * 1000,
            quality_flags=quality_flags + (["tm_fuzzy_match"] if tm_conf < 1.0 else ["tm_exact_match"]),
            from_tm=True, tm_confidence=tm_conf, detected_confidence=detected_conf)
        if persist_history:
            _persist(db, org_id, outcome, opts, user_id, api_key_id, kind)
        return outcome

    if src == tgt:
        outcome = TranslateOutcome(
            translation_id=hashlib.sha1(f"{text}{time.time_ns()}".encode()).hexdigest()[:24],
            source_language=src, target_language=tgt, source_text=text, translated_text=text,
            model="identity", provider="identity",
            latency_ms=(time.perf_counter() - started) * 1000,
            quality_flags=quality_flags + ["same_language"], detected_confidence=detected_conf)
        if persist_history:
            _persist(db, org_id, outcome, opts, user_id, api_key_id, kind)
        return outcome

    # 2) Model router → provider chain
    router = get_router()
    req = RouteRequest(task="mt", source_language=src, target_language=tgt,
                       domain=opts.domain, intent=opts.intent,
                       tenant_policy={"allow_pivot_translation": opts.allow_pivot})
    try:
        result, route = router.execute(
            req, lambda p: p.translate(text, src, tgt, glossary=glossary_map,
                                       domain=opts.domain, style_hint=style_hint))
    except ProviderUnavailable as exc:
        log.error("translation_all_providers_failed", extra={"reason": str(exc)})
        raise UpstreamAIError("All translation providers are unavailable",
                              code="translation_unavailable", recoverable=True,
                              details={"reason": str(exc)})

    translated = result.text
    quality_flags.extend(result.quality_flags)
    if glossary_map:
        translated, glossary_applied = apply_glossary_post(text, glossary_map, translated)
        if glossary_applied:
            quality_flags.append("glossary_enforced")

    # passthrough fallback: never pretend it's a translation
    if "untranslated_fallback" in quality_flags:
        log.warning("translation_degraded_passthrough", extra={"pair": f"{src}->{tgt}"})

    latency_ms = (time.perf_counter() - started) * 1000
    metrics.observe_translation(result.provider or route.provider_name, f"{src}-{tgt}",
                                result.latency_ms)

    outcome = TranslateOutcome(
        translation_id=hashlib.sha1(f"{text}{translated}{time.time_ns()}".encode()).hexdigest()[:24],
        source_language=src, target_language=tgt, source_text=text, translated_text=translated,
        model=result.model or route.provider_name, provider=result.provider or route.provider_name,
        latency_ms=latency_ms, quality_flags=quality_flags, detected_confidence=detected_conf)

    # 3) Feed successful MT output back into TM (learning loop, versioned)
    if "untranslated_fallback" not in quality_flags:
        try:
            tm_store(db, org_id, text, translated, src, tgt, domain=opts.domain,
                     created_by=user_id, confidence=max(result.confidence, 0.5))
        except Exception:
            log.exception("tm_store_failed")

    if persist_history:
        _persist(db, org_id, outcome, opts, user_id, api_key_id, kind)
    return outcome


def _persist(db: Session, org_id: str, o: TranslateOutcome, opts: TranslateOptions,
             user_id: str | None, api_key_id: str | None, kind: str) -> None:
    db.add(TranslationHistory(
        org_id=org_id, user_id=user_id, source_language=o.source_language,
        target_language=o.target_language, source_text=o.source_text,
        translated_text=o.translated_text, model=o.model, provider=o.provider,
        latency_ms=o.latency_ms, quality_flags=o.quality_flags, glossary_id=opts.glossary_id,
        style_profile_id=opts.style_profile_id, domain=opts.domain, intent=opts.intent,
        from_tm=o.from_tm, kind=kind))
    # metering: EVERY translation request is metered (TM hits and same-language included)
    from globaltalk.core.audit import meter
    meter(db, org_id=org_id, dimension="characters", quantity=len(o.source_text),
          user_id=user_id, api_key_id=api_key_id,
          metadata={"pair": f"{o.source_language}-{o.target_language}", "kind": kind,
                    "provider": o.provider, "from_tm": o.from_tm})
    meter(db, org_id=org_id, dimension="translation_requests", quantity=1,
          user_id=user_id, api_key_id=api_key_id,
          metadata={"pair": f"{o.source_language}-{o.target_language}", "kind": kind})
    db.commit()
