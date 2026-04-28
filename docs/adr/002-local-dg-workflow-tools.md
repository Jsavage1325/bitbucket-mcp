# ADR-002: Local DeltaGuard Workflow Tools

**Status:** Proposed
**Date:** 2026-04-27
**Deciders:** Data Engineering
**Extends:** ADR-001 (Bitbucket MCP Server — architecture, infrastructure, and pipeline)

---

## Context

ADR-001 defined the foundational MCP tools for Bitbucket: listing repos and PRs,
fetching diffs and comments, posting comments, and basic PR lifecycle actions
(approve / merge / decline / create).

The DeltaGuard (DG) code-review agent currently runs only on the EC2 worker, triggered
by Bitbucket webhooks on every PR commit. Developers have no way to run DG locally
against their own PR before pushing — they must wait for the worker poll cycle
(up to 60 s) and cannot iterate on the review locally.

Additionally, the existing `resolve-pr-comments` Claude Code skill — which fetches
unresolved DG comments and tasks an agent to fix them — currently runs via `bb` subprocess
calls and ad-hoc Python. These operations need first-class MCP tools so:

1. Any skill or agent can locally trigger a full DG review cycle against an open PR.
2. An agent can discover which comments are still unresolved (i.e., not yet addressed).
3. An agent can mark individual comments resolved after it has fixed the underlying issue.
4. Commit-level diffs can be fetched independently of a PR, enabling targeted analysis
   of specific commits (e.g., to explain a change, audit a hotfix, or review a squash).

---

## Decision

Add four new MCP tools to the Bitbucket MCP server defined in ADR-001.

---

### Tool 1 — `get_open_pr`

**Purpose:** Find the open PR for a given branch (defaults to the current git branch).
This is the entry point for the local DG workflow: an agent calls it to obtain the
`pr_id` needed by all other DG tools without the developer having to look it up manually.

**Endpoint:**
```
GET /repositories/{workspace}/{repo}/pullrequests
  ?state=OPEN
  &q=source.branch.name="{branch}"
```

**Signature:**
```python
@mcp.tool()
def get_open_pr(workspace: str, repo: str, branch: str | None = None) -> dict | None:
    """Return the open PR for the given branch, or None if no open PR exists.

    When branch is omitted the current git branch is detected via
    subprocess.check_output(["git", "branch", "--show-current"]).
    """
```

**Return value:** Full PR object (title, id, description, author, source/destination
branches, reviewers, links) or `None`.

**Local DG trigger flow:**
```
get_open_pr(workspace, repo)           → pr_id
get_pr_diff(workspace, repo, pr_id)    → diff text
get_pr_diffstat(workspace, repo, pr_id)
get_pr_comments(workspace, repo, pr_id)
→ build_prompt → claude --print → post_pr_comment
```

The tool itself does not run the review — it provides the PR handle. The DG trigger
flow above is assembled by the calling agent or skill, keeping the MCP tools composable.

---

### Tool 2 — `get_unresolved_pr_comments`

**Purpose:** Return only the comments on a PR that are not yet resolved. Used by the
`resolve-pr-comments` skill to discover what DG (or any reviewer) has flagged and an
agent has not yet addressed.

**Endpoint:**
```
GET /repositories/{workspace}/{repo}/pullrequests/{id}/comments
```
Filtered client-side: `[c for c in comments if not c.get("resolved", False)]`

Bitbucket comment objects include:
- `id` — required to resolve the comment (Tool 4)
- `resolved` — `true` / `false`
- `inline` — `{path, from, to}` for inline comments; absent for general comments
- `content.raw` — comment text
- `parent.id` — set if this is a reply; absent for top-level comments

**Signature:**
```python
@mcp.tool()
def get_unresolved_pr_comments(
    workspace: str,
    repo: str,
    pr_id: int,
    inline_only: bool = False,
) -> list[dict]:
    """Return all unresolved comments on a PR.

    Set inline_only=True to restrict to inline file/line comments (i.e. DG review
    comments), excluding general PR-level comments.
    """
```

**Filtering logic:**
```python
comments = client.get_pr_comments(workspace, repo, pr_id)
unresolved = [c for c in comments if not c.get("resolved", False)]
if inline_only:
    unresolved = [c for c in unresolved if c.get("inline")]
return unresolved
```

---

### Tool 3 — `resolve_pr_comment`

**Purpose:** Mark a single PR comment as resolved. Called by the agent after it has
committed a fix for the issue raised in that comment.

**Endpoint:**
```
PUT /repositories/{workspace}/{repo}/pullrequests/{id}/comments/{comment_id}
Body: {"resolved": true}
```

**Signature:**
```python
@mcp.tool()
def resolve_pr_comment(
    workspace: str,
    repo: str,
    pr_id: int,
    comment_id: int,
) -> dict:
    """Mark a PR comment as resolved. Returns the updated comment object."""
```

**Batch convenience:** The calling agent iterates over the list from
`get_unresolved_pr_comments` and calls `resolve_pr_comment` once per comment it has
addressed. No bulk endpoint exists in Bitbucket v2.0, so single-comment resolution
is the correct primitive. The per-comment granularity also means a partially-completed
agent run leaves the remaining comments unresolved — which is the correct state.

**Retry policy:** Same as other write operations — tenacity with exponential backoff on
`httpx.RequestError`, up to 3 attempts. `HTTP 404` (comment not found or already deleted)
is surfaced as a `BitbucketError` rather than retried.

---

### Tool 4 — `get_commit_diff`

**Purpose:** Fetch the unified diff for one or more commits. Useful for targeted analysis
of a specific commit (e.g., to explain a hotfix, audit a squash merge, or analyse a
cherry-pick) without the full PR context.

**Endpoints:**

| Input | Endpoint | Notes |
|---|---|---|
| Single commit hash | `GET /repositories/{workspace}/{repo}/diff/{hash}` | Diff of commit vs its first parent |
| Two commits / range | `GET /repositories/{workspace}/{repo}/diff/{base}..{tip}` | All changes reachable from tip but not base |
| List of commits | One `GET /diff/{hash}` per hash, results concatenated | No multi-commit bulk endpoint in BB v2.0 |

**Signature:**
```python
@mcp.tool()
def get_commit_diff(
    workspace: str,
    repo: str,
    commits: str | list[str],
) -> str:
    """Return the unified diff for one or more commits.

    commits can be:
      - A single hash string: "abc123"
      - A git range string:   "abc123..def456"
      - A list of hashes:     ["abc123", "def456", "789abc"]

    For a list, each commit's diff is fetched individually and concatenated
    with a header line ("--- commit {hash} ---") for readability.
    """
```

**Implementation notes:**
- The diff endpoint returns `text/plain` (not JSON); handled identically to the existing
  `get_pr_diff` method in `BitbucketClient`.
- For a list of commits the calls are made sequentially (not concurrent) to avoid
  hammering the rate limit. The Bitbucket API caps at 1,000 req/hr; a list of ≤ 50
  commits is a safe upper bound enforced by a `ValueError` in the tool.
- Range strings (`abc..def`) are passed through directly to the endpoint; the server
  does not parse or validate git range syntax.

---

## Impact on ADR-001 Tool Table

The four tools above are additive. The full tool surface of the server after both ADRs:

| # | Tool | Category |
|---|---|---|
| 1 | `list_repos` | Discovery |
| 2 | `list_open_prs` | Discovery |
| 3 | `get_open_pr` *(new)* | Discovery / DG local trigger |
| 4 | `get_pr` | PR read |
| 5 | `get_pr_diff` | PR read |
| 6 | `get_pr_diffstat` | PR read |
| 7 | `get_pr_comments` | PR read |
| 8 | `get_unresolved_pr_comments` *(new)* | PR read / DG workflow |
| 9 | `post_pr_comment` | PR write |
| 10 | `resolve_pr_comment` *(new)* | PR write / DG workflow |
| 11 | `approve_pr` | PR lifecycle |
| 12 | `decline_pr` | PR lifecycle |
| 13 | `merge_pr` | PR lifecycle |
| 14 | `create_pr` | PR lifecycle |
| 15 | `get_commit_diff` *(new)* | Commit read |

---

## Alternatives Considered

| Option | Reason Not Chosen |
|---|---|
| `get_open_pr` — detect branch from git inside the tool | Git is not always available in the MCP server process (e.g., HTTP transport on EC2). Branch detection is implemented as a best-effort fallback only; callers that know the branch should pass it explicitly. |
| `get_unresolved_pr_comments` — server-side filter via Bitbucket query param | Bitbucket v2.0 does not support `?q=resolved=false` on the comments endpoint. Filtering must happen client-side after fetching all comments. |
| `resolve_pr_comments` (bulk tool resolving all unresolved comments) | Overly coarse — an agent may fix some issues and not others in one pass. Per-comment resolution is the correct primitive; the calling agent controls which comments to mark resolved. |
| `get_commit_diff` — use `bb diff {hash}` subprocess | Same objection as ADR-001: `bb` does not output structured data. For diffs the text/plain REST response is equivalent and already handled by `BitbucketClient._get_diff`. |
| `get_commit_diff` — concurrent requests for a list of commits | Simpler but risks hitting the 1,000 req/hr rate limit on large commit lists. Sequential with a 50-commit cap is conservative and safe. |

---

## Consequences

**Positive:**
- The `resolve-pr-comments` Claude Code skill no longer needs any Python or shell
  outside of MCP tool calls — the full loop (fetch unresolved → fix → resolve) is
  expressible as a sequence of MCP tool invocations.
- `get_open_pr` removes the manual step of finding a PR ID, making the local DG trigger
  flow a single-line agent prompt: *"review my current PR"*.
- `get_commit_diff` enables commit-level code explanation and audit workflows that
  are currently impossible without shelling out to `git show` or `bb pr diff`.

**Negative:**
- Client-side filtering for `get_unresolved_pr_comments` fetches all comments then
  discards resolved ones. On PRs with many resolved comments (100+) this wastes one
  page of API calls. Acceptable given PR comment volumes at Citywire.
- `resolve_pr_comment` is a mutating operation exposed as an MCP tool. A misbehaving
  agent could mark comments resolved without actually fixing the underlying issue.
  Mitigated by: the tool operates on explicit `comment_id`s (no bulk-resolve), and
  comment resolution is reversible in the Bitbucket UI.
- `get_commit_diff` on a list of 50 commits consumes 50 API requests against the
  1,000 req/hr budget. This is fine in isolation but worth noting for agents that loop.
