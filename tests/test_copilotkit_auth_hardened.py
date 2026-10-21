"""The CopilotKit agent endpoints must be authenticated (issue #109, class 3).

Evidence behind this suite (2026-10-22, the day-2 ownership map, finding B-3):

``app/agent.py`` mounted the CopilotKit agent endpoints with **no auth at
all**:

* ``POST /api/copilotkit/agent/{name}/run`` (and three aliases) called the
  model with the caller's message — an open LLM proxy;
* ``GET /api/copilotkit/threads/{id}/messages`` read the shared in-process
  thread store, so an id guess exposed another conversation;
* a failed model call was answered with a canned greeting, so a broken
  agent was indistinguishable from a working one.

Pinned here: the run and thread endpoints require an authenticated
organization member, the threads are scoped per organization, a model failure
is reported as a failure, and the metadata endpoint stays public (it exposes
no user data and the client fetches it before the user has a session).
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# 1. the LLM proxy must not be open
# --------------------------------------------------------------------------- #
def test_the_agent_run_endpoint_requires_authentication(services_app_client):
    res = services_app_client.post("/api/copilotkit/agent/globaltalk_agent/run",
                                    json={"messages": [{"role": "user", "content": "hello"}]})
    assert res.status_code in (401, 403), (
        f"an unauthenticated caller reached the agent: HTTP {res.status_code} {res.text[:200]}")


def test_the_thread_endpoint_requires_authentication(services_app_client):
    res = services_app_client.get("/api/copilotkit/threads/some-thread-id/messages")
    assert res.status_code in (401, 403), (
        f"an unauthenticated caller read a thread: HTTP {res.status_code}")


# --------------------------------------------------------------------------- #
# 2. a thread belongs to the organization that wrote it
# --------------------------------------------------------------------------- #
def test_a_thread_is_not_readable_from_another_organization(services_app_client, user,
                                                             second_user):
    """The first user's thread must be invisible to the second organization."""
    from app.agent import _org_threads

    # Write the thread straight into the store: with no model configured the
    # run endpoint cannot create one, and the scoping is what is under test.
    _org_threads(user["org_id"])["shared-thread-id"] = [
        {"id": "m1", "role": "user", "content": "secret"},
    ]

    own = services_app_client.get("/api/copilotkit/threads/shared-thread-id/messages",
                                  headers=user["headers"])
    other = services_app_client.get("/api/copilotkit/threads/shared-thread-id/messages",
                                    headers=second_user["headers"])
    assert own.status_code == 200
    assert other.status_code == 200
    assert len(own.json()["messages"]) == 1, "the owner must see their thread"
    assert other.json()["messages"] == [], (
        "another organization read a thread that is not theirs")


# --------------------------------------------------------------------------- #
# 3. a broken agent must not look like a working one
# --------------------------------------------------------------------------- #
def test_a_model_failure_is_reported_as_a_failure(services_app_client, user):
    """With no model configured the endpoint must not answer with a success."""
    res = services_app_client.post(
        "/api/copilotkit/agent/globaltalk_agent/run",
        json={"messages": [{"role": "user", "content": "a real question"}]},
        headers=user["headers"])
    assert res.status_code in (200, 502), res.text
    if res.status_code == 502:
        assert "error" in res.json(), "a failure must be reported as an error"
    else:
        # a working agent answers the question; it must not answer with a
        # canned greeting that stands in for an answer
        body = res.json()
        messages = body.get("messages", [])
        assert messages, "the agent must answer"
        content = messages[-1].get("content", "")
        assert "running successfully" not in content, (
            "a canned install-check greeting must not stand in for an answer")
        assert "Hello! I am GlobalTalk AI Copilot" not in content, (
            "the canned fallback greeting must not stand in for an answer")


# --------------------------------------------------------------------------- #
# 4. the metadata endpoint stays public (no user data, fetched pre-session)
# --------------------------------------------------------------------------- #
def test_the_info_endpoint_stays_public(services_app_client):
    res = services_app_client.get("/api/copilotkit/info")
    assert res.status_code == 200, res.text
    assert "agents" in res.json() or "name" in res.json()


@pytest.mark.asyncio
async def test_the_info_payload_names_the_agent():
    from app.agent_info import copilotkit_info_payload
    payload = copilotkit_info_payload()
    assert payload.get("name") or payload.get("agents"), (
        "the client refuses to start without an agent name")
