# Bitbucket MCP Server — Runbook

## Overview

The Bitbucket MCP server runs as a local subprocess on each user's machine (or EC2 worker).
There is no shared cloud infrastructure — every consumer brings their own Bitbucket token
and runs their own instance.

---

## Setup

### Developer workstations

Install and register the server with Claude Code:

```bash
# Option A: published package
uvx bitbucket-mcp-server

# Option B: local development checkout
uv run bitbucket-mcp-server
```

Add to `~/.claude/mcp_servers.json`:

```json
{
  "bitbucket": {
    "command": "uvx",
    "args": ["bitbucket-mcp-server"],
    "env": {
      "BITBUCKET_ACCESS_TOKEN": "your-personal-token"
    }
  }
}
```

Alternatively, if `bb auth login` has already been run, the server will read credentials
from `~/.config/bb/config.toml` automatically and no env var is needed.

### EC2 workers (e.g. DeltaGuard)

The agent framework on EC2 registers the MCP server the same way as a local machine —
no long-running process or systemd unit required. Set `BITBUCKET_ACCESS_TOKEN` to a
service account token in the agent's environment:

```bash
export BITBUCKET_ACCESS_TOKEN=<service-account-token>
```

Or configure it in the agent's MCP client config, equivalent to the developer example above.

---

## Credential options

| Priority | Source | When to use |
|---|---|---|
| 1 | `BITBUCKET_ACCESS_TOKEN` env var | All environments; explicit per-user token |
| 2 | `~/.config/bb/config.toml` | Developer workstations with `bb auth login` already run |
| 3 | `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` env vars | Atlassian API token (Basic auth) |

Tokens are never logged or returned in tool output.

---

## Local development

```bash
make install      # install dependencies
make lint         # ruff check + format check
make test         # unit tests
make run          # start server (stdio transport, for use with Claude Code)
```

---

## Checking the server works

```bash
# Confirm the server starts and lists its tools
BITBUCKET_ACCESS_TOKEN=test uv run python -c "
import asyncio
from bitbucket_mcp.server import mcp
async def main():
    tools = await mcp.list_tools()
    for t in tools: print(t.name)
asyncio.run(main())
"
```

---

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: No Bitbucket credentials found` | No token in env or `bb` config | Set `BITBUCKET_ACCESS_TOKEN` or run `bb auth login` |
| `AuthenticationError` on API call | Token expired or revoked | Generate a new token at Bitbucket → Personal settings → App passwords |
| `RateLimitError` | Exceeded 1,000 req/hr | Wait for the rate limit window to reset (~1 hr) |
| `NotFoundError` on a known repo | Wrong workspace or repo slug | Check workspace/repo slugs match Bitbucket exactly |
# Smoke test change
