"""Seed data (PDD §54): languages, feature flags, default style profiles,
model registry, test glossary, test organization + demo user.

Idempotent — safe to run repeatedly (`python -m app.seed`).
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.config import settings
from app.db.base import utcnow
from app.db import models as M
from app.db.session import db_session, init_db
from app.security import hash_password
from gt_ai.capabilities import DEFAULT_LANGUAGES, QualityStatus

log = logging.getLogger("app.seed")

STATUS_NAMES: dict[int, str] = {int(v.value): k for k, v in QualityStatus.__members__.items()}

DEFAULT_STYLE_PROFILES = [
    ("Formal", "formal", {"tone": "professional", "formality": "formal",
                          "punctuation": "standard", "domain": "general"}),
    ("Casual", "casual", {"tone": "friendly", "formality": "informal",
                          "punctuation": "relaxed", "domain": "general"}),
    ("Technical", "technical", {"tone": "precise", "formality": "neutral",
                                "domain": "tech", "keep_code_verbatim": True}),
    ("Legal", "legal", {"tone": "diplomatic", "formality": "formal",
                        "domain": "legal", "preserve_clause_ids": True}),
    ("Finance", "finance", {"tone": "professional", "formality": "formal",
                            "domain": "finance", "preserve_numbers_strict": True}),
    ("Customer Support", "support", {"tone": "friendly", "formality": "neutral",
                                     "domain": "support"}),
    ("Education", "education", {"tone": "clear", "formality": "neutral",
                                "domain": "education"}),
    ("Sales", "sales", {"tone": "persuasive", "formality": "neutral",
                        "domain": "sales"}),
]

FEATURE_FLAGS = {
    "voice_translation": settings.ff_voice_translation,
    "document_translation": settings.ff_document_translation,
    "agent_bridge": settings.ff_agent_bridge,
    "voice_preservation": settings.ff_voice_preservation,
    "new_translation_model": settings.ff_new_translation_model,
    "experimental_language": settings.ff_experimental_language,
    "enterprise_sso": settings.ff_enterprise_sso,
}

MODEL_REGISTRY_SEED = [
    # name, task, provider, quality, cost, latency_class, private, gpu
    ("neural-web-mt", "mt", "neural_online", 92, 0, "fast", False, False),
    ("deepl-v2", "mt", "deepl", 95, 20, "fast", False, False),
    ("madlad-400-3b", "mt", "madlad400", 85, 70, "fast", True, False),
    ("nllb-200-600m-ct2", "mt", "nllb_ct2", 78, 40, "fast", True, False),
    ("argos-packs", "mt", "argos", 60, 20, "fast", True, False),
    ("mt-http-service", "mt", "mt_http", 70, 30, "fast", True, False),
    ("dev-echo-v1", "mt", "dev_echo", 1, 0, "realtime", True, False),
    ("whisper-small", "stt", "faster_whisper", 88, 50, "realtime", True, False),
    ("whisper-large-v3", "stt", "faster_whisper", 95, 90, "realtime", True, True),
    ("stt-http-service", "stt", "stt_http", 75, 30, "realtime", True, False),
    ("dev-text-v1", "stt", "dev_text", 0, 0, "realtime", True, False),
    ("kokoro-v1.0", "tts", "kokoro", 88, 40, "fast", True, False),
    ("piper-voices", "tts", "piper", 70, 25, "fast", True, False),
    ("tts-http-service", "tts", "tts_http", 70, 30, "fast", True, False),
    ("dev-tone-v1", "tts", "dev_tone", 0, 0, "realtime", True, False),
    ("fasttext-lid176", "lang_detect", "fasttext", 88, 5, "realtime", True, False),
    ("langdetect-script", "lang_detect", "langdetect", 62, 0, "realtime", True, False),
    ("extractive-tfidf", "summarize", "extractive", 55, 0, "realtime", True, False),
    ("llm-http", "summarize", "llm_http", 85, 60, "batch", True, False),
    ("hash-tfidf-embed", "embed", "hash_tfidf", 40, 0, "realtime", True, False),
    ("multilingual-e5", "embed", "sentence_transformers", 85, 30, "fast", True, False),
]


async def seed_languages(db) -> int:
    n = 0
    for lc in DEFAULT_LANGUAGES:
        row = await db.get(M.LanguageCapability, lc.code)
        data = dict(
            name=lc.name, native_name=lc.native_name, script=lc.script, rtl=lc.rtl,
            translation_status=STATUS_NAMES[lc.translation_status],
            speech_input_status=STATUS_NAMES[lc.speech_input_status],
            speech_output_status=STATUS_NAMES[lc.speech_output_status],
            realtime_status=STATUS_NAMES[lc.realtime_status],
            document_status=STATUS_NAMES[lc.document_status],
            stt_provider=lc.stt_provider, mt_provider=lc.mt_provider,
            tts_provider=lc.tts_provider, tts_voices=lc.tts_voices,
            wer_benchmark=lc.wer_benchmark, mt_quality_score=lc.mt_quality_score,
            notes=lc.notes,
        )
        if row is None:
            db.add(M.LanguageCapability(code=lc.code, **data))
            n += 1
        else:
            for k, v in data.items():
                setattr(row, k, v)
    return n


async def seed_flags(db) -> int:
    n = 0
    for key, default in FEATURE_FLAGS.items():
        row = await db.get(M.FeatureFlag, key)
        if row is None:
            db.add(M.FeatureFlag(key=key, enabled_default=default,
                                 description=f"Controls {key}"))
            n += 1
    return n


async def seed_styles(db) -> int:
    n = 0
    for name, kind, config in DEFAULT_STYLE_PROFILES:
        res = await db.execute(select(M.StyleProfile).where(
            M.StyleProfile.org_id.is_(None), M.StyleProfile.kind == kind))
        if res.scalars().first() is None:
            db.add(M.StyleProfile(name=name, kind=kind, config_json=config,
                                  org_id=None, status="active"))
            n += 1
    return n


async def seed_model_registry(db) -> int:
    n = 0
    for name, task, provider, q, c, lat, private, gpu in MODEL_REGISTRY_SEED:
        res = await db.execute(select(M.ModelRegistry).where(
            M.ModelRegistry.name == name, M.ModelRegistry.task == task))
        if res.scalars().first() is None:
            db.add(M.ModelRegistry(
                name=name, task=task, provider=provider, quality_tier=q,
                cost_tier=c, latency_class=lat, private=private, requires_gpu=gpu,
                status="active",
                config_json={"model": name},
            ))
            n += 1
    return n


async def seed_demo_org(db) -> None:
    """Test organization + owner user + glossary (PDD §54)."""
    res = await db.execute(select(M.User).where(M.User.email == "demo@globaltalk.local"))
    user = res.scalars().first()
    if user is None:
        user = M.User(
            email="demo@globaltalk.local",
            password_hash=hash_password("demo1234"),
            name="Demo User",
            locale="en", speak_lang="en", hear_lang="en",
            email_verified=True, is_platform_admin=True,
        )
        db.add(user)
        await db.flush()
        log.info("seeded demo user demo@globaltalk.local / demo1234")

    res_admin = await db.execute(select(M.User).where(M.User.email == "admin@globaltalk.dev"))
    admin_user = res_admin.scalars().first()
    if admin_user is None:
        admin_user = M.User(
            email="admin@globaltalk.dev",
            password_hash=hash_password("Demo1234!"),
            name="GlobalTalk Admin",
            locale="en", speak_lang="en", hear_lang="en",
            email_verified=True, is_platform_admin=True,
        )
        db.add(admin_user)
        await db.flush()
        log.info("seeded admin user admin@globaltalk.dev / Demo1234!")

    res = await db.execute(select(M.Organization).where(M.Organization.slug == "demo-org"))
    org = res.scalars().first()
    if org is None:
        org = M.Organization(name="Demo Organization", slug="demo-org", plan="pro")
        db.add(org)
        await db.flush()
        db.add(M.OrganizationMember(org_id=org.id, user_id=user.id, role="owner"))
        db.add(M.Project(org_id=org.id, name="Default Project"))
        db.add(M.Subscription(org_id=org.id, plan_code="pro", status="active",
                              quota_json={"characters": 5_000_000, "audio_minutes": 1000,
                                          "documents": 200, "api_requests": 100_000}))
        await db.flush()
        log.info("seeded demo organization")

    res = await db.execute(select(M.Glossary).where(M.Glossary.org_id == org.id,
                                                    M.Glossary.name == "Demo Product Glossary"))
    glossary = res.scalars().first()
    if glossary is None:
        glossary = M.Glossary(org_id=org.id, name="Demo Product Glossary",
                              source_lang="en", target_lang="hi", status="active",
                              created_by=user.id,
                              description="Sample terms demonstrating glossary enforcement")
        db.add(glossary)
        await db.flush()
        demo_terms = [
            ("cloud console", "क्लाउड कंसोल", []),
            ("GlobalTalk AI", "GlobalTalk AI", ["global talk", "globaltalk"]),
            ("deployment pipeline", "डीप्लॉयमेंट पाइपलाइन", ["deploy pipeline"]),
            ("API key", "एपीआई की", []),
        ]
        for src, tgt, variants in demo_terms:
            db.add(M.GlossaryTerm(glossary_id=glossary.id, source_text=src,
                                  target_text=tgt, spoken_variants_json=variants))
        log.info("seeded demo glossary")


async def run_seed() -> None:
    await init_db()
    async with db_session() as db:
        langs = await seed_languages(db)
        flags = await seed_flags(db)
        styles = await seed_styles(db)
        models = await seed_model_registry(db)
        await seed_demo_org(db)
        await db.commit()
        log.info("seed complete: languages=%d flags=%d styles=%d models=%d",
                 langs, flags, styles, models)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_seed())


if __name__ == "__main__":
    main()
