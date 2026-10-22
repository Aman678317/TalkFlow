"""The CopilotKit thread store, scoped per organization.

Kept in its own module (no LangGraph/LangChain import) so the isolation can
be tested in every environment — the agent endpoints themselves are mounted
only where the optional agent dependencies are installed, and the store must
be verifiable either way (issue #109 class 3, day-2 finding B-3).
"""
from __future__ import annotations

from typing import Any

#: org_id -> thread_id -> messages
threads_db: dict[str, dict[str, list[dict[str, Any]]]] = {}


def org_threads(org_id: Any) -> dict[str, list[dict[str, Any]]]:
    """The thread store of one organization.

    The store is shared in-process, so every read and write is scoped by
    organization: a thread id from one organization must never resolve in
    another.
    """
    key = str(org_id or "")
    return threads_db.setdefault(key, {})
