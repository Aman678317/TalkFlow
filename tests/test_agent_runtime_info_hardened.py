"""
The in-app agent runtime, as the CopilotKit client actually talks to it.

The client asks the runtime for an agent literally named "default" (the v2
provider's `agentId` is not applied to the sidebar's own chat). When the
runtime did not publish that name the client refused to start ("Agent
'default' not found after runtime sync ... Known agents: [globaltalk_agent]")
and the provider threw during render, which blanked the whole page
(2026-10-21).
"""
from __future__ import annotations


def test_runtime_info_publishes_the_agent_the_client_asks_for(services_app_client):
    r = services_app_client.get("/api/copilotkit/info")
    assert r.status_code == 200, r.text
    body = r.json()
    agents = body.get("agents") or {}
    assert "default" in agents, f"the client asks for 'default'; published: {list(agents)}"
    assert "globaltalk_agent" in agents, "the original agent name must stay published"
    assert agents["default"]["className"] == agents["globaltalk_agent"]["className"]


def test_runtime_info_is_reachable_from_the_post_method_too(services_app_client):
    r = services_app_client.post("/api/copilotkit/info")
    assert r.status_code == 200, r.text
    assert "default" in (r.json().get("agents") or {})


def test_the_run_endpoint_accepts_the_default_agent_name(services_app_client):
    """The agent name is not part of the routing contract - any name works."""
    r = services_app_client.post(
        "/api/copilotkit/agent/default/run",
        json={"threadId": "audit-thread", "messages": [
            {"role": "user", "content": "hello"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("threadId") == "audit-thread"
