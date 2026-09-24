"""Smoke tests for the AgentSIM MCP server — validates tool registration and input schemas."""

from __future__ import annotations

import sys
import asyncio

import httpx
import pytest
import uvicorn
from fastmcp.exceptions import ToolError
from starlette.testclient import TestClient
import agentsim_mcp.server as server

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
    async def valid_key(_api_key: str) -> bool:
        return True
    monkeypatch.setattr(server, "_validate_api_key", valid_key)

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
        unauthenticated = client.post(
            "/mcp",
            headers={"accept": "application/json, text/event-stream"},
            json=initialize,
        )
        responses = []
        for request_id in range(100):
            initialize["id"] = request_id
            responses.append(
                client.post(
                    "/mcp",
                    headers={"accept": "application/json, text/event-stream", "x-api-key": "asm_test_caller"},
                    json=initialize,
                )
            )
        tools_response = client.post(
            "/mcp",
            headers={"accept": "application/json, text/event-stream", "x-api-key": "asm_test_caller"},
            json={"jsonrpc": "2.0", "id": 101, "method": "tools/list", "params": {}},
        )

    assert unauthenticated.status_code == 401
    assert {response.status_code for response in responses} == {200}
    assert {response.headers.get("mcp-session-id") for response in responses} == {None}
    assert tools_response.status_code == 200
    assert "open_challenge" in tools_response.text


def test_provision_input_defaults() -> None:
    inp = ProvisionInput(agent_id="test-bot", service_url="https://staging.example.com")
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
        ProvisionInput(agent_id="test", service_url="https://staging.example.com", ttl_seconds=10)  # below 60

    with pytest.raises(Exception):
        ProvisionInput(agent_id="test", service_url="https://staging.example.com", ttl_seconds=100_000)  # above 86400


def test_open_challenge_input_defaults() -> None:
    inp = OpenChallengeInput(agent_id="test-bot", service_url="https://staging.example.com")
    assert inp.channel == "sms_otp"
    assert inp.country == "US"
    assert inp.ttl_seconds == 3600
    assert inp.service_url == "https://staging.example.com"


def test_open_challenge_input_channels() -> None:
    for channel in ["sms_otp", "email_otp", "magic_link", "webauthn_required"]:
        inp = OpenChallengeInput(agent_id="test-bot", service_url="https://staging.example.com", channel=channel)
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


@pytest.mark.asyncio
async def test_concurrent_http_callers_keep_request_scoped_keys(monkeypatch) -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)
        seen.append(request.headers["x-api-key"])
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(base_url="https://api.test", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_http", client)
    monkeypatch.setattr(server, "_http_mode", True)

    async def call(api_key: str) -> None:
        token = server._request_api_key.set(api_key)
        try:
            await server._request("GET", "/usage/summary")
        finally:
            server._request_api_key.reset(token)

    await asyncio.gather(call("asm_test_one"), call("asm_test_two"))
    await client.aclose()
    assert sorted(seen) == ["asm_test_one", "asm_test_two"]


@pytest.mark.asyncio
async def test_stdio_keeps_the_local_environment_key(monkeypatch) -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["x-api-key"])
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(base_url="https://api.test", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_http", client)
    monkeypatch.setattr(server, "_http_mode", False)
    monkeypatch.setattr(server, "_API_KEY", "asm_test_local")

    await server._request("GET", "/usage/summary")
    await client.aclose()
    assert seen == ["asm_test_local"]


@pytest.mark.asyncio
@pytest.mark.parametrize("populated", [False, True])
async def test_list_numbers_returns_active_sessions_and_pagination(monkeypatch, populated) -> None:
    sessions = [{"session_id": "session-one", "agent_id": "qa-agent"}] if populated else []
    body = {"sessions": sessions, "has_more": populated}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/sessions"
        assert dict(request.url.params) == {
            "status": "active", "agent_id": "qa-agent", "limit": "1", "after": "previous-session",
        }
        assert request.headers["x-api-key"] == "asm_test_listing"
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(base_url="https://api.test/v1", transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(server, "_http", client)
        monkeypatch.setattr(server, "_http_mode", False)
        monkeypatch.setattr(server, "_API_KEY", "asm_test_listing")
        result = await mcp.call_tool("list_numbers", {"agent_id": "qa-agent", "limit": 1, "after": "previous-session"})
    assert result.structured_content == body


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(401, "unauthorized"), (403, "forbidden"), (404, "not_found"), (500, "internal_error")])
async def test_list_numbers_does_not_report_api_failures_as_an_empty_account(monkeypatch, status, code) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"status": "active", "limit": "100"}
        return httpx.Response(status, json={"error": code, "message": "Listing failed"})

    async with httpx.AsyncClient(base_url="https://api.test/v1", transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(server, "_http", client)
        monkeypatch.setattr(server, "_http_mode", False)
        monkeypatch.setattr(server, "_API_KEY", "asm_test_listing")
        with pytest.raises(ToolError, match=code):
            await mcp.call_tool("list_numbers", {})


@pytest.mark.asyncio
async def test_account_status_only_counts_active_sessions(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"status": "active", "limit": "100"}
        return httpx.Response(200, json={"sessions": [{"agent_id": "qa-agent"}], "has_more": True})

    async with httpx.AsyncClient(base_url="https://api.test/v1", transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(server, "_http", client)
        monkeypatch.setattr(server, "_http_mode", False)
        monkeypatch.setattr(server, "_API_KEY", "asm_test_listing")
        result = await server.account_status()
    assert "Active sessions: 1+" in result
