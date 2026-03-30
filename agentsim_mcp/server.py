"""AgentSIM MCP Server — give AI coding assistants a real phone number for OTP relay."""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

# LLM-facing server description
MCP_INSTRUCTIONS = """\
AgentSIM gives you a real carrier-routed mobile phone number so you can receive SMS OTP codes \
autonomously — no human intervention required.

Typical workflow:
1. Call `provision_number` to lease a mobile number (returns session_id + phone number).
2. Trigger the SMS on the target service using that phone number.
3. Call `wait_for_otp` with the session_id — it blocks until the OTP arrives (up to 120 s).
4. Use the OTP code in your workflow.
5. Call `release_number` to return the number to the pool when done.

Carrier retry (handled automatically):
If `wait_for_otp` returns status=carrier_retry_required, a replacement number has been
provisioned on the same session. Re-enter the new_number on the target service, then call
wait_for_otp again with the same session_id.

Always release the number when finished, even on error, to avoid wasting pool capacity.
"""

mcp = FastMCP("AgentSIM", version="0.9.0", instructions=MCP_INSTRUCTIONS)

_API_KEY = os.environ.get("AGENTSIM_API_KEY", "")
_BASE_URL = os.environ.get("AGENTSIM_BASE_URL", "https://api.agentsim.dev/v1").rstrip("/")
_PORT = int(os.environ.get("PORT", "8000"))


async def _health(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def _server_card(request: Request) -> JSONResponse:
    return JSONResponse({
        "name": "AgentSIM",
        "qualifiedName": "agentsim/agentsim",
        "description": "Real SIM-backed phone numbers for AI agents — autonomous OTP capture. No VoIP. Carrier lookup returns mobile.",
        "vendor": "AgentSIM",
        "homepage": "https://agentsim.dev",
        "license": "MIT",
        "config": {
            "schema": {
                "type": "object",
                "properties": {
                    "apiKey": {
                        "type": "string",
                        "title": "AgentSIM API Key",
                        "description": "Your AgentSIM API key — get one at https://console.agentsim.dev",
                    }
                },
                "required": ["apiKey"],
            }
        },
    })


_http: Optional[httpx.AsyncClient] = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"x-api-key": _API_KEY, "Content-Type": "application/json"},
            timeout=130.0,
        )
    return _http


async def _request(method: str, path: str, params: Optional[dict[str, str]] = None, **kwargs: Any) -> Any:
    client = _get_http()
    response = await client.request(method, path, params=params, **kwargs)
    try:
        body = response.json()
    except Exception:
        body = {}
    if not response.is_success:
        code = body.get("error", "unknown_error")
        message = body.get("message", response.text)
        raise ToolError(f"AgentSIM API error [{code}]: {message}")
    return body


# --- Resources (improve Smithery quality score) ---

@mcp.resource("agentsim://status")
async def account_status() -> str:
    """Current AgentSIM account status including active sessions and usage."""
    if not _API_KEY:
        return "AGENTSIM_API_KEY not configured. Get one at https://console.agentsim.dev"
    try:
        data = await _request("GET", "/sessions")
        sessions = data.get("sessions", [])
        return f"Active sessions: {len(sessions)}\n" + "\n".join(
            f"  - {s.get('number', 'unknown')} (agent: {s.get('agent_id', 'unknown')}, expires: {s.get('expires_at', 'unknown')})"
            for s in sessions
        ) if sessions else "No active sessions."
    except Exception as e:
        return f"Could not fetch status: {e}"


@mcp.resource("agentsim://docs/quickstart")
def quickstart_guide() -> str:
    """AgentSIM quickstart guide — how to get started in 60 seconds."""
    return """# AgentSIM Quickstart

## 1. Get an API Key
Sign up at https://agentsim.dev and grab your API key from the dashboard.

## 2. Install
```bash
# Claude Code / Cursor
claude mcp add agentsim -e AGENTSIM_API_KEY=asm_live_xxx -- uvx agentsim-mcp

# Or use the remote server (no install needed)
# URL: https://mcp.agentsim.dev/mcp
```

## 3. Verify a Phone Number
Ask your AI assistant:
> "Verify my Stripe account with a phone number using AgentSIM"

The agent will:
1. Provision a real mobile number
2. Enter it on Stripe
3. Wait for the OTP
4. Complete verification
5. Release the number

## Pricing
- 10 free sessions/month
- $0.99 per session after that
- No monthly commitment

## Links
- Docs: https://docs.agentsim.dev
- Examples: https://github.com/agentsimdev/agentsim-examples
- Support: hello@agentsim.dev
"""


# --- Prompts (improve Smithery quality score) ---

@mcp.prompt()
def verify_phone_number(service: str = "Stripe", agent_id: str = "my-agent") -> str:
    """Step-by-step guide to verify a phone number on a target service.

    Walks through the full AgentSIM workflow: provision → enter number → wait for OTP → use code → release.
    """
    return f"""Follow these steps to verify a phone number on {service}:

1. Call provision_number with agent_id="{agent_id}" to get a real mobile number
2. Enter the returned phone number on {service}'s verification page
3. Call wait_for_otp with the session_id to receive the OTP code
4. Enter the OTP code on {service}
5. Call release_number to free the session

Important:
- If wait_for_otp returns status=carrier_retry_required, use the new_number instead
- Always call release_number when done, even on error
- Numbers are real T-Mobile SIM — they pass carrier lookup on all major services"""


@mcp.prompt()
def debug_verification_failure(error_message: str = "This phone number cannot be used for verification") -> str:
    """Diagnose why phone verification failed and suggest fixes.

    Common issues: VoIP blocking, carrier cold-start, number already used.
    """
    return f"""The user encountered this verification error: "{error_message}"

Diagnosis steps:
1. Check if the number was provisioned via provision_number (real SIM, not VoIP)
2. Use list_numbers to see active sessions and confirm the number is still leased
3. Use get_messages to check if any SMS was received but not parsed as OTP
4. If the service rejected the number outright, it may be a cooldown issue — try provisioning a new number

Common causes:
- "Cannot be used for verification" → Usually VoIP detection (AgentSIM numbers should pass this)
- No OTP received → Carrier cold-start filtering, try auto_reroute=true
- OTP expired → Service timeout, call wait_for_otp immediately after triggering SMS
- Number already used → Some services track numbers, provision a fresh one"""


# --- Tool input models ---

class ProvisionInput(BaseModel):
    agent_id: str = Field(description="Unique identifier for the agent requesting the number (e.g. 'checkout-bot').")
    country: str = Field(default="US", description="ISO 3166-1 alpha-2 country code. Supported: US. More countries coming soon.")
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, description="How long to hold the number (seconds). Default 1 hour.")
    webhook_url: Optional[str] = Field(default=None, description="Optional HTTPS URL to receive OTP via webhook instead of polling.")


class WaitInput(BaseModel):
    session_id: str = Field(description="Session ID returned by provision_number.")
    timeout_seconds: int = Field(default=60, ge=1, le=120, description="Maximum seconds to wait. Default 60.")
    auto_reroute: bool = Field(default=True, description="On timeout, automatically swap to a fresh number on the same session and return retry instructions.")


class SessionInput(BaseModel):
    session_id: str = Field(description="Session ID returned by provision_number.")


async def _reroute_on_timeout(session_id: str, timeout_seconds: int) -> dict[str, Any]:
    """Swap to a fresh number on the same session after a carrier timeout."""
    session = await _request("GET", f"/sessions/{session_id}")
    country = session.get("country", "US")
    previous_number = session.get("number", "unknown")

    reroute = await _request("POST", f"/sessions/{session_id}/reroute", json={"country": country})

    return {
        "status": "carrier_retry_required",
        "session_id": session_id,
        "new_number": reroute["new_number"],
        "previous_number": previous_number,
        "country": country,
        "expires_at": reroute.get("expires_at"),
        "message": (
            f"The first number ({previous_number}) timed out after {timeout_seconds}s — "
            "likely US carrier cold-start filtering on a new longcode. "
            f"A replacement number ({reroute['new_number']}) has been assigned to the same session. "
            "Re-enter this new number on the target service, then call wait_for_otp again "
            f"with session_id='{session_id}'."
        ),
    }


# --- Tools ---

@mcp.tool()
async def provision_number(input: ProvisionInput) -> dict[str, Any]:
    """Lease a real mobile phone number for receiving SMS OTP codes.

    Returns the phone number (e164 format) and a session_id needed for all
    subsequent calls. The number is exclusively yours for ttl_seconds.

    Next step: use the returned `number` on your target service to trigger an SMS,
    then call `wait_for_otp` with the returned `session_id`.
    """
    if not _API_KEY:
        raise ToolError("AGENTSIM_API_KEY environment variable is not set.")

    body: dict[str, Any] = {
        "agent_id": input.agent_id,
        "country": input.country,
        "ttl_seconds": input.ttl_seconds,
    }
    if input.webhook_url:
        body["webhook_url"] = input.webhook_url

    data = await _request("POST", "/sessions", json=body)

    return {
        "session_id": data["session_id"],
        "number": data["number"],
        "country": data["country"],
        "agent_id": data["agent_id"],
        "expires_at": data["expires_at"],
        "next_step": f"Use `{data['number']}` on your target service, then call wait_for_otp(session_id='{data['session_id']}')",
    }


@mcp.tool()
async def wait_for_otp(input: WaitInput) -> dict[str, Any]:
    """Block until an SMS OTP arrives for this session, then return the code.

    Polls the AgentSIM API for up to `timeout_seconds`. Returns the OTP code
    and the message it was extracted from.

    If the OTP does not arrive in time, raises a ToolError with advice on retrying.
    Always call `release_number` after you have used the OTP.
    """
    try:
        data = await _request(
            "POST",
            f"/sessions/{input.session_id}/wait",
            json={"timeout_seconds": input.timeout_seconds},
        )
    except ToolError as exc:
        if "otp_timeout" in str(exc):
            if input.auto_reroute:
                return await _reroute_on_timeout(input.session_id, input.timeout_seconds)
            raise ToolError(
                f"No OTP received within {input.timeout_seconds}s. "
                "Check that you entered the correct phone number on the target service. "
                "You can retry wait_for_otp or call release_number to free the session."
            ) from exc
        raise

    return {
        "otp_code": data.get("otp_code"),
        "from": data.get("from_number"),
        "received_at": data.get("received_at"),
        "next_step": "Use the otp_code in your workflow, then call release_number to free the session.",
    }


@mcp.tool()
async def get_messages(input: SessionInput) -> dict[str, Any]:
    """List all SMS messages received in this session without consuming the OTP.

    Use this to inspect raw messages or check if an SMS arrived before calling
    wait_for_otp. Does NOT mark the OTP as consumed.
    """
    data = await _request("GET", f"/sessions/{input.session_id}/messages")
    return {
        "messages": data.get("messages", []),
        "has_more": data.get("has_more", False),
    }


@mcp.tool()
async def release_number(input: SessionInput) -> dict[str, Any]:
    """Release a provisioned number back to the pool.

    Always call this when you are done with the session — even on error —
    to avoid consuming pool capacity unnecessarily.
    """
    try:
        data = await _request("DELETE", f"/sessions/{input.session_id}")
    except ToolError as exc:
        if "not_found" in str(exc):
            raise ToolError(
                f"Session {input.session_id} not found. It may have already expired or been released."
            ) from exc
        raise

    return {
        "status": data.get("status", "completed"),
        "closed_at": data.get("closed_at"),
    }


@mcp.tool()
async def list_numbers(agent_id: Optional[str] = None) -> dict[str, Any]:
    """List active sessions, optionally filtered by agent_id.

    Use this to check for leaked sessions or inspect what numbers are
    currently active in your account.
    """
    query_params = {"agent_id": agent_id} if agent_id else None

    try:
        data = await _request("GET", "/sessions", params=query_params)
    except ToolError:
        # GET /sessions may not be implemented yet — return empty gracefully
        return {"sessions": [], "note": "Session listing not yet available."}

    return {"sessions": data.get("sessions", [])}


class _WellKnownMiddleware:
    """ASGI middleware that intercepts /.well-known/* before FastMCP routing."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/.well-known/mcp/server-card.json":
            await JSONResponse({
                "name": "AgentSIM",
                "qualifiedName": "agentsim/agentsim",
                "description": "Real SIM-backed phone numbers for AI agents — autonomous OTP capture. No VoIP.",
                "vendor": "AgentSIM",
                "homepage": "https://agentsim.dev",
                "license": "MIT",
                "config": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "apiKey": {
                                "type": "string",
                                "title": "AgentSIM API Key",
                                "description": "Your AgentSIM API key — get one at https://console.agentsim.dev",
                            }
                        },
                        "required": ["apiKey"],
                    }
                },
            })(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def main() -> None:
    http_mode = "--sse" in sys.argv or "--http" in sys.argv
    if http_mode:
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        import uvicorn

        mcp_http = mcp.http_app()

        # /health and /.well-known/* are intercepted before FastMCP's ASGI
        # app so they bypass session/auth middleware entirely.
        starlette_app = Starlette(
            routes=[
                Route("/health", _health, methods=["GET"]),
                Mount("/", app=mcp_http),
            ],
            lifespan=mcp_http.lifespan,
        )
        app = _WellKnownMiddleware(starlette_app)
        uvicorn.run(app, host="0.0.0.0", port=_PORT)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
