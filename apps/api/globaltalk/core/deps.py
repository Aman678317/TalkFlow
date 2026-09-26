"""FastAPI dependencies: current user (JWT or API key), org membership, permission checks."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from globaltalk.core.db import get_db
from globaltalk.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from globaltalk.core.logging import tenant_id_var, user_id_var
from globaltalk.core.rbac import role_can
from globaltalk.core.security import decode_token, sha256
from globaltalk.models import ApiKey, Organization, OrganizationMember, User


class Principal:
    """Authenticated caller: a user (JWT) or an org-scoped API key."""

    def __init__(self, *, user: User | None = None, org: Organization | None = None,
                 membership: OrganizationMember | None = None, api_key: ApiKey | None = None):
        self.user = user
        self.org = org
        self.membership = membership
        self.api_key = api_key

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user else None

    @property
    def org_id(self) -> str:
        if self.org:
            return self.org.id
        raise UnauthorizedError("No organization context")

    @property
    def role(self) -> str:
        if self.api_key:
            return "admin"  # API keys act with admin scope of their org; scopes refine this
        return self.membership.role if self.membership else "member"

    @property
    def is_platform_admin(self) -> bool:
        return bool(self.user and self.user.is_platform_admin)

    def can(self, permission: str) -> bool:
        return self.is_platform_admin or role_can(self.role, permission)


def _load_membership(db: Session, user: User, org_id: str | None) -> tuple[Organization, OrganizationMember]:
    q = db.query(OrganizationMember, Organization).join(
        Organization, Organization.id == OrganizationMember.org_id
    ).filter(OrganizationMember.user_id == user.id)
    if org_id:
        q = q.filter(Organization.id == org_id)
    row = q.order_by(OrganizationMember.created_at.asc()).first()
    if not row:
        raise ForbiddenError("You are not a member of any organization", code="no_org")
    membership, org = row
    return org, membership


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    # 1) Bearer JWT
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
        if token.startswith("gtk_"):  # developer API key
            return _principal_from_api_key(db, token)
        payload = decode_token(token, "access")
        user = db.get(User, payload["sub"])
        if not user or not user.is_active:
            raise UnauthorizedError("User not found or inactive")
        # org switcher: explicit X-Org-Id header > token's org claim > first membership
        org_id = request.headers.get("x-org-id") or payload.get("org")
        org, membership = _load_membership(db, user, org_id)
        tenant_id_var.set(org.id)
        user_id_var.set(user.id)
        return Principal(user=user, org=org, membership=membership)
    # 2) API key header
    api_key = request.headers.get("x-api-key", "")
    if api_key:
        return _principal_from_api_key(db, api_key)
    raise UnauthorizedError("Authentication required", code="auth_required")


def _principal_from_api_key(db: Session, token: str) -> Principal:
    row = (db.query(ApiKey).filter(ApiKey.key_hash == sha256(token), ApiKey.revoked.is_(False)).first())
    if not row:
        raise UnauthorizedError("Invalid API key", code="api_key_invalid")
    org = db.get(Organization, row.org_id)
    if not org:
        raise UnauthorizedError("API key organization missing", code="api_key_invalid")
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    tenant_id_var.set(org.id)
    return Principal(org=org, api_key=row)


def get_optional_principal(request: Request, db: Session = Depends(get_db)) -> Principal | None:
    try:
        return get_principal(request, db)
    except (UnauthorizedError, ForbiddenError):
        return None


def require_permission(permission: str):
    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.can(permission):
            raise ForbiddenError(f"Missing permission: {permission}", code="forbidden_permission",
                                 details={"permission": permission})
        return principal
    return _dep


def require_platform_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_platform_admin:
        raise ForbiddenError("Platform admin required", code="admin_required")
    return principal


def get_org_or_404(db: Session, org_id: str) -> Organization:
    org = db.get(Organization, org_id)
    if not org:
        raise NotFoundError("Organization not found")
    return org


def ensure_org_member(db: Session, principal: Principal, org_id: str,
                      permission: str | None = None) -> None:
    """Tenant isolation guard: verify the principal belongs to org_id (or is platform admin)."""
    if principal.is_platform_admin:
        return
    if principal.org_id != org_id:
        raise ForbiddenError("Cross-organization access denied", code="tenant_isolation")
    if permission and not principal.can(permission):
        raise ForbiddenError(f"Missing permission: {permission}", code="forbidden_permission")
