<p align="center">
  <a href="https://agentsim.dev">
    <img src="https://agentsim.dev/logo.svg" alt="AgentSIM" width="80" />
  </a>
</p>

<h1 align="center">agentsim-mcp</h1>

<p align="center">
  <strong>MCP server for AgentSIM — give AI coding assistants real phone numbers</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/agentsim-mcp/"><img src="https://img.shields.io/pypi/v/agentsim-mcp?color=%2334D058&label=pypi" alt="PyPI version"></a>
  <a href="https://www.npmjs.com/package/@agentsim/mcp-server"><img src="https://img.shields.io/npm/v/@agentsim/mcp-server?color=%2334D058&label=npm" alt="npm version"></a>
  <a href="https://github.com/agentsimdev/agentsim-mcp/blob/main/LICENSE"><img src="https://img.shields.io/github/license/agentsimdev/agentsim-mcp" alt="License"></a>
</p>

<p align="center">
  <a href="https://docs.agentsim.dev/mcp">Docs</a> ·
  <a href="https://agentsim.dev/dashboard">Dashboard</a> ·
  <a href="https://github.com/agentsimdev/agentsim-examples">Examples</a>
</p>

---

MCP server that exposes AgentSIM phone number tools to AI coding assistants. Works with Claude Code, Cursor, Windsurf, and any MCP-compatible host.

Real SIM-backed numbers. No VoIP. Carrier lookup returns `mobile`.

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

Connect directly to the hosted server — no local installation required:

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
| `provision_number` | Lease a real mobile phone number — returns number + session ID |
| `wait_for_otp` | Long-poll until an OTP arrives (returns parsed code) |
| `get_messages` | List raw SMS messages received on a session |
| `release_number` | Release a session early (number returned to pool) |
| `list_numbers` | List all active sessions for your account |

### Typical Workflow

```
1. provision_number  →  get phone number + session_id
2. Use the number on target service to trigger SMS
3. wait_for_otp      →  get the OTP code
4. Use the OTP in your workflow
5. release_number    →  return number to pool
```

If `wait_for_otp` returns `status=carrier_retry_required`, a replacement number has been provisioned on the same session. Re-enter the new number on the target service, then call `wait_for_otp` again.

## Authentication

Set `AGENTSIM_API_KEY` in your environment. Get your key at [agentsim.dev/dashboard](https://agentsim.dev/dashboard).

## Self-Hosting

### Docker / Railway

```toml
# railway.toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python -m agentsim_mcp.server --http"
healthcheckPath = "/health"
```

### Manual

```bash
pip install agentsim-mcp
AGENTSIM_API_KEY=asm_live_xxx agentsim-mcp --sse
```

## Pricing

- **Hobby**: 10 free sessions/month
- **Builder**: $0.99/session
- Sessions that time out are **not billed**

## Links

- [Documentation](https://docs.agentsim.dev/mcp)
- [Python SDK](https://github.com/agentsimdev/agentsim-python)
- [TypeScript SDK](https://github.com/agentsimdev/agentsim-typescript)
- [Examples](https://github.com/agentsimdev/agentsim-examples)

## License

[MIT](LICENSE)
