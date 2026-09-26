"""Auth routes: signup/login/logout/refresh, email verification, password reset, sessions.

Tokens: short-lived JWT access + rotating refresh tokens (hashed at rest, bound to a
tracked device session). Passwords: bcrypt(12). OIDC/SAML/MFA: architecture prepared
(User.mfa_enabled, Integration.kind='oidc'), behind the enterprise_sso flag.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from globaltalk.core.audit import audit
from globaltalk.core.config import settings
from globaltalk.core.db import get_db
from globaltalk.core.deps import Principal, get_principal
from globaltalk.core.errors import NotFoundError, UnauthorizedError, ValidationError
from globaltalk.core.ratelimit import Limit, check_rate_limit
from globaltalk.core.security import (create_access_token, create_refresh_token,
                                      hash_password, random_token, sha256, verify_password)
from globaltalk.models import (Organization, OrganizationMember, RefreshToken, Subscription,
                               User, UserSession)
from globaltalk.schemas import (AuthResponse, LoginRequest, MembershipOut, OrgOut,
                                PasswordResetConfirm, PasswordResetRequest, RefreshRequest,
                                SessionOut, SignupRequest, TokenPair, UserOut)

router = APIRouter(prefix="/auth", tags=["auth"])
AUTH_LIMIT = Limit.parse(settings.rate_limit_auth)


def _slugify(name: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    return slug or fallback


def _issue_tokens(db: Session, user: User, org: Organization | None, request: Request,
                  user_agent: str = "", ip: str = "") -> tuple[TokenPair, UserSession]:
    session = UserSession(user_id=user.id, user_agent=user_agent[:400], ip_address=ip[:64])
    db.add(session)
    db.flush()
    access = create_access_token(user.id, {"org": org.id} if org else None)
    refresh, refresh_hash = create_refresh_token(user.id, session.id)
    db.add(RefreshToken(user_id=user.id, session_id=session.id, token_hash=refresh_hash,
                        expires_at=datetime.now(timezone.utc)
                        + timedelta(days=settings.refresh_token_ttl_days)))
    db.commit()
    return TokenPair(access_token=access, refresh_token=refresh,
                     expires_in=settings.access_token_ttl_minutes * 60), session


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(body: SignupRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f"signup:{request.client.host if request.client else 'x'}", AUTH_LIMIT)
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise ValidationError("An account with this email already exists", code="email_taken")
    user = User(email=email, password_hash=hash_password(body.password),
                full_name=body.full_name.strip(),
                verification_token_hash=sha256(random_token()))
    db.add(user)
    db.flush()
    org_name = body.organization_name.strip() or f"{user.full_name or email}'s Workspace"
    slug = _slugify(org_name, "org")
    if db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{slug}-{sha256(email)[:6]}"
    org = Organization(name=org_name, slug=slug, plan="free")
    db.add(org)
    db.flush()
    db.add(OrganizationMember(org_id=org.id, user_id=user.id, role="owner"))
    db.add(Subscription(org_id=org.id, plan="free", status="active",
                        current_period_start=datetime.now(timezone.utc)))
    db.commit()
    audit(db, "user.signup", org_id=org.id, actor_user_id=user.id,
          ip_address=request.client.host if request.client else "")
    tokens, _ = _issue_tokens(db, user, org, request,
                              request.headers.get("user-agent", ""),
                              request.client.host if request.client else "")
    return AuthResponse(tokens=tokens, user=UserOut.model_validate(user),
                        membership=MembershipOut(org=OrgOut.model_validate(org), role="owner"))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit(f"login:{body.email.lower()}", AUTH_LIMIT)
    user = db.query(User).filter(User.email == body.email.lower()).first()
    # constant-time-ish: verify against a dummy hash when the user doesn't exist
    ok = verify_password(body.password, user.password_hash if user else
                         "$2b$12$C6UzMDM.H6dfI/f/IKcEeO7ZBpDLWjLbLmXa2yTvmMmJQTlbUJyJq")
    if not user or not ok or not user.is_active:
        audit(db, "auth.login_failed", actor_user_id=user.id if user else None,
              ip_address=request.client.host if request.client else "",
              details={"email": body.email.lower()})
        raise UnauthorizedError("Invalid email or password", code="bad_credentials")
    membership = (db.query(OrganizationMember, Organization)
                  .join(Organization).filter(OrganizationMember.user_id == user.id)
                  .order_by(OrganizationMember.created_at.asc()).first())
    org = membership[1] if membership else None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, "auth.login", org_id=org.id if org else None, actor_user_id=user.id,
          ip_address=request.client.host if request.client else "")
    tokens, _ = _issue_tokens(db, user, org, request, request.headers.get("user-agent", ""),
                              request.client.host if request.client else "")
    return AuthResponse(
        tokens=tokens, user=UserOut.model_validate(user),
        membership=MembershipOut(org=OrgOut.model_validate(org), role=membership[0].role)
        if membership else None)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    from globaltalk.core.security import decode_token
    payload = decode_token(body.refresh_token, "refresh")
    row = (db.query(RefreshToken)
           .filter(RefreshToken.token_hash == sha256(body.refresh_token),
                   RefreshToken.revoked.is_(False)).first())
    if not row or row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise UnauthorizedError("Refresh token revoked or expired", code="refresh_invalid")
    user = db.get(User, row.user_id)
    session = db.get(UserSession, row.session_id)
    if not user or not user.is_active or not session or session.revoked:
        raise UnauthorizedError("Session invalid", code="session_invalid")
    # rotate: revoke old, issue new (replay of a stolen token then fails loudly)
    row.revoked = True
    membership = (db.query(OrganizationMember)
                  .filter(OrganizationMember.user_id == user.id)
                  .order_by(OrganizationMember.created_at.asc()).first())
    org = db.get(Organization, membership.org_id) if membership else None
    access = create_access_token(user.id, {"org": org.id} if org else None)
    new_refresh, new_hash = create_refresh_token(user.id, session.id)
    row.replaced_by = new_hash
    db.add(RefreshToken(user_id=user.id, session_id=session.id, token_hash=new_hash,
                        expires_at=datetime.now(timezone.utc)
                        + timedelta(days=settings.refresh_token_ttl_days)))
    session.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return TokenPair(access_token=access, refresh_token=new_refresh,
                     expires_in=settings.access_token_ttl_minutes * 60)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, principal: Principal = Depends(get_principal),
           db: Session = Depends(get_db)):
    row = (db.query(RefreshToken)
           .filter(RefreshToken.token_hash == sha256(body.refresh_token)).first())
    if row:
        row.revoked = True
        session = db.get(UserSession, row.session_id)
        if session:
            session.revoked = True
        db.commit()
    audit(db, "auth.logout", org_id=principal.org_id if principal.org else None,
          actor_user_id=principal.user_id)


@router.get("/me", response_model=AuthResponse)
def me(principal: Principal = Depends(get_principal)):
    return AuthResponse(
        tokens=TokenPair(access_token="", refresh_token="", expires_in=0),
        user=UserOut.model_validate(principal.user) if principal.user else
        UserOut(id="", email="api-key", full_name="API Key", is_platform_admin=False,
                email_verified=True, default_language="en",
                created_at=datetime.now(timezone.utc)),
        membership=MembershipOut(org=OrgOut.model_validate(principal.org),
                                 role=principal.role) if principal.org else None)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = (db.query(UserSession).filter(UserSession.user_id == principal.user_id)
            .order_by(UserSession.created_at.desc()).limit(50).all())
    return [SessionOut(id=r.id, user_agent=r.user_agent, ip_address=r.ip_address,
                       created_at=r.created_at, last_seen_at=r.last_seen_at, revoked=r.revoked)
            for r in rows]


@router.post("/password-reset", status_code=202)
def password_reset(body: PasswordResetRequest, db: Session = Depends(get_db)):
    """Always 202 (no user enumeration). In dev the token is returned; in prod it is emailed."""
    user = db.query(User).filter(User.email == body.email.lower()).first()
    resp = {"status": "if the account exists, a reset link has been sent"}
    if user:
        token = random_token()
        user.password_reset_token_hash = sha256(token)
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        audit(db, "auth.password_reset_requested", actor_user_id=user.id)
        if settings.app_env != "production":
            resp["dev_token"] = token
    return resp


@router.post("/password-reset/confirm")
def password_reset_confirm(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    user = (db.query(User)
            .filter(User.password_reset_token_hash == sha256(body.token)).first())
    if (not user or not user.password_reset_expires_at
            or user.password_reset_expires_at.replace(tzinfo=timezone.utc)
            < datetime.now(timezone.utc)):
        raise UnauthorizedError("Reset token invalid or expired", code="reset_invalid")
    user.password_hash = hash_password(body.new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    # revoke all sessions on password reset
    for rt in db.query(RefreshToken).filter(RefreshToken.user_id == user.id,
                                            RefreshToken.revoked.is_(False)).all():
        rt.revoked = True
    db.commit()
    audit(db, "auth.password_reset_completed", actor_user_id=user.id)
    return {"status": "password updated; all sessions revoked"}


@router.post("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token_hash == sha256(token)).first()
    if not user:
        raise NotFoundError("Verification token invalid", code="verify_invalid")
    user.email_verified = True
    user.verification_token_hash = None
    db.commit()
    return {"status": "email verified"}
