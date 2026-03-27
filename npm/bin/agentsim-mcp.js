#!/usr/bin/env node

'use strict';

const { spawnSync, execFileSync } = require('child_process');

function hasCommand(cmd) {
  try {
    execFileSync(cmd, ['--version'], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

const args = process.argv.slice(2);

if (hasCommand('uvx')) {
  const result = spawnSync('uvx', ['agentsim-mcp', ...args], {
    stdio: 'inherit',
    env: process.env,
  });
  process.exit(result.status ?? 1);
} else if (hasCommand('python3') || hasCommand('python')) {
  const python = hasCommand('python3') ? 'python3' : 'python';
  const result = spawnSync(python, ['-m', 'agentsim_mcp.server', ...args], {
    stdio: 'inherit',
    env: process.env,
  });
  process.exit(result.status ?? 1);
} else {
  process.stderr.write(
    'AgentSIM MCP: Python runtime not found.\n' +
    'Install uv (recommended): https://docs.astral.sh/uv/getting-started/installation/\n' +
    'Or install Python 3.11+: https://python.org\n'
  );
  process.exit(1);
}
