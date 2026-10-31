"""Data models for Enterprise Privacy, RBAC & Audit Trails (Module J)."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RetentionPolicy(BaseModel):
    """Retention and automated purge configuration for a tenant."""
    tenant_id: str
    recording_retention_days: int = 30  # 0 = immediate purge after processing
    transcript_retention_days: int = 90
    allow_training_on_data: bool = False  # STRICTLY FALSE BY DEFAULT
    require_explicit_consent_per_call: bool = True
    enforce_at_rest_encryption: bool = True


class UserRoleAssignment(BaseModel):
    """RBAC assignment."""
    user_id: str
    tenant_id: str
    role: str  # 'admin', 'translator', 'viewer', 'participant'
    assigned_at: float = Field(default_factory=time.time)


class AuditLogEntry(BaseModel):
    """Immutable audit record for enterprise compliance."""
    log_id: str
    tenant_id: str
    user_id: str
    action: str  # 'access_media', 'delete_recording', 'export_dubbed_video', 'consent_grant', 'consent_revoke'
    resource_id: str
    resource_type: str  # 'meeting', 'recording', 'transcript', 'consent', 'api_key'
    status: str = "success"  # 'success', 'denied'
    ip_address: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
