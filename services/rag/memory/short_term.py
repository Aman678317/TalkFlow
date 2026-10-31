"""Short-Term Memory Manager for active job states, chunk manifests and stage handoffs."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional
from rag.models import ShortTermMemoryItem
from rag.storage.base import BaseRAGStorage
from rag.storage import get_rag_storage


class ShortTermMemoryManager:
    """Manages active job-level state and chunk tracking across the 7 agents."""

    def __init__(self, storage: Optional[BaseRAGStorage] = None):
        self.storage = storage or get_rag_storage()

    def record_stage_transition(
        self,
        job_id: str,
        agent_id: str,
        stage: str,
        tenant_id: str = "talkflow_enterprise",
        chunk_updates: Optional[Dict[str, Any]] = None,
        intermediate_output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> ShortTermMemoryItem:
        """Updates or initializes short-term memory record for an active job."""
        existing = self.storage.get_short_term_memory(job_id, tenant_id)

        now = time.time()
        if existing:
            existing.agent_id = agent_id
            existing.stage = stage
            existing.updated_at = now
            if chunk_updates:
                existing.chunk_states.update(chunk_updates)
            if intermediate_output:
                existing.intermediate_outputs.update(intermediate_output)
            if error and error not in existing.active_errors:
                existing.active_errors.append(error)
            item = existing
        else:
            item = ShortTermMemoryItem(
                job_id=job_id,
                agent_id=agent_id,
                tenant_id=tenant_id,
                stage=stage,
                chunk_states=chunk_updates or {},
                intermediate_outputs=intermediate_output or {},
                active_errors=[error] if error else [],
                created_at=now,
                updated_at=now,
            )

        self.storage.save_short_term_memory(item)
        return item

    def get_job_state(self, job_id: str, tenant_id: str = "talkflow_enterprise") -> Optional[ShortTermMemoryItem]:
        """Retrieves short-term context for a processing job."""
        return self.storage.get_short_term_memory(job_id, tenant_id)

