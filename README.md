# agentsim-mcp

<!-- mcp-name: dev.agentsim/mcp -->

MCP server that exposes AgentSIM phone number tools to AI coding assistants — Claude Code, Cursor, Windsurf, and any other MCP-compatible host.

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

| Tool | Description |
|------|-------------|
| `provision_number` | Provision a phone number for an agent — returns number, session ID, expiry |
| `wait_for_otp` | Long-poll until an OTP arrives on the session (returns parsed code) |
| `get_messages` | List raw SMS messages received on a session |
| `release_number` | Release a session early (number returned to pool) |
| `list_numbers` | List all active sessions for this account |

## Auth

Set `AGENTSIM_API_KEY` in your environment. Get your key at [console.agentsim.dev](https://console.agentsim.dev).

## Supported Countries

US (more coming soon)
