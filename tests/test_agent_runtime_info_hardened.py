"""
The CopilotKit runtime-info contract.

The client asks the runtime for an agent literally named "default" (the v2
provider's `agentId` is not applied to the sidebar's own chat). When the
runtime did not publish that name the client refused to start ("Agent
'default' not found after runtime sync ... Known agents: [globaltalk_agent]")
and the provider threw during render, which blanked the whole page
(2026-10-21).

The payload lives in `app.agent_info` (no LangGraph import) so this contract is
testable even where the optional agent dependencies are not installed.
"""
from __future__ import annotations

import pytest

from app.agent_info import DEFAULT_AGENT_ALIAS, copilotkit_info_payload


def test_the_payload_publishes_the_agent_name_the_client_asks_for():
    payload = copilotkit_info_payload()
    agents = payload["agents"]
    assert DEFAULT_AGENT_ALIAS in agents, f"the client asks for 'default'; published: {list(agents)}"
    assert "globaltalk_agent" in agents, "the original agent name must stay published"
    assert agents[DEFAULT_AGENT_ALIAS]["className"] == agents["globaltalk_agent"]["className"]


def test_the_alias_points_at_the_same_agent():
    payload = copilotkit_info_payload()
    alias = payload["agents"][DEFAULT_AGENT_ALIAS]
    original = payload["agents"]["globaltalk_agent"]
    assert alias["description"] == original["description"]
    assert alias["className"] == original["className"]
    assert alias["name"] == DEFAULT_AGENT_ALIAS


def test_the_payload_keeps_its_documented_shape():
    payload = copilotkit_info_payload()
    assert payload["version"]
    assert payload["runtimeEntitlements"]["status"] == "ready"
    assert payload["threadEndpoints"]["restEndpointsAvailable"] is True


def test_a_custom_agent_name_is_also_published_with_the_alias():
    payload = copilotkit_info_payload(agent_name="other_agent")
    assert "other_agent" in payload["agents"]
    assert DEFAULT_AGENT_ALIAS in payload["agents"]


def test_the_runtime_serves_the_contract_when_the_agent_is_mounted(services_app_client):
    """The agent is an OPTIONAL dependency - skip where it is not installed."""
    r = services_app_client.get("/api/copilotkit/info")
    if r.status_code == 404:
        pytest.skip("the optional CopilotKit agent is not mounted in this environment")
    assert r.status_code == 200, r.text
    agents = r.json().get("agents") or {}
    assert DEFAULT_AGENT_ALIAS in agents
    assert "globaltalk_agent" in agents


def test_the_run_endpoint_accepts_the_alias_agent_name(services_app_client):
    r = services_app_client.post(
        "/api/copilotkit/agent/default/run",
        json={"threadId": "audit-thread", "messages": [
            {"role": "user", "content": "hello"}]},
    )
    if r.status_code == 404:
        pytest.skip("the optional CopilotKit agent is not mounted in this environment")
    assert r.status_code == 200, r.text
    assert r.json().get("threadId") == "audit-thread"
