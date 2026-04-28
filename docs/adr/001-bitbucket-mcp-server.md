# ADR-001: Bitbucket MCP Server via FastMCP

**Status:** Proposed
**Date:** 2026-04-27
**Deciders:** Data Engineering

---

## Context

The `bb` CLI is a drop-in git replacement that adds Bitbucket Cloud features (pull requests,
auth, raw API access). It is already installed and authenticated on developer workstations
across the team via `bb auth login`, with credentials stored at
`~/.config/bb/config.toml['auth']['password']`.

Several projects — starting with `agentic-code-reviewer` — duplicate the same Bitbucket
interaction patterns:

- Reading auth tokens from the `bb` config file.
- Listing repositories in a workspace.
- Fetching open PRs, diffs, diffstats, and comments.
- Posting inline review comments and summary comments.
- Approving, merging, or declining PRs.

Today this logic lives as a hand-rolled `BitbucketClient` in
`agentic-code-reviewer/src/lib/bitbucket/client.py`. Any new project that needs Bitbucket
access must either copy that client, reach for the full `bb` subprocess, or call the REST
API directly — all of which scatter auth and retry logic across repos.

The **`bitbucket-sdk`** package (authored by the team) provides a clean REST API client
with built-in retry handling, typed responses, and both Bearer and Basic auth strategies.
The MCP server uses this SDK directly rather than bundling its own HTTP client.

Claude Code and other AI-assisted development tools use the **Model Context Protocol (MCP)**
to expose structured capabilities to agents. An MCP server for Bitbucket would mean every
Claude-assisted workflow across the team can call `list_open_prs`, `get_pr_diff`,
`post_comment`, etc., without any project needing to bundle its own Bitbucket client.

**FastMCP** (`fastmcp>=2.0`) is a Python framework that reduces an MCP server to decorated
functions — no protocol boilerplate. It matches the team's preference for Python, `uv`, and
`ruff`, and supports both `stdio` (local Claude Code) and `streamable-http` transports.

---

## Decision

Build a **Bitbucket MCP server** using FastMCP, distributed as a standalone Python package
in this repository.

### Auth model

The server resolves credentials at startup and passes them to the `bitbucket-sdk`
`BitbucketClient`. Two auth strategies are supported, selected by priority:

| Priority | Credential source | Auth strategy | Typical environment |
|---|---|---|---|
| 1 | `BITBUCKET_ACCESS_TOKEN` env var | Bearer token | All environments; set per-user in MCP client config |
| 2 | `~/.config/bb/config.toml` `auth.password` | Bearer token | Developer workstations (`bb auth login`) |
| 3 | `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` env vars | HTTP Basic | Environments with only an Atlassian API token |

```python
def _resolve_auth() -> dict:
    if token := os.getenv("BITBUCKET_ACCESS_TOKEN"):
        return {"access_token": token}
    config_path = Path.home() / ".config" / "bb" / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            if password := tomllib.load(f).get("auth", {}).get("password"):
                return {"access_token": password}
    if (email := os.getenv("BITBUCKET_EMAIL")) and (token := os.getenv("BITBUCKET_API_TOKEN")):
        return {"email": email, "api_token": token}
    raise RuntimeError(
        "No Bitbucket credentials found. Set BITBUCKET_ACCESS_TOKEN, run 'bb auth login', "
        "or set BITBUCKET_EMAIL and BITBUCKET_API_TOKEN."
    )
```

The resolved credentials are passed directly to `BitbucketClient(**_resolve_auth())`; the
server never logs or returns credential values in tool output.

### MCP tools exposed

| Tool | Bitbucket REST endpoint | Maps from |
|---|---|---|
| `list_repos(workspace, updated_since?)` | `GET /repositories/{workspace}` | `BitbucketClient.list_repos` |
| `list_open_prs(workspace, repo)` | `GET /repositories/{workspace}/{repo}/pullrequests?state=OPEN` | `BitbucketClient.list_open_prs` |
| `get_pr(workspace, repo, pr_id)` | `GET /repositories/{workspace}/{repo}/pullrequests/{id}` | `bb pr view` |
| `get_pr_diff(workspace, repo, pr_id)` | `GET /repositories/{workspace}/{repo}/pullrequests/{id}/diff` | `BitbucketClient.get_pr_diff` |
| `get_pr_diffstat(workspace, repo, pr_id)` | `GET /repositories/{workspace}/{repo}/pullrequests/{id}/diffstat` | `BitbucketClient.get_pr_diffstat` |
| `get_pr_comments(workspace, repo, pr_id)` | `GET /repositories/{workspace}/{repo}/pullrequests/{id}/comments` | `BitbucketClient.get_pr_comments` |
| `post_pr_comment(workspace, repo, pr_id, body, file_path?, line?)` | `POST /repositories/{workspace}/{repo}/pullrequests/{id}/comments` | `BitbucketClient.post_summary_comment` / `post_review_comments` |
| `approve_pr(workspace, repo, pr_id)` | `POST /repositories/{workspace}/{repo}/pullrequests/{id}/approve` | `bb pr approve` |
| `decline_pr(workspace, repo, pr_id)` | `POST /repositories/{workspace}/{repo}/pullrequests/{id}/decline` | `bb pr decline` |
| `merge_pr(workspace, repo, pr_id, strategy?)` | `POST /repositories/{workspace}/{repo}/pullrequests/{id}/merge` | `bb pr merge` |
| `create_pr(workspace, repo, title, source_branch, destination_branch, description?)` | `POST /repositories/{workspace}/{repo}/pullrequests` | `bb pr create` |

### Server entry point

```python
# src/bitbucket_mcp/server.py
from fastmcp import FastMCP

mcp = FastMCP("bitbucket")

@mcp.tool()
def list_open_prs(workspace: str, repo: str) -> list[dict]:
    """List all open pull requests for a repository."""
    ...

if __name__ == "__main__":
    mcp.run()  # defaults to stdio transport
```

### Transport

`stdio` in all environments. The MCP client (Claude Code on developer workstations, or the
DeltaGuard agent on EC2) starts the server as a subprocess per session and manages its
lifecycle. Registered as `uvx bitbucket-mcp-server` (or a local path during development).

Each user or agent runs their own instance with their own token — there is no shared
long-running server process.

### Retry and rate-limit handling

Handled by the `bitbucket-sdk` internally: tenacity with exponential backoff on
`requests.exceptions.RequestException` and `HTTP 429`, up to 5 attempts for reads and
3 for writes. No retry logic is required in the MCP server layer.

### CI/CD pipeline

`bitbucket-pipelines.yml` runs quality gates on every PR and on merge to `main`.

| Event | Steps |
|---|---|
| PR opened / updated | ruff lint + format check, unit tests, pip-audit |
| Merge to `main` | ruff lint + format check, full test suite, pip-audit, `uv build` |

No cloud credentials or infrastructure steps are required in the pipeline.

### Project structure

```
bitbucket-mcp-server/
├── src/
│   └── bitbucket_mcp/
│       ├── __init__.py
│       ├── server.py       # FastMCP app + tool definitions
│       └── auth.py         # _resolve_auth() — env var + bb config fallback chain
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   └── adr/
├── agents.md
├── bitbucket-pipelines.yml # quality gates: lint, test, pip-audit, build
├── pyproject.toml          # fastmcp, bitbucket-sdk; entry_point: bitbucket-mcp-server
├── .env.example
├── Makefile
└── RUNBOOK.md
```

---

## Alternatives Considered

| Option | Reason Not Chosen |
|---|---|
| Shared PyPI library (`citywire-bitbucket-client`) | Does not integrate with Claude Code / MCP. AI agents cannot call library functions directly; they need MCP tools. Still requires each consuming project to initialise and wire the client. |
| Subprocess wrapper calling `bb` CLI directly | The `bb` CLI does not support structured JSON output on all commands, making parsing fragile. The REST API gives typed, paginated responses and is already battle-tested in `agentic-code-reviewer`. |
| Anthropic's official Bitbucket MCP (via `mcp__claude_ai_Atlassian`) | Cloud-hosted, requires OAuth SSO via claude.ai — not suitable for EC2 worker processes or private Bitbucket workspaces behind a corporate token. |
| FastAPI REST proxy | An HTTP service adds a deployment target, auth layer, and network hop with no benefit over MCP for the AI-agent use case. For non-AI consumers, `bb` CLI already covers the need. |
| LangChain Bitbucket toolkit | Heavy dependency; no FastMCP/MCP integration; agent framework lock-in. |
| Shared service-account token on EC2 | All users sharing one token creates a blast radius — if the token is revoked or rotated, all consumers break simultaneously. Per-user tokens isolate failures. |
| Long-running `streamable-http` server on EC2 | Adds a managed process (systemd, supervisor) and a network port with no benefit over per-invocation `stdio` startup. `stdio` startup cost is ~200 ms once per session, which is acceptable. |

---

## Consequences

**Positive:**
- Auth boilerplate implemented once; all projects inherit it by adding the MCP server to
  their Claude Code config.
- `agentic-code-reviewer`'s hand-rolled `BitbucketClient` can be deleted — replaced by
  either the `bitbucket-sdk` directly or a call to this MCP server, removing ~190 lines
  of duplicated HTTP client code.
- New projects (PR push skill, code search agent, pipeline monitor) can use Bitbucket
  operations immediately with no client code of their own.
- FastMCP handles MCP protocol compliance, JSON-schema generation from type hints, and
  transport negotiation — no bespoke protocol work required.
- `uvx bitbucket-mcp-server` gives a zero-install developer experience once published.
- The pipeline enforces lint and format checks on every PR, preventing style drift without
  requiring manual reviewer attention.
- No cloud infrastructure to provision or maintain — zero operational overhead.

**Negative:**
- MCP adds a process boundary between the agent and the Bitbucket API. Startup latency
  for `stdio` transport is ~200 ms per Claude Code session (one-time, not per call).
- The server must be kept up-to-date with FastMCP API changes. FastMCP 2.x has a stable
  tool decorator API; pin the minor version.
- The existing `BitbucketClient` in `agentic-code-reviewer` cannot be removed until
  that project is migrated to use the MCP server — there will be a brief period of
  parallel implementations.
- Each user is responsible for providing and rotating their own `BITBUCKET_ACCESS_TOKEN`.
  There is no central rotation mechanism.

---

## Non-Functional Requirements

| Concern | Target |
|---|---|
| Latency (read tools) | p95 < 2 s (Bitbucket API is the bottleneck) |
| Startup latency | ~200 ms per session (one-time stdio subprocess start, not per call) |
| Cost | Zero — no cloud infrastructure; runs as a local subprocess |
| Auth security | Token resolved from env var or local file; never logged or returned in tool output |
| Scaling | Per-user process; Bitbucket API rate limits (1,000 req/hr per token) are the ceiling |
