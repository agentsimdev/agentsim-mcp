# agentsim-mcp

<!-- mcp-name: dev.agentsim/mcp -->

MCP server that exposes AgentSIM challenge tools to AI coding assistants: Claude Code, Cursor, Windsurf, and any other MCP-compatible host. Primary tools: `open_challenge`, `wait_for_verdict`. Aliases: `provision_number`, `wait_for_otp`.

## Setup

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

## Tools

### Control-Plane Nouns (Recommended)

| Tool | Description |
|------|-------------|
| `open_challenge` | Open an authentication challenge session — accepts channel (sms_otp \| email_otp \| magic_link \| webauthn_required), returns session ID + identifier (phone number or email address) |
| `wait_for_verdict` | Long-poll for the challenge verdict — returns structured outcome including otp_code, magic_link, webauthn_required, or policy_denied |
| `get_messages` | List raw SMS messages received on a session |
| `release_number` | Release a session early (allocation returned to pool) |
| `list_numbers` | List all active sessions for this account |

### Legacy Aliases (Backward Compatibility)

| Tool | Maps to | Description |
|------|---------|-------------|
| `provision_number` | `open_challenge(channel=sms_otp)` | Provision a temporary programmable US number for SMS OTP — kept for backward compatibility |
| `wait_for_otp` | `wait_for_verdict` | Long-poll until an OTP arrives — kept for backward compatibility |

## Auth

Set `AGENTSIM_API_KEY` in your environment. Get your key at [console.agentsim.dev](https://console.agentsim.dev).

## Supported Countries

US (more coming soon)
