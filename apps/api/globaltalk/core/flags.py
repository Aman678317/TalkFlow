"""Feature flags: DB-backed with env-var overrides, tenant-scoped evaluation."""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

DEFAULT_FLAGS: dict[str, dict[str, Any]] = {
    "voice_translation": {"default_enabled": True, "description": "Realtime voice translation pipeline"},
    "document_translation": {"default_enabled": True, "description": "Document translation pipeline"},
    "agent_bridge": {"default_enabled": False, "description": "Agent-to-agent language bridge"},
    "voice_preservation": {"default_enabled": False, "description": "Voice cloning/preservation (consent-gated)"},
    "new_translation_model": {"default_enabled": False, "description": "Route to candidate MT model"},
    "experimental_language": {"default_enabled": False, "description": "Expose EXPERIMENTAL languages"},
    "enterprise_sso": {"default_enabled": False, "description": "OIDC/SAML SSO"},
    "audio_enhancement": {"default_enabled": False, "description": "DeepFilterNet-style denoising pre-STT"},
    "speech_separation": {"default_enabled": False, "description": "Overlap separation (Asteroid)"},
    "speaker_diarization": {"default_enabled": False, "description": "pyannote-style diarization"},
    "seamless_research": {"default_enabled": False, "description": "Seamless experimental S2ST research route"},
}


def flag_enabled(db: Session | None, name: str, org_id: str | None = None) -> bool:
    env = os.environ.get(f"FEATURE_{name.upper()}")
    if env is not None:
        return env.lower() in ("1", "true", "yes")
    if db is not None:
        from sqlalchemy import or_

        from globaltalk.models import FeatureFlag
        conds = [FeatureFlag.name == name, FeatureFlag.org_id.is_(None)]
        if org_id is not None:
            conds = [FeatureFlag.name == name,
                     or_(FeatureFlag.org_id.is_(None), FeatureFlag.org_id == org_id)]
        # org-specific overrides win over the global default row
        row = (db.query(FeatureFlag).filter(*conds)
               .order_by(FeatureFlag.org_id.isnot(None).desc()).first())
        if row is not None:
            return row.enabled
    return DEFAULT_FLAGS.get(name, {}).get("default_enabled", False)
