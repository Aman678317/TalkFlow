"""Translation identity and provenance integrity validation."""
from __future__ import annotations

import hashlib
from typing import Optional
from app.core.exceptions import TranslationIdentityMismatchError


class IdentityValidator:
    """Verifies that synthesis requests retain immutable translation identity bindings."""

    @classmethod
    def validate_identity(
        cls,
        segment_id: Optional[str] = None,
        target_language: Optional[str] = None,
        text: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        translation_id: Optional[str] = None,
    ) -> str:
        """Verifies presence of identity keys and returns deterministic candidate hash."""
        if not segment_id or not segment_id.strip():
            raise TranslationIdentityMismatchError("Missing mandatory 'segment_id' in synthesis request.")

        if not target_language or not target_language.strip():
            raise TranslationIdentityMismatchError("Missing mandatory 'target_language' in synthesis request.")

        if text is not None and not text.strip():
            raise TranslationIdentityMismatchError("Synthesis request contains empty or whitespace-only text.")

        raw_key = f"{session_id or ''}:{segment_id}:{translation_id or ''}:{target_language.lower().strip()}:{text or ''}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


identity_validator = IdentityValidator()
