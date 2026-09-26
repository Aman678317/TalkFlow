"""RBAC: roles -> permissions (PDD §26). Enforced at service boundaries."""
from __future__ import annotations

from app.errors import AuthorizationError

PERMISSIONS = [
    "manage_members", "manage_billing", "manage_glossaries", "manage_api_keys",
    "create_meeting", "delete_meeting", "view_transcript", "export_document",
    "manage_integrations", "manage_security", "view_usage", "manage_documents",
    "manage_styles", "manage_tm", "manage_webhooks", "admin_platform",
    "use_translate", "use_voice", "manage_projects", "view_audit",
]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(PERMISSIONS),
    "admin": set(PERMISSIONS) - {"admin_platform"},
    "manager": {
        "manage_members", "manage_glossaries", "create_meeting", "delete_meeting",
        "view_transcript", "export_document", "manage_integrations", "view_usage",
        "manage_documents", "manage_styles", "manage_tm", "manage_webhooks",
        "use_translate", "use_voice", "manage_projects", "view_audit",
    },
    "member": {
        "create_meeting", "view_transcript", "export_document", "view_usage",
        "manage_documents", "manage_glossaries", "manage_styles", "manage_tm",
        "use_translate", "use_voice",
    },
    "viewer": {"view_transcript", "use_translate", "view_usage"},
}


def role_can(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_role(role: str, permission: str) -> None:
    if not role_can(role, permission):
        raise AuthorizationError(
            f"Role '{role}' lacks permission '{permission}'.",
            details={"required_permission": permission, "role": role})
