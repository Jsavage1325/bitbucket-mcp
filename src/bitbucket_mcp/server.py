from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime
from typing import Any

from bitbucket_sdk import BitbucketClient
from fastmcp import FastMCP

from .auth import _resolve_auth_kwargs

mcp = FastMCP("bitbucket")
_client = BitbucketClient(**_resolve_auth_kwargs())

_MAX_COMMITS = 50


def _serialise(obj: Any) -> Any:
    """Recursively convert SDK dataclass models to JSON-serialisable types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _serialise(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if hasattr(obj, "__iter__"):
        return [_serialise(i) for i in obj]
    return obj


@mcp.tool()
def list_repos(workspace: str, updated_since: str | None = None) -> list[dict]:
    """List repositories in a workspace.

    updated_since: ISO 8601 date string; filters to repos updated after that date.
    """
    return _serialise(_client.repositories.list(workspace, updated_since))


@mcp.tool()
def list_open_prs(workspace: str, repo: str) -> list[dict]:
    """List all open pull requests for a repository."""
    return _serialise(_client.pull_requests.list(workspace, repo, state="OPEN"))


@mcp.tool()
def get_open_pr(workspace: str, repo: str, branch: str | None = None) -> dict | None:
    """Return the open PR for the given branch, or None if no open PR exists.
    Detects the current git branch when branch is omitted.
    """
    return _serialise(_client.pull_requests.get_open(workspace, repo, branch))


@mcp.tool()
def get_pr(workspace: str, repo: str, pr_id: int) -> dict:
    """Fetch a pull request by ID."""
    return _serialise(_client.pull_requests.get(workspace, repo, pr_id))


@mcp.tool()
def get_pr_diff(workspace: str, repo: str, pr_id: int) -> str:
    """Return the unified diff for a pull request."""
    return _client.pull_requests.get_diff(workspace, repo, pr_id)


@mcp.tool()
def get_pr_diffstat(workspace: str, repo: str, pr_id: int) -> list[dict]:
    """Return per-file change statistics for a pull request."""
    return _serialise(_client.pull_requests.get_diffstat(workspace, repo, pr_id))


@mcp.tool()
def get_pr_comments(workspace: str, repo: str, pr_id: int) -> list[dict]:
    """Return all comments on a pull request."""
    return _serialise(_client.pull_requests.list_comments(workspace, repo, pr_id))


@mcp.tool()
def get_unresolved_pr_comments(
    workspace: str, repo: str, pr_id: int, inline_only: bool = False
) -> list[dict]:
    """Return unresolved comments on a pull request.
    Set inline_only=True to restrict to inline file/line comments.
    """
    return _serialise(
        _client.pull_requests.list_unresolved_comments(workspace, repo, pr_id, inline_only)
    )


@mcp.tool()
def post_pr_comment(
    workspace: str,
    repo: str,
    pr_id: int,
    body: str,
    file_path: str | None = None,
    line: int | None = None,
) -> dict:
    """Post a comment on a pull request. Provide file_path and line for an inline comment."""
    return _serialise(
        _client.pull_requests.post_comment(workspace, repo, pr_id, body, file_path, line)
    )


@mcp.tool()
def resolve_pr_comment(workspace: str, repo: str, pr_id: int, comment_id: int) -> dict:
    """Mark a pull request comment as resolved."""
    _client.pull_requests.resolve_comment(workspace, repo, pr_id, comment_id)
    return {"status": "ok"}


@mcp.tool()
def approve_pr(workspace: str, repo: str, pr_id: int) -> dict:
    """Approve a pull request."""
    _client.pull_requests.approve(workspace, repo, pr_id)
    return {"status": "ok"}


@mcp.tool()
def decline_pr(workspace: str, repo: str, pr_id: int) -> dict:
    """Decline a pull request."""
    return _serialise(_client.pull_requests.decline(workspace, repo, pr_id))


@mcp.tool()
def merge_pr(
    workspace: str,
    repo: str,
    pr_id: int,
    strategy: str = "merge_commit",
    message: str | None = None,
    close_source_branch: bool | None = None,
) -> dict:
    """Merge a pull request. strategy must be 'merge_commit' or 'squash'."""
    return _serialise(
        _client.pull_requests.merge(workspace, repo, pr_id, strategy, close_source_branch, message)
    )


@mcp.tool()
def create_pr(
    workspace: str,
    repo: str,
    title: str,
    source_branch: str,
    destination_branch: str,
    description: str | None = None,
    reviewers: list[str] | None = None,
    close_source_branch: bool = False,
) -> dict:
    """Create a pull request."""
    return _serialise(
        _client.pull_requests.create(
            workspace, repo, title, source_branch, destination_branch,
            description, reviewers, close_source_branch,
        )
    )


@mcp.tool()
def get_commit_diff(workspace: str, repo: str, commits: str | list[str]) -> str:
    """Return the unified diff for one or more commits.
    commits can be a single hash, a range string ('abc..def'), or a list of hashes (max 50).
    """
    if isinstance(commits, list):
        if len(commits) > _MAX_COMMITS:
            raise ValueError(f"commits list must not exceed {_MAX_COMMITS} entries")
        parts = []
        for c in commits:
            parts.append(f"--- commit {c} ---")
            parts.append(_client.repositories.get_commit_diff(workspace, repo, c))
        return "\n".join(parts)
    return _client.repositories.get_commit_diff(workspace, repo, commits)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bitbucket MCP Server")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
