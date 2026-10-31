"""Data models for Developer Platform, API Keys & Webhooks (Module I)."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ApiKeyRecord(BaseModel):
    """Developer API key metadata, permissions, and usage limits."""
    key_id: str
    api_key_hash: str
    name: str = "Default Developer Key"
    tenant_id: str = "org_default"
    role: str = "developer"  # 'admin', 'developer', 'read_only'
    is_active: bool = True
    rate_limit_rpm: int = 120  # Requests per minute
    total_minutes_allowed: float = 1000.0  # Monthly quota in audio minutes
    total_minutes_used: float = 0.0
    total_requests_count: int = 0
    created_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None


class WebhookRegistration(BaseModel):
    """Webhook subscription for automated event dispatching."""
    webhook_id: str
    tenant_id: str = "org_default"
    target_url: str
    event_types: List[str] = Field(default_factory=lambda: ["job.completed", "meeting.intelligence.ready"])
    secret_token: str
    is_active: bool = True
    created_at: float = Field(default_factory=time.time)


class WebhookDeliveryLog(BaseModel):
    """Log record of a webhook delivery attempt."""
    delivery_id: str
    webhook_id: str
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    response_code: Optional[int] = None
    success: bool = False
    timestamp: float = Field(default_factory=time.time)
