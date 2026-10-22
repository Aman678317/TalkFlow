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

The agent endpoints are mounted only where the OPTIONAL agent dependencies
(LangChain/LangGraph) are installed — CI does not have them, so the HTTP
pins skip there exactly like the existing runtime-info suite does. The
isolation and the wiring are pinned **without** the optional dependencies,
so they hold in every environment.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
AGENT = REPO / "services" / "api" / "app" / "agent.py"
THREADS = REPO / "services" / "api" / "app" / "agent_threads.py"


def _agent_source() -> str:
    return AGENT.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. the wiring — checked without the optional agent dependencies
# --------------------------------------------------------------------------- #
def test_the_agent_endpoints_require_an_authenticated_member():
    src = _agent_source()
    assert "require_org_user" in src, (
        "the agent endpoints must depend on an authenticated organization member")
    run_endpoint = src[src.index("async def run_agent_endpoint"):]
    run_endpoint = run_endpoint[:run_endpoint.index("async def get_thread_messages")]
    assert "Depends(require_org_user)" in run_endpoint, (
        "the run endpoint (the LLM proxy) must require authentication")
    thread_endpoint = src[src.index("async def get_thread_messages"):]
    assert "Depends(require_org_user)" in thread_endpoint, (
        "the thread endpoint must require authentication")


def test_the_thread_store_is_scoped_per_organization():
    from app.agent_threads import org_threads, threads_db
    a = org_threads("org-a")
    a["t1"] = [{"id": "m1", "role": "user", "content": "secret"}]
    b = org_threads("org-b")
    assert not b.get("t1"), "another organization must not see the thread"
    assert org_threads("org-a")["t1"], "the owner must still see it"
    assert "org-a" in threads_db


def test_the_store_module_needs_no_agent_dependency():
    """The store must be verifiable where the optional agent deps are absent."""
    import ast
    tree = ast.parse(THREADS.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for dependency in ("langchain", "langgraph", "openai"):
        assert not any(dependency in name for name in imported), (
            f"the thread store must not import {dependency} — it has to stay "
            "testable without the optional agent dependencies")


def test_a_model_failure_is_reported_as_a_failure():
    """The catch-all must not answer a failed model call with a greeting."""
    src = _agent_source()
    assert 'status_code=502' in src, (
        "a failed model call must be reported as a failure, not a success")
    assert "Hello! I am GlobalTalk AI Copilot, your assistant" not in src, (
        "the canned fallback greeting must not stand in for an answer")


# --------------------------------------------------------------------------- #
# 2. the HTTP surface — where the optional agent is mounted
# --------------------------------------------------------------------------- #
def _skip_if_not_mounted(response) -> None:
    if response.status_code == 404:
        pytest.skip("the optional CopilotKit agent is not mounted in this environment")


def test_the_agent_run_endpoint_requires_authentication(services_app_client):
    res = services_app_client.post("/api/copilotkit/agent/globaltalk_agent/run",
                                    json={"messages": [{"role": "user", "content": "hello"}]})
    _skip_if_not_mounted(res)
    assert res.status_code in (401, 403), (
        f"an unauthenticated caller reached the agent: HTTP {res.status_code} {res.text[:200]}")


def test_the_thread_endpoint_requires_authentication(services_app_client):
    res = services_app_client.get("/api/copilotkit/threads/some-thread-id/messages")
    _skip_if_not_mounted(res)
    assert res.status_code in (401, 403), (
        f"an unauthenticated caller read a thread: HTTP {res.status_code}")


def test_a_thread_is_not_readable_from_another_organization(services_app_client, user,
                                                             second_user):
    from app.agent_threads import org_threads

    # Write the thread straight into the store: with no model configured the
    # run endpoint cannot create one, and the scoping is what is under test.
    org_threads(user["org_id"])["shared-thread-id"] = [
        {"id": "m1", "role": "user", "content": "secret"},
    ]

    own = services_app_client.get("/api/copilotkit/threads/shared-thread-id/messages",
                                  headers=user["headers"])
    other = services_app_client.get("/api/copilotkit/threads/shared-thread-id/messages",
                                    headers=second_user["headers"])
    _skip_if_not_mounted(own)
    assert own.status_code == 200
    assert other.status_code == 200
    assert len(own.json()["messages"]) == 1, "the owner must see their thread"
    assert other.json()["messages"] == [], (
        "another organization read a thread that is not theirs")


def test_the_info_endpoint_stays_public(services_app_client):
    res = services_app_client.get("/api/copilotkit/info")
    _skip_if_not_mounted(res)
    assert res.status_code == 200, res.text
    assert "agents" in res.json() or "name" in res.json()


@pytest.mark.asyncio
async def test_the_info_payload_names_the_agent():
    from app.agent_info import copilotkit_info_payload
    payload = copilotkit_info_payload()
    assert payload.get("name") or payload.get("agents"), (
        "the client refuses to start without an agent name")
