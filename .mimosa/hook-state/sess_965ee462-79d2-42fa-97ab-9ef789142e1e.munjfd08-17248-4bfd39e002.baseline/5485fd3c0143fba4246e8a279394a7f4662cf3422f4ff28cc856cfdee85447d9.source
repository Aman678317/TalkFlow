"""RBAC: roles → permissions. Enforced at service boundaries via require_permission()."""
from __future__ import annotations

ALL_PERMISSIONS = [
    "manage_members", "manage_billing", "manage_glossaries", "manage_api_keys",
    "create_meeting", "delete_meeting", "view_transcript", "export_document",
    "manage_integrations", "manage_security", "view_usage", "translate",
    "upload_document", "manage_style_profiles", "manage_translation_memory",
    "use_assistant", "manage_webhooks", "view_audit",
]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(ALL_PERMISSIONS),
    "admin": set(ALL_PERMISSIONS) - {"manage_billing"},  # billing often reserved; owner keeps all
    "manager": {
        "manage_members", "manage_glossaries", "create_meeting", "delete_meeting",
        "view_transcript", "export_document", "manage_integrations", "view_usage",
        "translate", "upload_document", "manage_style_profiles", "manage_translation_memory",
        "use_assistant", "manage_webhooks",
    },
    "member": {
        "create_meeting", "view_transcript", "export_document", "translate",
        "upload_document", "manage_glossaries", "manage_translation_memory",
        "use_assistant",
    },
    "viewer": {"view_transcript", "translate"},
}

# admin role also gets billing in this deployment model (documented in docs/SECURITY.md)
ROLE_PERMISSIONS["admin"].add("manage_billing")


def role_can(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def roles_for_permission(permission: str) -> list[str]:
    return [r for r, perms in ROLE_PERMISSIONS.items() if permission in perms]
