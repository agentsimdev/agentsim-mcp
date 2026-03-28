"""Smoke tests for the AgentSIM MCP server — validates tool registration and input schemas."""

from __future__ import annotations

from agentsim_mcp.server import mcp, ProvisionInput, WaitInput, SessionInput


EXPECTED_TOOLS = {"provision_number", "wait_for_otp", "get_messages", "release_number", "list_numbers"}


def test_mcp_instance_exists() -> None:
    assert mcp is not None
    assert mcp.name == "AgentSIM"


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
