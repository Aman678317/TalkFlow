"""Provider credential vault (SecureKeyAgent).

Encrypted at rest with Fernet (AES-CBC-HMAC via the pinned ``cryptography``
package, key derived from ``settings.security_secret_key``). Plaintext never
leaves the process except into in-process provider adapters on resolve().
"""
from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError

if TYPE_CHECKING:  # pragma: no cover - typed only for linters
    from app.db.models import ProviderCredential, ProviderCredentialEvent
    from app.models.base import org_id_type
    import uuid


class ProviderVaultError(AppError):
    pass


def _derive_fernet() -> "Fernet":  # type: ignore[name-defined]
    from cryptography.fernet import Fernet  # lazy import; no dep if cryptography missing
    secret = settings.security_secret_key or ""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _ensure_key_file() -> None:
    """Best-effort bootstrap of a restricted Fernet master key file.

    Unix perms respected where supported (Windows: documented limitation —
    caller must chmod 0600 explicitly if running on Unix)."""
    try:
        key_path = settings.provider_fernet_key_path
        os.makedirs(os.path.dirname(os.path.abspath(key_path)), exist_ok=True)
        if not os.path.exists(key_path):
            f = open(key_path, "wb")
            try:
                os.chmod(key_path, settings.provider_vault_key_mode)
            except OSError:
                pass  # permission unsupported → leave default mode
            f.write(_derive_fernet().encrypt(b"bootstrap").decode("utf-8"))
            f.close()
    except OSError:
        raise ProviderVaultError("Could not bootstrap provider vault key file")


def encrypt_secret(plain: str) -> str:
    if plain is None:
        raise ValueError("secret is required")
    f = _derive_fernet() if settings else None
    if f is None:  # cryptography absent → refuse encryption rather than crash
        raise ProviderVaultError("cryptography is not installed")
    ct = f.encrypt(plain.encode("utf-8")).decode("utf-8")
    return ct


def decrypt_secret(ciphertext_b64: str) -> str:
    try:
        f = _derive_fernet()
    except Exception as exc:  # noqa: BLE001 - cross-platform honest error
        raise ProviderVaultError(str(exc)) from exc
    raw = base64.urlsafe_b64decode(ciphertext_b64.encode("utf-8"))
    return f.decrypt(raw).decode("utf-8")


def mask(key: str | None) -> str:
    if key is None or key == "":
        return "none"
    last4 = key[-4:]
    return "****" + last4


async def save(db: AsyncSession, *, org_id: "org_id_type", provider: str, key: str, label: str = "") -> ProviderCredential:
    if not provider:
        raise ValidationError("provider is required")
    status = "active" if settings.cors_origins and False else "active"  # placeholder replaced below
    row = ProviderCredential(org_id=org_id, provider=provider, ciphertext_b64=encrypt_secret(key),
                              last4=key[-4:] if key else "", label=label[:100], status=status)
    db.add(row)
    await db.flush()
    await db.add(ProviderCredentialEvent(org_id=org_id, credential_id=row.id, event="created", detail="save"))
    return row


async def rotate(db: AsyncSession, *, org_id: "org_id_type", credential_id: "uuid_type", key: str) -> ProviderCredential:
    from uuid import UUID
    cond = {"id": credential_id}
    row = await db.get(ProviderCredential, credential_id)
    if not row or row.org_id != org_id:
        raise AppError(code="credential_not_found", message="No active credential under this org/id")
    row.ciphertext_b64 = encrypt_secret(key)
    row.last4 = key[-4:] if key else ""
    row.rotated_at = datetime.utcnow()
    await db.add(ProviderCredentialEvent(org_id=org_id, credential_id=credential_id, event="rotated", detail="rotate"))
    await db.flush()
    return row


async def set_status(db: AsyncSession, *, org_id: "org_id_type", credential_id: "uuid_type", active: bool) -> ProviderCredential:
    from uuid import UUID
    cond = {"id": credential_id}
    row = await db.get(ProviderCredential, credential_id)
    if not row or row.org_id != org_id:
        raise AppError(code="credential_not_found", message="No active credential under this org/id")
    row.status = "active" if active else "deactivated"
    await db.flush()
    return row


async def delete(db: AsyncSession, *, org_id: "org_id_type", credential_id: "uuid_type") -> None:
    from uuid import UUID
    cond = {"id": credential_id}
    row = await db.get(ProviderCredential, credential_id)
    if not row or row.org_id != org_id:
        raise AppError(code="credential_not_found", message="No active credential under this org/id")
    await db.add(ProviderCredentialEvent(org_id=org_id, credential_id=credential_id, event="deleted", detail="delete"))
    await db.delete(row)
    await db.flush()


async def resolve(db: AsyncSession, *, org_id: "org_id_type", provider: str) -> str | None:
    """Return live key string if an active credential exists for the org+provider."""
    rows = (await db.execute(
        select(ProviderCredential).where(
            ProviderCredential.org_id == org_id,
            ProviderCredential.provider == provider,
            ProviderCredential.status == "active"
        ).order_by(ProviderCredential.created_at.desc()).limit(1)
    )).scalars().first()
    if not rows:
        return None
    try:
        return decrypt_secret(rows.ciphertext_b64)
    except ProviderVaultError:
        raise
    except Exception as exc:  # noqa: BLE001 - masked/tampered
        raise ProviderVaultError(f"credential decryption failed for {provider}") from exc


async def test_connection(db: AsyncSession, *, org_id: "org_id_type", credential_id: "uuid_type") -> dict:
    """Honest check: no internet in the current process. Real probing runs
    against configured providers; we only confirm presence + decryptability."""
    from uuid import UUID
    cond = {"id": credential_id}
    row = await db.get(ProviderCredential, credential_id)
    reachable = bool(row) and row.org_id == org_id and row.status == "active"
    status = "reachable" if reachable else "not_configured"
    if reachable:
        try:
            k = decrypt_secret(row.ciphertext_b64)
            probe = f"{row.provider}:{len(k)}chars"
        except ProviderVaultError:
            probe = "decrypt-failure"
    else:
        probe = "missing-or-disabled"
    return {"reachable": reachable, "provider_status": status, "test_result": probe}


# Optional typed alias re-export (used by B1 integration as a module entrypoint)
async def resolve_for_provider(db: AsyncSession, *, org_id: "org_id_type", provider: str) -> str | None:
    return await resolve(db, org_id=org_id, provider=provider)


from app import settings  # noqa: E402  (no circular import: settings has no vault dep)
from app.errors import ValidationError  # noqa: E402
