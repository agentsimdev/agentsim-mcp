"""Smoke tests for the AgentSIM MCP server — validates tool registration and input schemas."""

from __future__ import annotations

import sys

import uvicorn
from starlette.testclient import TestClient

from agentsim_mcp.server import (
    OpenChallengeInput,
    ProvisionInput,
    SessionInput,
    WaitForVerdictInput,
    WaitInput,
    main,
    mcp,
)


EXPECTED_TOOLS = {
    # New control-plane nouns
    "open_challenge",
    "wait_for_verdict",
    # Legacy aliases (backward compatibility)
    "provision_number",
    "wait_for_otp",
    # Other tools
    "get_messages",
    "release_number",
    "list_numbers",
}


def test_mcp_instance_exists() -> None:
    assert mcp is not None
    assert mcp.name == "AgentSIM"


def test_http_transport_does_not_create_server_sessions(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(sys, "argv", ["agentsim-mcp", "--http"])
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(app=app))

    main()

    initialize = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "session-retention-test", "version": "1"},
        },
    }
    with TestClient(captured["app"]) as client:  # type: ignore[arg-type]
        responses = []
        for request_id in range(100):
            initialize["id"] = request_id
            responses.append(
                client.post(
                    "/mcp",
                    headers={"accept": "application/json, text/event-stream"},
                    json=initialize,
                )
            )
        tools_response = client.post(
            "/mcp",
            headers={"accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 101, "method": "tools/list", "params": {}},
        )

    assert {response.status_code for response in responses} == {200}
    assert {response.headers.get("mcp-session-id") for response in responses} == {None}
    assert tools_response.status_code == 200
    assert "open_challenge" in tools_response.text


def test_provision_input_defaults() -> None:
    inp = ProvisionInput(agent_id="test-bot")
    assert inp.country == "US"
    assert inp.ttl_seconds == 3600


def test_wait_input_defaults() -> None:
    inp = WaitInput(session_id="sess-abc")
    assert inp.timeout_seconds == 60
    assert inp.auto_reroute is True


def test_session_input_requires_session_id() -> None:
    import pytest

    with pytest.raises(Exception):
        SessionInput()  # type: ignore[call-arg]


def test_provision_input_ttl_bounds() -> None:
    import pytest

    with pytest.raises(Exception):
        ProvisionInput(agent_id="test", ttl_seconds=10)  # below 60

    with pytest.raises(Exception):
        ProvisionInput(agent_id="test", ttl_seconds=100_000)  # above 86400


def test_open_challenge_input_defaults() -> None:
    inp = OpenChallengeInput(agent_id="test-bot")
    assert inp.channel == "sms_otp"
    assert inp.country == "US"
    assert inp.ttl_seconds == 3600
    assert inp.service_url is None


def test_open_challenge_input_channels() -> None:
    for channel in ["sms_otp", "email_otp", "magic_link", "webauthn_required"]:
        inp = OpenChallengeInput(agent_id="test-bot", channel=channel)
        assert inp.channel == channel


def test_wait_for_verdict_input_defaults() -> None:
    inp = WaitForVerdictInput(session_id="sess-xyz")
    assert inp.timeout_seconds == 60


def test_wait_for_verdict_input_requires_session_id() -> None:
    import pytest

    with pytest.raises(Exception):
        WaitForVerdictInput()  # type: ignore[call-arg]


async def test_all_tools_registered() -> None:
    """Verify both new tools and legacy aliases are registered."""
    tools = await mcp.list_tools()
    registered_tools = {tool.name for tool in tools}
    assert EXPECTED_TOOLS.issubset(registered_tools), f"Missing tools: {EXPECTED_TOOLS - registered_tools}"
