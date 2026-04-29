from __future__ import annotations

import argparse
import dataclasses
import os
from datetime import datetime
from typing import Any

from bitbucket_sdk import BitbucketClient, NotFoundError
from fastmcp import FastMCP

from .auth import _resolve_auth_kwargs

mcp = FastMCP("bitbucket")
_client = BitbucketClient(**_resolve_auth_kwargs())

_MAX_COMMITS = 50


def _resolve_workspace(workspace: str | None) -> str:
    if workspace is not None:
        return workspace
    env = os.environ.get("BITBUCKET_WORKSPACE")
    if env:
        return env
    raise ValueError(
        "workspace is required: pass it as an argument or set BITBUCKET_WORKSPACE."
    )


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
def list_repos(workspace: str | None = None, updated_since: str | None = None) -> list[dict]:
    """List repositories in a workspace.

    updated_since: ISO 8601 date string; filters to repos updated after that date.
    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(_client.repositories.list(ws, updated_since))


@mcp.tool()
def list_open_prs(repo: str, workspace: str | None = None) -> list[dict]:
    """List all open pull requests for a repository.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(_client.pull_requests.list(ws, repo, state="OPEN"))


@mcp.tool()
def get_open_pr(
    repo: str, workspace: str | None = None, branch: str | None = None
) -> dict | None:
    """Return the open PR for the given branch, or None if no open PR exists.
    Detects the current git branch when branch is omitted.
    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    try:
        return _serialise(_client.pull_requests.get_open(ws, repo, branch))
    except NotFoundError:
        return None


@mcp.tool()
def get_pr(repo: str, pr_id: int, workspace: str | None = None) -> dict:
    """Fetch a pull request by ID.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(_client.pull_requests.get(ws, repo, pr_id))


@mcp.tool()
def get_pr_diff(repo: str, pr_id: int, workspace: str | None = None) -> str:
    """Return the unified diff for a pull request.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _client.pull_requests.get_diff(ws, repo, pr_id)


@mcp.tool()
def get_pr_diffstat(repo: str, pr_id: int, workspace: str | None = None) -> list[dict]:
    """Return per-file change statistics for a pull request.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(_client.pull_requests.get_diffstat(ws, repo, pr_id))


@mcp.tool()
def get_pr_comments(repo: str, pr_id: int, workspace: str | None = None) -> list[dict]:
    """Return all comments on a pull request.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(_client.pull_requests.list_comments(ws, repo, pr_id))


@mcp.tool()
def get_unresolved_pr_comments(
    repo: str, pr_id: int, workspace: str | None = None, inline_only: bool = False
) -> list[dict]:
    """Return unresolved comments on a pull request.
    Set inline_only=True to restrict to inline file/line comments.
    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(
        _client.pull_requests.list_unresolved_comments(ws, repo, pr_id, inline_only)
    )


@mcp.tool()
def post_pr_comment(
    repo: str,
    pr_id: int,
    body: str,
    workspace: str | None = None,
    file_path: str | None = None,
    line: int | None = None,
) -> dict:
    """Post a comment on a pull request. Provide file_path and line for an inline comment.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(
        _client.pull_requests.post_comment(ws, repo, pr_id, body, file_path, line)
    )


@mcp.tool()
def resolve_pr_comment(
    repo: str, pr_id: int, comment_id: int, workspace: str | None = None
) -> dict:
    """Mark a pull request comment as resolved.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    _client.pull_requests.resolve_comment(ws, repo, pr_id, comment_id)
    return {"status": "ok"}


@mcp.tool()
def approve_pr(repo: str, pr_id: int, workspace: str | None = None) -> dict:
    """Approve a pull request.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    _client.pull_requests.approve(ws, repo, pr_id)
    return {"status": "ok"}


@mcp.tool()
def decline_pr(repo: str, pr_id: int, workspace: str | None = None) -> dict:
    """Decline a pull request.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(_client.pull_requests.decline(ws, repo, pr_id))


@mcp.tool()
def merge_pr(
    repo: str,
    pr_id: int,
    workspace: str | None = None,
    strategy: str = "merge_commit",
    message: str | None = None,
    close_source_branch: bool | None = None,
) -> dict:
    """Merge a pull request. strategy must be 'merge_commit' or 'squash'.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(
        _client.pull_requests.merge(ws, repo, pr_id, strategy, close_source_branch, message)
    )


@mcp.tool()
def create_pr(
    repo: str,
    title: str,
    source_branch: str,
    destination_branch: str,
    workspace: str | None = None,
    description: str | None = None,
    reviewers: list[str] | None = None,
    close_source_branch: bool = False,
) -> dict:
    """Create a pull request.

    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    return _serialise(
        _client.pull_requests.create(
            ws, repo, title, source_branch, destination_branch,
            description, reviewers, close_source_branch,
        )
    )


def _normalise_range(spec: str) -> str:
    # Bitbucket's diff API treats 'a..b' as "what a adds over b" — the reverse of git
    # convention. Swap so callers can use the natural git order (old..new).
    if "..." not in spec and ".." in spec:
        left, right = spec.split("..", 1)
        return f"{right}..{left}"
    return spec


@mcp.tool()
def get_commit_diff(repo: str, commits: str | list[str], workspace: str | None = None) -> str:
    """Return the unified diff for one or more commits.
    commits can be a single hash, a range string ('abc..def'), or a list of hashes (max 50).
    workspace: defaults to BITBUCKET_WORKSPACE env var if not provided.
    """
    ws = _resolve_workspace(workspace)
    if isinstance(commits, list):
        if len(commits) > _MAX_COMMITS:
            raise ValueError(f"commits list must not exceed {_MAX_COMMITS} entries")
        parts = []
        for c in commits:
            parts.append(f"--- commit {c} ---")
            parts.append(_client.repositories.get_commit_diff(ws, repo, c))
        return "\n".join(parts)
    return _client.repositories.get_commit_diff(ws, repo, _normalise_range(commits))


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
