"""Seed data (section 54): languages, feature flags, system style profiles, model registry,
development org/user, test glossary. Idempotent — safe to run on every startup."""
from __future__ import annotations

from globaltalk.core.config import settings
from globaltalk.core.db import SessionLocal
from globaltalk.core.logging import get_logger

log = get_logger("seed")

SYSTEM_STYLES = [
    ("Formal", "formal",
     "Use formal register: complete sentences, honorific-neutral tone, no contractions, "
     "no slang. Preserve titles and courtesy forms appropriate to the target culture."),
    ("Casual", "casual",
     "Use a natural conversational register: contractions allowed, friendly tone, "
     "keep idioms natural in the target language rather than literal."),
    ("Technical", "technical",
     "Technical documentation register: precise terminology, keep product names, API "
     "identifiers, code, versions and units untranslated; prefer established target-language "
     "technical terms."),
    ("Legal", "legal",
     "Legal register: exact, conservative phrasing; preserve defined terms, clause "
     "references, numbering and capitalization of defined terms; never paraphrase obligations."),
    ("Finance", "finance",
     "Finance register: preserve currency codes, amounts, tickers, fiscal periods and "
     "accounting terminology exactly; use standard target-market financial terms."),
    ("Customer Support", "customer_support",
     "Support register: empathetic, clear, action-oriented; short sentences; keep ticket "
     "IDs, product names and steps intact."),
    ("Education", "education",
     "Educational register: clear explanations, define jargon on first use, keep examples "
     "and pedagogical structure intact."),
    ("Sales", "sales",
     "Sales register: persuasive but factual; keep value propositions crisp; localize "
     "units, currency and formality to the target market."),
]

MODEL_REGISTRY_SEED = [
    # task, provider, model_id, revision, languages, hardware, license, review, status, prio
    ("stt", "faster-whisper", "Systran/faster-whisper-small", "pinned-small-int8",
     ["multilingual-99"], "cpu", "MIT", "REVIEWED", "SUPPORTED", 10),
    ("stt", "faster-whisper", "Systran/faster-whisper-large-v3", "pinned-large-v3",
     ["multilingual-99"], "gpu", "MIT", "REVIEWED", "BETA", 20),
    ("stt", "indicconformer", "ai4bharat/indic-conformer-600m-multilingual", "pinned-600m",
     ["hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur"], "gpu",
     "CC-BY-SA (check per release)", "PENDING", "EXPERIMENTAL", 5),
    ("mt", "argos", "argos-translate NLLB packages", "per-package-index",
     ["installed-pairs-only"], "cpu", "MIT (models: per-package)", "REVIEWED", "SUPPORTED", 10),
    ("mt", "seamless", "facebook/seamless-m4t-v2-large", "pinned-research",
     ["~100"], "gpu", "CC-BY-NC 4.0 (NON-COMMERCIAL)", "REVIEWED-BLOCKED", "EXPERIMENTAL", 90),
    ("tts", "kokoro", "hexgrad/kokoro-82M (onnx v1.0)", "pinned-v1.0",
     ["en", "ja", "zh", "es", "fr"], "cpu", "Apache-2.0", "REVIEWED", "SUPPORTED", 10),
    ("tts", "indic-parler", "ai4bharat/indic-parler-tts", "pinned-mini",
     ["hi", "bn", "gu", "kn", "ml", "mr", "or", "pa", "ta", "te"], "gpu",
     "check model card", "PENDING", "EXPERIMENTAL", 20),
    ("vad", "silero", "snakers4/silero-vad", "pinned-v5", ["language-agnostic"], "cpu",
     "MIT (model: CC-BY-NC — review!)", "PENDING", "EXPERIMENTAL", 20),
    ("vad", "energy", "internal-energy-vad", "1.0", ["language-agnostic"], "cpu",
     "Internal", "REVIEWED", "SUPPORTED", 10),
    ("llm", "vllm", "configurable open model", "pinned-by-deployment", ["multilingual"],
     "gpu", "per-model", "PENDING", "EXPERIMENTAL", 10),
    ("llm", "extractive", "internal-extractive-assistant", "1.0", ["language-agnostic"],
     "cpu", "Internal", "REVIEWED", "SUPPORTED", 100),
    ("embedding", "hash", "internal-hash-ngram-256", "1.0", ["language-agnostic"], "cpu",
     "Internal", "REVIEWED", "SUPPORTED", 100),
]


def seed_all() -> None:
    db = SessionLocal()
    try:
        from globaltalk.models import (FeatureFlag, Glossary, GlossaryTerm, ModelRegistry,
                                       StyleProfile)
        from globaltalk.core.flags import DEFAULT_FLAGS
        from globaltalk.services.capabilities import seed_registry

        seed_registry(db)

        for name, meta in DEFAULT_FLAGS.items():
            exists = (db.query(FeatureFlag).filter(FeatureFlag.name == name,
                                                   FeatureFlag.org_id.is_(None)).first())
            if not exists:
                db.add(FeatureFlag(name=name, org_id=None,
                                   enabled=meta["default_enabled"],
                                   description=meta["description"]))

        for name, kind, prompt in SYSTEM_STYLES:
            if not db.query(StyleProfile).filter(StyleProfile.name == name,
                                                 StyleProfile.is_system.is_(True)).first():
                db.add(StyleProfile(name=name, kind=kind, is_system=True,
                                    prompt_fragment=prompt,
                                    rules={"versioned": True}))

        for (task, provider, model_id, revision, langs, hw, lic, review, status,
             prio) in MODEL_REGISTRY_SEED:
            if not (db.query(ModelRegistry)
                    .filter(ModelRegistry.task == task, ModelRegistry.provider == provider,
                            ModelRegistry.model_id == model_id).first()):
                db.add(ModelRegistry(task=task, provider=provider, model_id=model_id,
                                     revision=revision, languages=langs, hardware=hw,
                                     license=lic, license_review_status=review,
                                     production_status=status, priority=prio,
                                     gpu_required=(hw == "gpu")))

        if settings.app_env in ("development", "test"):
            _seed_dev_org(db)
        db.commit()
        log.info("seed_complete")
    except Exception:
        db.rollback()
        log.exception("seed_failed")
    finally:
        db.close()


def _seed_dev_org(db) -> None:
    from globaltalk.core.security import hash_password
    from globaltalk.models import (Glossary, GlossaryTerm, Organization, OrganizationMember,
                                   Subscription, User)
    from datetime import datetime, timezone

    email = "admin@globaltalk.dev"
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, password_hash=hash_password("Demo1234!"),
                    full_name="Dev Admin", is_platform_admin=True, email_verified=True)
        db.add(user)
        db.flush()
        org = Organization(name="GlobalTalk Demo", slug="globaltalk-demo", plan="pro")
        db.add(org)
        db.flush()
        db.add(OrganizationMember(org_id=org.id, user_id=user.id, role="owner"))
        db.add(Subscription(org_id=org.id, plan="pro", status="active",
                            current_period_start=datetime.now(timezone.utc)))
        g = Glossary(org_id=org.id, name="Platform Terms (demo)", source_language="en",
                     target_language="hi", domain="technology", status="active",
                     description="Seeded test glossary")
        db.add(g)
        db.flush()
        for src, tgt in [("cloud console", "क्लाउड कंसोल"),
                         ("API key", "API कुंजी"),
                         ("realtime translation", "रीयलटाइम अनुवाद")]:
            db.add(GlossaryTerm(glossary_id=g.id, source_term=src, source_lower=src.lower(),
                                target_term=tgt, spoken_variants=[]))
        db.flush()
        log.info("seed_dev_org", extra={"org": org.id})
