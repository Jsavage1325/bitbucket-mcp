# Bitbucket MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives Claude Code (and any MCP-compatible AI agent) full access to the Bitbucket Cloud REST API — pull requests, diffs, comments, reviews, and more.

## Tools

| Tool | Description |
|---|---|
| `list_repos` | List repositories in a workspace |
| `list_open_prs` | List open pull requests for a repo |
| `get_open_pr` | Get the open PR for the current branch |
| `get_pr` | Fetch a PR by ID |
| `get_pr_diff` | Unified diff for a PR |
| `get_pr_diffstat` | Per-file change statistics for a PR |
| `get_pr_comments` | All comments on a PR |
| `get_unresolved_pr_comments` | Unresolved comments only (optionally inline only) |
| `post_pr_comment` | Post a general or inline comment |
| `resolve_pr_comment` | Mark a comment as resolved |
| `approve_pr` | Approve a PR |
| `decline_pr` | Decline a PR |
| `merge_pr` | Merge a PR (`merge_commit` or `squash`) |
| `create_pr` | Open a new PR |
| `get_commit_diff` | Diff for a commit, range, or list of commits |

## Installation

```bash
uvx mini-bitbucket-mcp
```

Register globally with Claude Code:

```bash
# If you use the bb CLI (credentials auto-detected)
claude mcp add --scope user bitbucket -- uvx mini-bitbucket-mcp

# Or pass a token directly
claude mcp add --scope user -e BITBUCKET_ACCESS_TOKEN=<token> bitbucket -- uvx mini-bitbucket-mcp

```

`--scope user` makes the server available in every project on your machine.

### Project-level config

Drop a `.mcp.json` at your repo root:

```json
{
  "mcpServers": {
    "bitbucket": {
      "command": "uvx",
      "args": ["bitbucket-mcp-server"],
      "env": {
        "BITBUCKET_ACCESS_TOKEN": "<your-token>"
      }
    }
  }
}
```

## Authentication

The server tries credentials in this order:

| Priority | Source | Notes |
|---|---|---|
| 1 | `BITBUCKET_ACCESS_TOKEN` env var | Bitbucket App Password or OAuth token |
| 2 | `~/.config/bb/tokens.json` | Written by `bb auth login` |
| 3 | `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` | Atlassian API token (Basic auth) |

Generate an App Password at **Bitbucket → Personal settings → App passwords** with `Repositories: Read` and `Pull requests: Read/Write` scopes.

## Usage with Claude Code

Once registered, Claude Code will automatically use the Bitbucket tools in any repo whose `git remote` points to `bitbucket.org`. Add this to `~/.claude/CLAUDE.md` to make it explicit:

```markdown
A `bitbucket` MCP server is registered globally. Use it for all Bitbucket tasks (PRs, comments, diffs, reviews).

Derive `workspace` and `repo` from `git remote get-url origin` — format: `git@bitbucket.org:{workspace}/{repo}.git`.
```

## Local development

```bash
make install   # install dependencies
make lint      # ruff check + format
make test      # unit tests
make run       # start server on stdio
```
