# agentsim-mcp

<!-- mcp-name: dev.agentsim/mcp -->

**Availability:** Live SMS is self-serve for owned public HTTPS services after exact-origin verification and an allow policy. Hobby includes 10 live US SMS sessions per UTC month, with one active live session per account and no card required. Billing shows current paid terms before checkout and preserves any existing agreement. Check [current access and channel support](https://docs.agentsim.dev/availability) before using live examples.

MCP server that exposes AgentSIM challenge tools to AI coding assistants: Codex CLI, Claude Code, Cursor, Windsurf, and any other MCP-compatible host. Primary tools: `open_challenge`, `wait_for_verdict`. Aliases: `provision_number`, `wait_for_otp`.

## Setup

For **Codex CLI**, follow [Connect Codex](https://docs.agentsim.dev/mcp/connect#codex-cli). It covers key handling, the SMS wait timeout, and browser access. Then use the [complete phone sign-in prompt](https://docs.agentsim.dev/mcp/recipes#complete-a-phone-sign-in).

### Claude Code

```bash
claude mcp add agentsim -e AGENTSIM_API_KEY=asm_live_xxx -- uvx agentsim-mcp
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agentsim": {
      "command": "uvx",
      "args": ["agentsim-mcp"],
      "env": {
        "AGENTSIM_API_KEY": "asm_live_xxx"
      }
    }
  }
}
```

### Cursor / Windsurf

Add `agentsim-mcp` as a stdio MCP server with `AGENTSIM_API_KEY` in the environment config.

### Remote (no install)

Connect directly to the hosted MCP server without installing anything locally:

```json
{
  "mcpServers": {
    "agentsim": {
      "type": "streamable-http",
      "url": "https://mcp.agentsim.dev/mcp",
      "headers": {
        "x-api-key": "asm_live_..."
      }
    }
  }
}
```

The hosted endpoint uses stateless HTTP and does not issue `mcp-session-id` headers. The `session_id` returned by AgentSIM tools identifies a challenge and remains valid across tool calls.

## Tools

### Control-Plane Nouns (Recommended)

| Tool | Description |
|------|-------------|
| `identify_agent` | Add a stable agent ID to the console without opening a challenge, sending SMS, or using allowance |
| `open_challenge` | Open an authentication challenge session for a required owned `service_url`; accepts channel (sms_otp \| email_otp \| magic_link \| webauthn_required), returns session ID + identifier |
| `wait_for_verdict` | Long-poll for the challenge verdict — returns structured outcome including otp_code, magic_link, or webauthn_required; policy denial fails on open |
| `get_messages` | Read SMS metadata and parsed codes; reading codes consumes them |
| `release_number` | Release a session early (allocation returned to pool) |
| `list_numbers` | List all active sessions for this account |

### Legacy Aliases (Backward Compatibility)

| Tool | Maps to | Description |
|------|---------|-------------|
| `provision_number` | `open_challenge(channel=sms_otp)` | Provision a temporary programmable US number for SMS OTP — kept for backward compatibility |
| `wait_for_otp` | `wait_for_verdict` | Legacy wait with automatic extension after timeout by default; number may be unchanged |

## Auth

For stdio, set `AGENTSIM_API_KEY` in the process environment. For hosted HTTP, every request must send its own `x-api-key`; the server validates and forwards that caller-scoped key. Get a key at [console.agentsim.dev](https://console.agentsim.dev).

## Supported Countries

US
