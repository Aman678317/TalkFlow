"""
The CopilotKit runtime-info payload.

Kept in its own module (no LangGraph import) so the contract can be tested
wherever the optional agent dependencies are not installed.

The CopilotKit v2 client asks the runtime for an agent literally named
``default``: the provider's ``agentId`` is not applied to the sidebar's own
chat. When the runtime did not publish that name the client refused to start
("Agent 'default' not found after runtime sync ... Known agents:
[globaltalk_agent]") and the provider threw during render, which blanked the
whole page (2026-10-21).
"""

DEFAULT_AGENT_ALIAS = "default"


def copilotkit_info_payload(
    agent_name: str = "globaltalk_agent",
    description: str = "GlobalTalk AI assistant for translation, voice, and meetings",
    class_name: str = "LangGraphAGUIAgent",
) -> dict:
    """The payload served at ``/api/copilotkit/info``."""
    agent = {"name": agent_name, "description": description, "className": class_name}
    return {
        "version": "1.77.0",
        "agents": {
            agent_name: agent,
            # The client asks for "default"; the run endpoint accepts any agent
            # name, so publishing the alias is enough.
            DEFAULT_AGENT_ALIAS: {**agent, "name": DEFAULT_AGENT_ALIAS},
        },
        "mode": "intelligence",
        "intelligence": {
            "wsUrl": "wss://api.intelligence.copilotkit.ai/v1",
        },
        "licenseStatus": "valid",
        "runtimeEntitlements": {
            "status": "ready",
        },
        "threadEndpoints": {
            "managedThreadMetadata": True,
            "restEndpointsAvailable": True,
            "mutations": True,
        },
        "suggestions": True,
        "inspectorMetadata": True,
        "inspectorLearning": True,
        "audioFileTranscriptionEnabled": False,
    }
