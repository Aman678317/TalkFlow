"""Enterprise Privacy, Security, RBAC & Audit Engine (Module J).

Enforces strict tenant isolation, role-based access control, user-controlled media deletion,
configurable retention policies, and immutable compliance audit trails.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import time
from typing import Dict, List, Optional
from modules.enterprise_privacy.models import (
    AuditLogEntry,
    RetentionPolicy,
    UserRoleAssignment,
)

logger = logging.getLogger("talkflow.modules.enterprise_privacy")

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin": [
        "media:read", "media:delete", "media:export", "studio:edit",
        "tm:approve", "policy:manage", "keys:manage", "audit:read"
    ],
    "translator": [
        "media:read", "media:export", "studio:edit", "tm:approve"
    ],
    "viewer": [
        "media:read"
    ],
    "participant": [
        "room:join", "stream:listen"
    ],
}


class EnterprisePrivacyEngine:
    """Manages multi-tenant security boundaries, retention, RBAC, and compliance audits."""

    def __init__(self) -> None:
        # tenant_id -> RetentionPolicy
        self._policies: Dict[str, RetentionPolicy] = {}
        # (tenant_id, user_id) -> UserRoleAssignment
        self._roles: Dict[Tuple[str, str], UserRoleAssignment] = {}
        # List of AuditLogEntry
        self._audit_logs: List[AuditLogEntry] = []
        self._seed_default_policy()

    def _seed_default_policy(self) -> None:
        self.set_retention_policy(
            RetentionPolicy(
                tenant_id="org_default",
                recording_retention_days=30,
                transcript_retention_days=90,
                allow_training_on_data=False,
                require_explicit_consent_per_call=True,
                enforce_at_rest_encryption=True,
            )
        )
        self.assign_role("user_admin", "org_default", "admin")
        self.assign_role("user_reviewer", "org_default", "translator")

    # --- Retention & Consent Policies ---

    def set_retention_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        self._policies[policy.tenant_id] = policy
        logger.info(f"Updated retention policy for tenant '{policy.tenant_id}' (retention={policy.recording_retention_days}d)")
        return policy

    def get_retention_policy(self, tenant_id: str) -> RetentionPolicy:
        if tenant_id not in self._policies:
            self._policies[tenant_id] = RetentionPolicy(tenant_id=tenant_id)
        return self._policies[tenant_id]

    # --- Role-Based Access Control ---

    def assign_role(self, user_id: str, tenant_id: str, role: str) -> UserRoleAssignment:
        if role not in ROLE_PERMISSIONS:
            raise ValueError(f"Invalid role '{role}'. Allowed roles: {list(ROLE_PERMISSIONS.keys())}")
        assignment = UserRoleAssignment(user_id=user_id, tenant_id=tenant_id, role=role)
        self._roles[(tenant_id, user_id)] = assignment
        return assignment

    def verify_permission(self, user_id: str, tenant_id: str, permission: str) -> bool:
        """Verifies if the user holds the required permission within the given tenant boundary."""
        assignment = self._roles.get((tenant_id, user_id))
        if not assignment:
            # Default to viewer if authenticated user has no explicit assignment
            role = "viewer"
        else:
            role = assignment.role

        allowed = permission in ROLE_PERMISSIONS.get(role, [])
        if not allowed:
            self.log_audit(
                tenant_id=tenant_id,
                user_id=user_id,
                action="access_denied",
                resource_id=permission,
                resource_type="permission",
                status="denied",
            )
        return allowed

    # --- Audit Logging ---

    def log_audit(
        self,
        tenant_id: str,
        user_id: str,
        action: str,
        resource_id: str,
        resource_type: str,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditLogEntry:
        """Appends an immutable compliance audit record."""
        log_id = f"aud_{hashlib.md5(f'{tenant_id}_{user_id}_{action}_{time.time()}'.encode()).hexdigest()[:12]}"
        entry = AuditLogEntry(
            log_id=log_id,
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            resource_type=resource_type,
            status=status,
            details=details or {},
            timestamp=time.time(),
        )
        self._audit_logs.append(entry)
        return entry

    def query_audit_logs(self, tenant_id: str, limit: int = 100) -> List[AuditLogEntry]:
        """Queries tenant audit trail."""
        return [entry for entry in self._audit_logs if entry.tenant_id == tenant_id][-limit:]

    # --- User-Controlled Recording Deletion & Purge ---

    def delete_recording(self, file_path: str, tenant_id: str, user_id: str) -> bool:
        """Securely deletes media file and writes audit log."""
        if not self.verify_permission(user_id, tenant_id, "media:delete"):
            raise PermissionError(f"User '{user_id}' lacks permission 'media:delete' in tenant '{tenant_id}'.")

        p = Path(file_path)
        deleted = False
        if p.exists() and p.is_file():
            try:
                p.unlink()
                deleted = True
            except Exception as e:
                logger.error(f"Failed to delete file '{file_path}': {e}")

        self.log_audit(
            tenant_id=tenant_id,
            user_id=user_id,
            action="delete_recording",
            resource_id=file_path,
            resource_type="recording",
            status="success" if deleted else "file_not_found",
        )
        return deleted


# Global Privacy Engine Instance
enterprise_privacy_engine = EnterprisePrivacyEngine()

