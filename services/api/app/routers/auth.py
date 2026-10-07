"""Auth router (PDD §24): signup, login, refresh, logout, password reset,
email verification, session/device management. OIDC/SAML/MFA-ready schema.
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache
from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import get_db
from app.deps import Principal, client_ip_hash, get_principal, rl_auth
from app.errors import AuthenticationError, AuthorizationError, NotFoundError, ValidationError
from app.schemas import (
    ChangePasswordRequest, LoginRequest, OrganizationOut, RefreshRequest,
    SessionOut, SignupRequest, SocialLoginRequest, TokenPair, UpdateProfileRequest,
    UserIdentityOut, UserOut,
)
from app.security import (
    create_token, decode_token, hash_password, password_policy_ok,
    verify_password,
)
from app.services import audit_service, billing_service
from app.services.social_auth_service import social_auth_service

log = logging.getLogger("app.routers.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/api/v1/auth",
        max_age=settings.jwt_refresh_ttl_days * 86400,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
    )


def _set_csrf_cookie(response: Response, csrf_token: str | None = None) -> None:
    if not csrf_token:
        csrf_token = secrets.token_hex(32)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
        max_age=settings.jwt_refresh_ttl_days * 86400,
    )


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    return slug or f"org-{secrets.token_hex(3)}"


async def _issue_tokens(db: AsyncSession, user: M.User, request: Request,
                        org_id: uuid.UUID | None,
                        session_id: uuid.UUID | None = None) -> TokenPair:
    access, _ = create_token(str(user.id), "access",
                             extra={"org_id": str(org_id) if org_id else None})
    refresh, jti = create_token(str(user.id), "refresh",
                                extra={"org_id": str(org_id) if org_id else None})
    # session + refresh-token rows (device tracking)
    device = request.headers.get("user-agent", "")[:300]
    session = None
    if session_id:
        session = await db.get(M.Session, session_id)
    if session:
        session.last_seen_at = utcnow()
        session.device_info = device
        session.ip_hash = client_ip_hash(request)
    else:
        session = M.Session(user_id=user.id, device_info=device,
                            ip_hash=client_ip_hash(request),
                            last_seen_at=utcnow(),
                            expires_at=utcnow() + timedelta(days=settings.jwt_refresh_ttl_days))
        db.add(session)
        await db.flush()
    from app.security import hash_api_key
    db.add(M.RefreshToken(user_id=user.id, session_id=session.id, jti=jti,
                          token_hash=hash_api_key(refresh),
                          expires_at=utcnow() + timedelta(days=settings.jwt_refresh_ttl_days)))
    await db.commit()
    return TokenPair(access_token=access, refresh_token=refresh,
                     expires_in=settings.jwt_access_ttl_minutes * 60)


@router.post("/signup", response_model=dict, status_code=201,
             dependencies=[Depends(rl_auth)])
async def signup(body: SignupRequest, request: Request, response: Response,
                 db: AsyncSession = Depends(get_db)):
    ok, msg = password_policy_ok(body.password)
    if not ok:
        raise ValidationError(msg)
    existing = (await db.execute(select(M.User).where(
        M.User.email == body.email.lower()))).scalars().first()
    if existing:
        # do not leak which emails are registered
        raise ValidationError("Signup failed. Check your details or reset your password.")
    user = M.User(
        email=body.email.lower(), password_hash=hash_password(body.password),
        name=body.name or body.email.split("@")[0], locale=body.locale,
        speak_lang=body.locale.split("-")[0], hear_lang=body.locale.split("-")[0],
    )
    db.add(user)
    await db.flush()

    org = None
    if body.organization_name:
        slug = _slugify(body.organization_name)
        base_slug = slug
        i = 2
        while (await db.execute(select(M.Organization).where(
                M.Organization.slug == slug))).scalars().first():
            slug = f"{base_slug}-{i}"
            i += 1
        org = M.Organization(name=body.organization_name, slug=slug, plan="free")
        db.add(org)
        await db.flush()
        db.add(M.OrganizationMember(org_id=org.id, user_id=user.id, role="owner"))
        db.add(M.Project(org_id=org.id, name="Default Project"))
    await db.commit()
    if org:
        await billing_service.get_or_create_subscription(db, org)

    # email verification token (delivered via email adapter; dev: cached+logged)
    verify_token = secrets.token_urlsafe(24)
    await cache().set(f"verify:{verify_token}", str(user.id), ttl_s=86400)
    log.info("email verification link (dev): /api/v1/auth/verify-email?token=%s",
             verify_token)

    tokens = await _issue_tokens(db, user, request, org.id if org else None)
    _set_refresh_cookie(response, tokens.refresh_token)
    _set_csrf_cookie(response)
    await audit_service.record(db, action="auth.signup", actor_id=user.id,
                               org_id=org.id if org else None,
                               ip_hash=client_ip_hash(request))
    await db.commit()
    return {"user": UserOut.model_validate(user),
            "organization": OrganizationOut.model_validate(org) if org else None,
            "tokens": tokens,
            "verification": {"pending": True,
                             "dev_link": f"/api/v1/auth/verify-email?token={verify_token}"}}


@router.post("/login", response_model=dict, dependencies=[Depends(rl_auth)])
async def login(body: LoginRequest, request: Request, response: Response,
                db: AsyncSession = Depends(get_db)):
    email_clean = body.email.lower().strip()
    user = (await db.execute(select(M.User).where(
        M.User.email == email_clean))).scalars().first()

    if user is None or not verify_password(body.password, user.password_hash):
        await audit_service.record(db, action="auth.login_failed",
                                   actor_id=user.id if user else None,
                                   outcome="failure",
                                   ip_hash=client_ip_hash(request),
                                   details={"email": email_clean})
        await db.commit()
        raise AuthenticationError("Invalid email or password.")
    if user.status != "active":
        raise AuthenticationError("Account is not active.")
    if body.org_id:
        try:
            requested_org = uuid.UUID(body.org_id)
        except ValueError:
            raise ValidationError("Invalid org_id.")
        member = (await db.execute(select(M.OrganizationMember).where(
            M.OrganizationMember.user_id == user.id,
            M.OrganizationMember.org_id == requested_org,
            M.OrganizationMember.status == "active"))).scalars().first()
        if member is None:
            raise AuthorizationError("You are not a member of the requested organization.")
        org_id = requested_org
    else:
        member = (await db.execute(select(M.OrganizationMember).where(
            M.OrganizationMember.user_id == user.id,
            M.OrganizationMember.status == "active")
            .order_by(M.OrganizationMember.created_at))).scalars().first()
        org_id = member.org_id if member else None
    user.last_login_at = utcnow()
    tokens = await _issue_tokens(db, user, request, org_id)
    _set_refresh_cookie(response, tokens.refresh_token)
    _set_csrf_cookie(response)
    await audit_service.record(db, action="auth.login", actor_id=user.id,
                               org_id=org_id, ip_hash=client_ip_hash(request))
    await db.commit()
    return {"user": UserOut.model_validate(user), "tokens": tokens,
            "org_id": str(org_id) if org_id else None}


@router.post("/social-login", response_model=dict, dependencies=[Depends(rl_auth)])
async def social_login(body: SocialLoginRequest, request: Request, response: Response,
                       db: AsyncSession = Depends(get_db)):
    provider = body.provider.lower().strip()
    if provider not in ("google", "github", "apple"):
        raise ValidationError(f"Unsupported social provider: {provider}")

    # 1. Cryptographically verify provider token / authorization code
    verified = await social_auth_service.verify_identity(
        provider=provider,
        token=body.token,
        code=body.code,
        redirect_uri=body.redirect_uri,
    )

    # 2. Check if this exact provider identity already exists in user_identities
    identity = (await db.execute(select(M.UserIdentity).where(
        M.UserIdentity.provider == provider,
        M.UserIdentity.provider_user_id == verified.provider_user_id,
    ))).scalars().first()

    if identity:
        # Existing identity found - retrieve linked user
        user = (await db.execute(select(M.User).where(M.User.id == identity.user_id))).scalars().first()
        if not user:
            raise AuthenticationError("Linked user account not found.")
        if user.status != "active":
            raise AuthenticationError("Account is not active.")

        # Update identity metadata if provider info changed
        identity.email = verified.email
        identity.email_verified = verified.email_verified
        identity.profile_data = verified.raw_claims
        if not user.email_verified and verified.email_verified:
            user.email_verified = True
    else:
        # 3. Identity not yet linked. Look up if user exists with this verified email
        clean_email = verified.email.lower().strip()
        user = (await db.execute(select(M.User).where(M.User.email == clean_email))).scalars().first()

        if user:
            # ACCOUNT TAKEOVER PROTECTION:
            # We ONLY link to an existing user account if the provider asserts email_verified is TRUE!
            if not verified.email_verified:
                raise AuthenticationError(
                    "Cannot link social account: identity provider has not verified this email address."
                )
            if user.status != "active":
                raise AuthenticationError("Account is not active.")

            if not user.email_verified and verified.email_verified:
                user.email_verified = True

            identity = M.UserIdentity(
                user_id=user.id,
                provider=provider,
                provider_user_id=verified.provider_user_id,
                email=clean_email,
                email_verified=verified.email_verified,
                profile_data=verified.raw_claims,
            )
            db.add(identity)
        else:
            # 4. User does not exist - provision new user
            display_name = verified.name or clean_email.split("@")[0]
            random_pw = secrets.token_urlsafe(32)
            user = M.User(
                email=clean_email,
                password_hash=hash_password(random_pw),
                name=display_name,
                locale="en",
                speak_lang="en",
                hear_lang="en",
                email_verified=verified.email_verified,
                is_platform_admin=False,
            )
            db.add(user)
            await db.flush()

            demo_org = (await db.execute(select(M.Organization).where(
                M.Organization.slug == "demo-org"))).scalars().first()
            if demo_org:
                db.add(M.OrganizationMember(org_id=demo_org.id, user_id=user.id, role="member"))
                await db.flush()
            else:
                org_slug = _slugify(f"{display_name}-workspace")
                new_org = M.Organization(name=f"{display_name}'s Workspace", slug=org_slug, plan="free")
                db.add(new_org)
                await db.flush()
                db.add(M.OrganizationMember(org_id=new_org.id, user_id=user.id, role="owner"))
                await db.flush()

            identity = M.UserIdentity(
                user_id=user.id,
                provider=provider,
                provider_user_id=verified.provider_user_id,
                email=clean_email,
                email_verified=verified.email_verified,
                profile_data=verified.raw_claims,
            )
            db.add(identity)

    # 5. Determine active organization
    member = (await db.execute(select(M.OrganizationMember).where(
        M.OrganizationMember.user_id == user.id,
        M.OrganizationMember.status == "active")
        .order_by(M.OrganizationMember.created_at))).scalars().first()
    org_id = member.org_id if member else None

    user.last_login_at = utcnow()
    tokens = await _issue_tokens(db, user, request, org_id)
    _set_refresh_cookie(response, tokens.refresh_token)
    _set_csrf_cookie(response)

    await audit_service.record(
        db,
        action="auth.social_login",
        actor_id=user.id,
        org_id=org_id,
        ip_hash=client_ip_hash(request),
        details={"provider": provider, "provider_sub": verified.provider_user_id, "email": verified.email},
    )
    await db.commit()
    return {
        "user": UserOut.model_validate(user),
        "tokens": tokens,
        "org_id": str(org_id) if org_id else None,
        "provider": provider,
    }


@router.get("/me/identities", response_model=list[UserIdentityOut])
async def list_identities(principal: Principal = Depends(get_principal),
                          db: AsyncSession = Depends(get_db)):
    if principal.kind != "user" or not principal.user_id:
        raise AuthenticationError("User authentication required.")
    res = await db.execute(select(M.UserIdentity).where(M.UserIdentity.user_id == principal.user_id))
    return [UserIdentityOut.model_validate(i) for i in res.scalars().all()]


@router.delete("/me/identities/{provider}", status_code=204)
async def unlink_identity(provider: str,
                          principal: Principal = Depends(get_principal),
                          db: AsyncSession = Depends(get_db)):
    if principal.kind != "user" or not principal.user_id:
        raise AuthenticationError("User authentication required.")
    provider = provider.lower().strip()
    identity = (await db.execute(select(M.UserIdentity).where(
        M.UserIdentity.user_id == principal.user_id,
        M.UserIdentity.provider == provider,
    ))).scalars().first()
    if not identity:
        raise NotFoundError("Identity not linked.")
    await db.delete(identity)
    await audit_service.record(db, action="auth.identity_unlinked", actor_id=principal.user_id,
                               org_id=principal.org_id, details={"provider": provider})
    await db.commit()


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, request: Request, response: Response,
                  db: AsyncSession = Depends(get_db)):
    raw_token = (body.refresh_token or "").strip() or request.cookies.get("refresh_token")
    if not raw_token:
        raise AuthenticationError("Refresh token missing.")

    payload = decode_token(raw_token, "refresh")
    from app.security import hash_api_key
    token_hash = hash_api_key(raw_token)
    row = (await db.execute(select(M.RefreshToken).where(
        M.RefreshToken.jti == payload["jti"]))).scalars().first()
    if row is not None and row.revoked_at is not None and row.token_hash == token_hash:
        # Grace window for concurrent multi-tab requests / network retries (15 seconds)
        revoked_at = row.revoked_at
        if revoked_at.tzinfo is None:
            revoked_at = revoked_at.replace(tzinfo=timezone.utc)
        if (utcnow() - revoked_at) <= timedelta(seconds=15) and row.replaced_by:
            user = await db.get(M.User, row.user_id)
            if user and user.status == "active":
                log.info("Concurrent refresh within 15s grace window for user %s; issuing tokens", user.id)
                tokens = await _issue_tokens(db, user, request,
                                             uuid.UUID(payload["org_id"]) if payload.get("org_id") else None,
                                             session_id=row.session_id)
                _set_refresh_cookie(response, tokens.refresh_token)
                await db.commit()
                return tokens

    if row is None or row.revoked_at is not None or row.token_hash != token_hash:
        # possible token reuse — revoke the whole session family
        if row is not None:
            await db.execute(update(M.RefreshToken).where(
                M.RefreshToken.session_id == row.session_id)
                .values(revoked_at=utcnow()))
            await audit_service.record(db, action="auth.refresh_reuse_detected",
                                       actor_id=row.user_id, outcome="failure")
            await db.commit()
        raise AuthenticationError("Refresh token invalid or revoked. Sign in again.")
    if row.expires_at < utcnow():
        raise AuthenticationError("Refresh token expired. Sign in again.")
    user = await db.get(M.User, row.user_id)
    if user is None or user.status != "active":
        raise AuthenticationError("Account not found or inactive.")
    # rotate
    row.revoked_at = utcnow()
    tokens = await _issue_tokens(db, user, request,
                                 uuid.UUID(payload["org_id"]) if payload.get("org_id") else None,
                                 session_id=row.session_id)
    new_payload = decode_token(tokens.refresh_token, "refresh")
    row.replaced_by = new_payload.get("jti")
    session = await db.get(M.Session, row.session_id)
    if session:
        session.last_seen_at = utcnow()
    _set_refresh_cookie(response, tokens.refresh_token)
    await db.commit()
    return tokens


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response,
                 principal: Principal = Depends(get_principal),
                 db: AsyncSession = Depends(get_db)):
    _clear_refresh_cookie(response)
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = decode_token(auth[7:], "access")
        except AuthenticationError:
            payload = None
        if payload and principal.user:
            await db.execute(update(M.RefreshToken).where(
                M.RefreshToken.user_id == principal.user.id,
                M.RefreshToken.revoked_at.is_(None))
                .values(revoked_at=utcnow()))
            await audit_service.record(db, action="auth.logout",
                                       actor_id=principal.user.id,
                                       org_id=principal.org_id)
            await db.commit()


@router.post("/logout-all", status_code=204)
async def logout_all(response: Response,
                     principal: Principal = Depends(get_principal),
                     db: AsyncSession = Depends(get_db)):
    _clear_refresh_cookie(response)
    if principal.user:
        await db.execute(update(M.RefreshToken).where(
            M.RefreshToken.user_id == principal.user.id,
            M.RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow()))
        await db.execute(update(M.Session).where(
            M.Session.user_id == principal.user.id,
            M.Session.revoked_at.is_(None))
            .values(revoked_at=utcnow()))
        await audit_service.record(db, action="auth.logout_all",
                                   actor_id=principal.user.id,
                                   org_id=principal.org_id)
        await db.commit()


@router.get("/me", response_model=dict)
async def me(principal: Principal = Depends(get_principal),
             db: AsyncSession = Depends(get_db)):
    if principal.kind == "api_key" or principal.user is None:
        raise AuthenticationError("API keys cannot access user profile endpoints.")
    orgs = []
    for m in (principal.user.memberships or []):
        if m.org is not None:
            orgs.append({"org": OrganizationOut.model_validate(m.org), "role": m.role})
    return {"user": UserOut.model_validate(principal.user),
            "organizations": orgs,
            "permissions": _permissions_for(principal)}


def _permissions_for(principal: Principal) -> list[str]:
    from app.rbac import ROLE_PERMISSIONS
    if principal.user and principal.user.is_platform_admin:
        from app.rbac import PERMISSIONS
        return list(PERMISSIONS)
    return sorted(ROLE_PERMISSIONS.get(principal.role, set()))


@router.get("/me/sessions", response_model=list[SessionOut])
async def my_sessions(principal: Principal = Depends(get_principal),
                      db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.Session).where(
        M.Session.user_id == principal.user_id,
        M.Session.expires_at > utcnow())
        .order_by(M.Session.created_at.desc()).limit(50))
    return [SessionOut.model_validate(s) for s in res.scalars().all()]


@router.post("/me/sessions/{session_id}/revoke", status_code=204)
async def revoke_session(session_id: uuid.UUID,
                         principal: Principal = Depends(get_principal),
                         db: AsyncSession = Depends(get_db)):
    s = await db.get(M.Session, session_id)
    if s is None or s.user_id != principal.user_id:
        raise NotFoundError("Session not found.")
    s.revoked_at = utcnow()
    await db.execute(update(M.RefreshToken).where(
        M.RefreshToken.session_id == session_id,
        M.RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
    await audit_service.record(db, action="auth.session_revoked",
                               actor_id=principal.user_id, org_id=principal.org_id,
                               resource_type="session", resource_id=str(session_id))
    await db.commit()


@router.put("/me", response_model=UserOut)
async def update_profile(body: UpdateProfileRequest,
                         principal: Principal = Depends(get_principal),
                         db: AsyncSession = Depends(get_db)):
    user = principal.user
    if user is None:
        raise AuthenticationError("User not found.")
    if body.name is not None:
        user.name = body.name
    if body.locale is not None:
        user.locale = body.locale
    if body.speak_lang is not None:
        user.speak_lang = body.speak_lang
    if body.hear_lang is not None:
        user.hear_lang = body.hear_lang
    await db.commit()
    return UserOut.model_validate(user)


@router.post("/me/change-password", status_code=204)
async def change_password(body: ChangePasswordRequest,
                          principal: Principal = Depends(get_principal),
                          db: AsyncSession = Depends(get_db)):
    user = principal.user
    if user is None:
        raise AuthenticationError("User not found.")
    if not verify_password(body.current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect.")
    ok, msg = password_policy_ok(body.new_password)
    if not ok:
        raise ValidationError(msg)
    user.password_hash = hash_password(body.new_password)
    await db.execute(update(M.RefreshToken).where(
        M.RefreshToken.user_id == user.id, M.RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow()))
    await audit_service.record(db, action="auth.password_changed",
                               actor_id=user.id, org_id=principal.org_id)
    await db.commit()


@router.post("/password-reset/request", status_code=202)
async def password_reset_request(email: str, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(M.User).where(
        M.User.email == email.lower()))).scalars().first()
    if user:
        token = secrets.token_urlsafe(24)
        await cache().set(f"pwreset:{token}", str(user.id), ttl_s=1800)
        log.info("password reset link (dev): /reset?token=%s", token)
    # always 202 — no account enumeration
    return {"status": "if the email exists, a reset link was issued"}


@router.post("/password-reset/confirm", status_code=204)
async def password_reset_confirm(body: dict, db: AsyncSession = Depends(get_db)):
    token = body.get("token", "")
    new_password = body.get("new_password", "")
    user_id = await cache().get(f"pwreset:{token}")
    if not user_id:
        raise AuthenticationError("Reset token invalid or expired.")
    ok, msg = password_policy_ok(new_password)
    if not ok:
        raise ValidationError(msg)
    user = await db.get(M.User, uuid.UUID(user_id))
    if user is None:
        raise NotFoundError("User not found.")
    user.password_hash = hash_password(new_password)
    await cache().delete(f"pwreset:{token}")
    await db.execute(update(M.RefreshToken).where(
        M.RefreshToken.user_id == user.id, M.RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow()))
    await audit_service.record(db, action="auth.password_reset", actor_id=user.id)
    await db.commit()


@router.get("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    user_id = await cache().get(f"verify:{token}")
    if not user_id:
        raise AuthenticationError("Verification token invalid or expired.")
    user = await db.get(M.User, uuid.UUID(user_id))
    if user:
        user.email_verified = True
        await cache().delete(f"verify:{token}")
        await db.commit()
    return {"status": "email verified"}
