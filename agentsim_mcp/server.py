"""AgentSIM MCP Server — challenge · policy · verdict tools for AI coding assistants."""

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
AgentSIM gives you authentication challenge tools for browser agents and controlled auth workflows.
It opens challenges (SMS OTP, email OTP, magic links, WebAuthn detect-and-halt), waits for verdicts,
and releases sessions when finished.

Typical workflow:
1. Call `open_challenge` with a channel (sms_otp | email_otp | magic_link | webauthn_required).
2. Trigger the challenge in your target service or controlled auth workflow.
3. Call `wait_for_verdict` with the session_id — it blocks until the outcome arrives or times out.
4. If the verdict is policy_denied or webauthn_required, stop — these are control-plane halts.
5. Call `release_number` to return the allocation to the pool when done.

Supported channels: sms_otp (programmable US numbers), email_otp (mock inject), magic_link (mock inject),
webauthn_required (detect-and-halt). Policy layer blocks third-party services by default; allow your
staging/development services through account policies. Check https://docs.agentsim.dev/policies-verdicts.

Legacy aliases: `provision_number` → `open_challenge`, `wait_for_otp` → `wait_for_verdict`.
Always release the session when finished, even on error, to avoid wasting pool capacity.
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
        "description": "Auth challenge tools for browser agents. Open a challenge, wait for a verdict, inspect evidence, and close the session. SMS is connector 0. Authorized use only, on apps you own.",
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

## 3. Run a challenge
Ask your AI assistant:
> "Use AgentSIM to test my staging phone OTP wall. Open a challenge, wait up to 120 seconds for the verdict, inspect messages if nothing arrives, and close the session."

The agent will:
1. Call open_challenge (sms_otp by default)
2. Enter the identifier on the owned auth wall
3. Call wait_for_verdict
4. Inspect messages if the verdict is a timeout
5. Call release_number to close the session

provision_number and wait_for_otp remain aliases.

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
def verify_phone_number(service: str = "staging auth flow", agent_id: str = "my-agent") -> str:
    """Step-by-step guide to run an auth challenge on a target workflow.

    Walks through the AgentSIM workflow: open_challenge · wait_for_verdict · release_number.
    """
    return f"""Follow these steps to run an auth challenge on {service}:

1. Check https://docs.agentsim.dev/supported-services if {service} is a third-party target. Google and Stripe are refused.
2. Call open_challenge with agent_id="{agent_id}" (channel defaults to sms_otp)
3. Enter the returned identifier on {service} (an app you own)
4. Call wait_for_verdict with the session_id
5. If wait_for_verdict times out, call get_messages and classify the outcome
6. Call release_number to close the session

provision_number and wait_for_otp are aliases for existing callers.

Important:
- Runtime integration is not a target-service support claim
- Always call release_number when done, even on error"""


@mcp.prompt()
def debug_verification_failure(error_message: str = "This phone number cannot be used for verification") -> str:
    """Diagnose why phone verification failed and suggest fixes.

    Common issues: VoIP blocking, carrier cold-start, number already used.
    """
    return f"""The user encountered this verification error: "{error_message}"

Diagnosis steps:
1. Use list_numbers to see active sessions and confirm the number is still leased
2. Use get_messages to check if any SMS was received but not parsed as OTP
3. Check the target UI for explicit phone rejection, CAPTCHA, hCaptcha, Arkose, or email-only fallback
4. Check https://docs.agentsim.dev/supported-services for known target behavior

Common causes:
- "Cannot be used for verification" → phone_rejected; the target may reject the current number class
- No OTP received → no_sms; the target may have silently suppressed SMS or provider logs may show no send
- CAPTCHA/puzzle before phone step → anti_bot_gate; this is not a phone-support verdict
- OTP expired → wait window too short or target delay; inspect raw messages before retrying
- Email-only path → email_only_flow; the tested flow did not exercise AgentSIM"""


# --- Tool input models ---

class OpenChallengeInput(BaseModel):
    agent_id: str = Field(description="Unique identifier for the agent requesting the challenge (e.g. 'checkout-bot').")
    channel: str = Field(default="sms_otp", description="Challenge channel: sms_otp | email_otp | magic_link | webauthn_required.")
    service_url: Optional[str] = Field(default=None, description="Optional URL of the target service for policy evaluation.")
    country: str = Field(default="US", description="ISO 3166-1 alpha-2 country code (sms_otp only). Supported: US.")
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, description="How long to hold the session (seconds). Default 1 hour.")
    webhook_url: Optional[str] = Field(default=None, description="Optional HTTPS URL to receive verdict via webhook instead of polling.")


class ProvisionInput(BaseModel):
    agent_id: str = Field(description="Unique identifier for the agent requesting the number (e.g. 'checkout-bot').")
    country: str = Field(default="US", description="ISO 3166-1 alpha-2 country code. Supported: US. More countries coming soon.")
    ttl_seconds: int = Field(default=3600, ge=60, le=86400, description="How long to hold the number (seconds). Default 1 hour.")
    webhook_url: Optional[str] = Field(default=None, description="Optional HTTPS URL to receive OTP via webhook instead of polling.")


class WaitForVerdictInput(BaseModel):
    session_id: str = Field(description="Session ID returned by open_challenge.")
    timeout_seconds: int = Field(default=60, ge=1, le=120, description="Maximum seconds to wait. Default 60.")


class WaitInput(BaseModel):
    session_id: str = Field(description="Session ID returned by provision_number.")
    timeout_seconds: int = Field(default=60, ge=1, le=120, description="Maximum seconds to wait. Default 60.")
    auto_reroute: bool = Field(default=True, description="On timeout, automatically swap to a fresh number on the same session and return retry instructions.")


class SessionInput(BaseModel):
    session_id: str = Field(description="Session ID returned by open_challenge or provision_number.")


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
async def open_challenge(input: OpenChallengeInput) -> dict[str, Any]:
    """Open an authentication challenge session.

    Supports multiple channels: sms_otp (programmable US number), email_otp (mock inbox),
    magic_link (mock inbox), and webauthn_required (detect-and-halt).

    Returns the challenge identifier (phone number or email address) and a session_id
    needed for all subsequent calls. The session is reserved for ttl_seconds.

    Next step: use the returned identifier on your target service to trigger the challenge,
    then call `wait_for_verdict` with the returned `session_id`.
    """
    if not _API_KEY:
        raise ToolError("AGENTSIM_API_KEY environment variable is not set.")

    body: dict[str, Any] = {
        "agent_id": input.agent_id,
        "channel": input.channel,
        "ttl_seconds": input.ttl_seconds,
    }
    if input.channel == "sms_otp":
        body["country"] = input.country
    if input.service_url:
        body["service_url"] = input.service_url
    if input.webhook_url:
        body["webhook_url"] = input.webhook_url

    data = await _request("POST", "/sessions", json=body)

    result: dict[str, Any] = {
        "session_id": data["session_id"],
        "channel": data.get("channel", input.channel),
        "agent_id": data["agent_id"],
        "expires_at": data["expires_at"],
    }

    if input.channel == "sms_otp":
        result["number"] = data["number"]
        result["country"] = data["country"]
        result["next_step"] = f"Use `{data['number']}` on your target service, then call wait_for_verdict(session_id='{data['session_id']}')"
    elif input.channel in ("email_otp", "magic_link"):
        result["inbox_address"] = data.get("inbox_address", data.get("email"))
        result["next_step"] = f"Use `{result['inbox_address']}` on your target service, then call wait_for_verdict(session_id='{data['session_id']}')"
    else:
        result["next_step"] = f"Call wait_for_verdict(session_id='{data['session_id']}') to check for policy or WebAuthn verdicts"

    return result


@mcp.tool()
async def provision_number(input: ProvisionInput) -> dict[str, Any]:
    """Open an SMS challenge session (alias for open_challenge with channel=sms_otp).

    DEPRECATED: Use `open_challenge` with channel="sms_otp" instead. This tool is kept
    for backward compatibility with existing MCP clients.

    Returns the phone number (e164 format) and a session_id needed for all
    subsequent calls. The session is reserved for ttl_seconds.

    Next step: use the returned `number` on an app you own to trigger the wall,
    then call `wait_for_verdict` (or the `wait_for_otp` alias) with the `session_id`.
    """
    if not _API_KEY:
        raise ToolError("AGENTSIM_API_KEY environment variable is not set.")

    body: dict[str, Any] = {
        "agent_id": input.agent_id,
        "country": input.country,
        "ttl_seconds": input.ttl_seconds,
        "channel": "sms_otp",
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
async def wait_for_verdict(input: WaitForVerdictInput) -> dict[str, Any]:
    """Block until a challenge verdict arrives for this session.

    Polls the AgentSIM API for up to `timeout_seconds`. Returns the structured verdict,
    which may include:
    - otp_code: the parsed OTP (for sms_otp, email_otp channels)
    - magic_link: the extracted HTTPS URL (for magic_link channel)
    - webauthn_required: true if WebAuthn/passkey was detected (detect-and-halt)
    - policy_denied: true if the service_url is blocked by account policy

    Always call `release_number` after processing the verdict.
    """
    try:
        data = await _request(
            "POST",
            f"/sessions/{input.session_id}/wait",
            json={"timeout_seconds": input.timeout_seconds},
        )
    except ToolError as exc:
        if "otp_timeout" in str(exc) or "challenge_timeout" in str(exc):
            raise ToolError(
                f"No verdict received within {input.timeout_seconds}s. "
                "Check that you entered the correct identifier on the target service. "
                "You can retry wait_for_verdict or call release_number to free the session."
            ) from exc
        raise

    result: dict[str, Any] = {
        "session_id": input.session_id,
        "received_at": data.get("received_at"),
    }

    if "otp_code" in data:
        result["otp_code"] = data["otp_code"]
        result["from"] = data.get("from_number") or data.get("from")
    if "magic_link" in data:
        result["magic_link"] = data["magic_link"]
    if data.get("webauthn_required"):
        result["webauthn_required"] = True
        result["verdict"] = "webauthn_required"
    if data.get("policy_denied"):
        result["policy_denied"] = True
        result["verdict"] = "policy_denied"

    result["next_step"] = "Use the verdict in your workflow, then call release_number to free the session."
    return result


@mcp.tool()
async def wait_for_otp(input: WaitInput) -> dict[str, Any]:
    """Block until an SMS verdict arrives for this session (alias for wait_for_verdict).

    DEPRECATED: Use `wait_for_verdict` instead. This tool is kept for backward
    compatibility with existing MCP clients.

    Polls the AgentSIM API for up to `timeout_seconds`. Returns the OTP code
    when the SMS challenge resolves.

    If the verdict does not arrive in time, raises a ToolError with advice on retrying.
    Always call `release_number` after you have used the verdict.
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
    wait_for_verdict. Does NOT mark the OTP as consumed.
    """
    data = await _request("GET", f"/sessions/{input.session_id}/messages")
    return {
        "messages": data.get("messages", []),
        "has_more": data.get("has_more", False),
    }


@mcp.tool()
async def release_number(input: SessionInput) -> dict[str, Any]:
    """Close a challenge session.

    Always call this when you are done — even on error — so the session does
    not keep consuming pool capacity.
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
    """List active challenge sessions, optionally filtered by agent_id.

    Use this to check for leaked sessions or inspect what is currently active.
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
                "description": "Auth challenge tools for browser agents. Open a challenge, wait for a verdict, inspect evidence, and close the session.",
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

        mcp_http = mcp.http_app(stateless_http=True)

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
