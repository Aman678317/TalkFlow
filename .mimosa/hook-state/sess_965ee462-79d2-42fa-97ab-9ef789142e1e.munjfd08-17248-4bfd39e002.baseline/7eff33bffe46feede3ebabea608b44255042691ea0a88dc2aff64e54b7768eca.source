"""Organizations, members (team), projects (PDD §25, §26)."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.session import get_db
from app.deps import Principal, get_principal, require_org_user
from app.errors import ConflictError, NotFoundError, ValidationError
from app.rbac import ROLE_PERMISSIONS
from app.schemas import OrgMemberOut, OrganizationOut, UserOut
from app.services import audit_service

log = logging.getLogger("app.routers.orgs")

router = APIRouter(prefix="/api/v1", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberInvite(BaseModel):
    email: EmailStr
    role: str = "member"


class MemberRoleUpdate(BaseModel):
    role: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    created_at: object


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
async def create_org(body: OrgCreate, principal: Principal = Depends(get_principal),
                     db: AsyncSession = Depends(get_db)):
    import re, secrets
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:60] or "org"
    if (await db.execute(select(M.Organization).where(
            M.Organization.slug == slug))).scalars().first():
        slug = f"{slug}-{secrets.token_hex(2)}"
    org = M.Organization(name=body.name, slug=slug, plan="free")
    db.add(org)
    await db.flush()
    db.add(M.OrganizationMember(org_id=org.id, user_id=principal.user_id, role="owner"))
    db.add(M.Project(org_id=org.id, name="Default Project"))
    await db.commit()
    from app.services import billing_service
    await billing_service.get_or_create_subscription(db, org)
    await audit_service.record(db, action="org.created", org_id=org.id,
                               actor_id=principal.user_id, resource_type="org",
                               resource_id=str(org.id))
    await db.commit()
    return OrganizationOut.model_validate(org)


@router.get("/organizations/current", response_model=OrganizationOut)
async def current_org(principal: Principal = Depends(require_org_user)):
    return OrganizationOut.model_validate(principal.org)


@router.get("/members", response_model=list[OrgMemberOut])
async def list_members(principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.OrganizationMember).where(
        M.OrganizationMember.org_id == principal.org_id,
        M.OrganizationMember.status == "active")
        .order_by(M.OrganizationMember.created_at))
    return [OrgMemberOut.model_validate(m) for m in res.scalars().all()]


@router.post("/members", status_code=201)
async def invite_member(body: MemberInvite,
                        principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    principal.require("manage_members")
    if body.role not in ROLE_PERMISSIONS:
        raise ValidationError(f"Unknown role '{body.role}'.",
                              details={"roles": list(ROLE_PERMISSIONS)})
    user = (await db.execute(select(M.User).where(
        M.User.email == body.email.lower()))).scalars().first()
    if user is None:
        # invite-by-email without account: record pending invite (dev: returns token)
        return {"status": "invited", "email": body.email, "pending": True}
    existing = (await db.execute(select(M.OrganizationMember).where(
        M.OrganizationMember.org_id == principal.org_id,
        M.OrganizationMember.user_id == user.id))).scalars().first()
    if existing and existing.status == "active":
        raise ConflictError("User is already a member.")
    if existing:
        existing.status = "active"
        existing.role = body.role
    else:
        db.add(M.OrganizationMember(org_id=principal.org_id, user_id=user.id,
                                    role=body.role))
    await audit_service.record(db, action="org.member_added", org_id=principal.org_id,
                               actor_id=principal.user_id, resource_type="user",
                               resource_id=str(user.id), details={"role": body.role})
    await db.commit()
    return {"status": "added", "email": body.email, "role": body.role}


@router.put("/members/{member_id}/role", status_code=200)
async def update_member_role(member_id: uuid.UUID, body: MemberRoleUpdate,
                             principal: Principal = Depends(require_org_user),
                             db: AsyncSession = Depends(get_db)):
    principal.require("manage_members")
    if body.role not in ROLE_PERMISSIONS:
        raise ValidationError(f"Unknown role '{body.role}'.")
    member = await db.get(M.OrganizationMember, member_id)
    if member is None or member.org_id != principal.org_id:
        raise NotFoundError("Member not found.")
    if member.role == "owner" and body.role != "owner":
        owners = (await db.execute(select(M.OrganizationMember).where(
            M.OrganizationMember.org_id == principal.org_id,
            M.OrganizationMember.role == "owner"))).scalars().all()
        if len(owners) <= 1:
            raise ConflictError("Transfer ownership before demoting the last owner.")
    old = member.role
    member.role = body.role
    await audit_service.record(db, action="org.member_role_changed",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="member", resource_id=str(member_id),
                               details={"from": old, "to": body.role})
    await db.commit()
    return {"id": str(member_id), "role": body.role}


@router.delete("/members/{member_id}", status_code=204)
async def remove_member(member_id: uuid.UUID,
                        principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    principal.require("manage_members")
    member = await db.get(M.OrganizationMember, member_id)
    if member is None or member.org_id != principal.org_id:
        raise NotFoundError("Member not found.")
    if member.user_id == principal.user_id and member.role == "owner":
        raise ConflictError("Owners cannot remove themselves; transfer ownership first.")
    member.status = "removed"
    await audit_service.record(db, action="org.member_removed",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="member", resource_id=str(member_id))
    await db.commit()


@router.get("/projects", response_model=list[dict])
async def list_projects(principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.Project).where(
        M.Project.org_id == principal.org_id).order_by(M.Project.created_at))
    return [{"id": str(p.id), "name": p.name, "description": p.description,
             "created_at": p.created_at.isoformat()} for p in res.scalars().all()]


@router.post("/projects", status_code=201, response_model=dict)
async def create_project(body: ProjectCreate,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_projects")
    p = M.Project(org_id=principal.org_id, name=body.name, description=body.description)
    db.add(p)
    await db.commit()
    return {"id": str(p.id), "name": p.name}


@router.get("/roles", response_model=dict)
async def roles():
    """RBAC matrix — consumed by the team-management UI."""
    return {"permissions": sorted({p for perms in ROLE_PERMISSIONS.values() for p in perms}),
            "roles": {r: sorted(p) for r, p in ROLE_PERMISSIONS.items()}}
