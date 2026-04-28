import dataclasses
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from bitbucket_mcp import server


@dataclasses.dataclass
class _Repo:
    slug: str
    updated_on: datetime


@dataclasses.dataclass
class _PR:
    id: int
    title: str
    created_on: datetime


class TestSerialise:
    def test_none(self):
        assert server._serialise(None) is None

    def test_string(self):
        assert server._serialise("hello") == "hello"

    def test_int(self):
        value = 42
        assert server._serialise(value) == value

    def test_float(self):
        value = 3.14
        assert server._serialise(value) == value

    def test_bool(self):
        assert server._serialise(True) is True

    def test_datetime(self):
        dt = datetime(2026, 1, 15, 10, 30, 0)
        assert server._serialise(dt) == "2026-01-15T10:30:00"

    def test_dataclass_with_datetime_field(self):
        dt = datetime(2026, 1, 15, 0, 0, 0)
        result = server._serialise(_Repo(slug="my-repo", updated_on=dt))
        assert result == {"slug": "my-repo", "updated_on": "2026-01-15T00:00:00"}

    def test_nested_dataclass(self):
        dt = datetime(2026, 1, 15, 0, 0, 0)
        result = server._serialise(_PR(id=1, title="My PR", created_on=dt))
        assert result == {"id": 1, "title": "My PR", "created_on": "2026-01-15T00:00:00"}

    def test_dict(self):
        dt = datetime(2026, 1, 15, 0, 0, 0)
        result = server._serialise({"key": dt, "nested": {"a": 1}})
        assert result == {"key": "2026-01-15T00:00:00", "nested": {"a": 1}}

    def test_list(self):
        assert server._serialise([1, "two", None]) == [1, "two", None]

    def test_generator(self):
        assert server._serialise(x for x in [1, 2, 3]) == [1, 2, 3]

    def test_list_of_dataclasses(self):
        dt = datetime(2026, 1, 15, 0, 0, 0)
        repos = [_Repo(slug="a", updated_on=dt), _Repo(slug="b", updated_on=dt)]
        result = server._serialise(repos)
        assert [r["slug"] for r in result] == ["a", "b"]


class TestTools:
    def setup_method(self):
        self._mock = MagicMock()
        self._patcher = patch.object(server, "_client", self._mock)
        self._patcher.start()

    def teardown_method(self):
        self._patcher.stop()

    # --- repositories ---

    def test_list_repos(self):
        self._mock.repositories.list.return_value = [{"slug": "repo-a"}]
        result = server.list_repos("ws")
        self._mock.repositories.list.assert_called_once_with("ws", None)
        assert result == [{"slug": "repo-a"}]

    def test_list_repos_with_updated_since(self):
        self._mock.repositories.list.return_value = []
        server.list_repos("ws", "2026-01-01")
        self._mock.repositories.list.assert_called_once_with("ws", "2026-01-01")

    def test_get_commit_diff_string(self):
        self._mock.repositories.get_commit_diff.return_value = "diff output"
        result = server.get_commit_diff("ws", "repo", "abc123")
        self._mock.repositories.get_commit_diff.assert_called_once_with("ws", "repo", "abc123")
        assert result == "diff output"

    def test_get_commit_diff_range_string(self):
        self._mock.repositories.get_commit_diff.return_value = "range diff"
        result = server.get_commit_diff("ws", "repo", "abc..def")
        assert result == "range diff"

    def test_get_commit_diff_list(self):
        self._mock.repositories.get_commit_diff.side_effect = ["diff1", "diff2"]
        result = server.get_commit_diff("ws", "repo", ["abc", "def"])
        assert "--- commit abc ---" in result
        assert "diff1" in result
        assert "--- commit def ---" in result
        assert "diff2" in result

    def test_get_commit_diff_list_too_long(self):
        with pytest.raises(ValueError, match="commits list must not exceed 50"):
            server.get_commit_diff("ws", "repo", ["x"] * 51)

    # --- pull requests ---

    def test_list_open_prs(self):
        self._mock.pull_requests.list.return_value = [{"id": 1}]
        result = server.list_open_prs("ws", "repo")
        self._mock.pull_requests.list.assert_called_once_with("ws", "repo", state="OPEN")
        assert result == [{"id": 1}]

    def test_get_open_pr_no_branch(self):
        self._mock.pull_requests.get_open.return_value = {"id": 7}
        result = server.get_open_pr("ws", "repo")
        self._mock.pull_requests.get_open.assert_called_once_with("ws", "repo", None)
        assert result == {"id": 7}

    def test_get_open_pr_with_branch(self):
        self._mock.pull_requests.get_open.return_value = None
        result = server.get_open_pr("ws", "repo", branch="feature/x")
        self._mock.pull_requests.get_open.assert_called_once_with("ws", "repo", "feature/x")
        assert result is None

    def test_get_pr(self):
        self._mock.pull_requests.get.return_value = {"id": 5}
        result = server.get_pr("ws", "repo", 5)
        self._mock.pull_requests.get.assert_called_once_with("ws", "repo", 5)
        assert result == {"id": 5}

    def test_get_pr_diff(self):
        self._mock.pull_requests.get_diff.return_value = "diff --git..."
        result = server.get_pr_diff("ws", "repo", 5)
        assert result == "diff --git..."

    def test_get_pr_diffstat(self):
        self._mock.pull_requests.get_diffstat.return_value = [{"lines_added": 10}]
        result = server.get_pr_diffstat("ws", "repo", 5)
        assert result == [{"lines_added": 10}]

    def test_get_pr_comments(self):
        self._mock.pull_requests.list_comments.return_value = [{"id": 1}]
        result = server.get_pr_comments("ws", "repo", 5)
        assert result == [{"id": 1}]

    def test_get_unresolved_pr_comments_default(self):
        self._mock.pull_requests.list_unresolved_comments.return_value = [{"id": 2}]
        result = server.get_unresolved_pr_comments("ws", "repo", 5)
        self._mock.pull_requests.list_unresolved_comments.assert_called_once_with(
            "ws", "repo", 5, False
        )
        assert result == [{"id": 2}]

    def test_get_unresolved_pr_comments_inline_only(self):
        self._mock.pull_requests.list_unresolved_comments.return_value = []
        server.get_unresolved_pr_comments("ws", "repo", 5, inline_only=True)
        self._mock.pull_requests.list_unresolved_comments.assert_called_once_with(
            "ws", "repo", 5, True
        )

    def test_post_pr_comment_summary(self):
        self._mock.pull_requests.post_comment.return_value = {"id": 99}
        result = server.post_pr_comment("ws", "repo", 5, "Looks good!")
        self._mock.pull_requests.post_comment.assert_called_once_with(
            "ws", "repo", 5, "Looks good!", None, None
        )
        assert result == {"id": 99}

    def test_post_pr_comment_inline(self):
        self._mock.pull_requests.post_comment.return_value = {"id": 100}
        server.post_pr_comment("ws", "repo", 5, "Fix this", "src/main.py", 42)
        self._mock.pull_requests.post_comment.assert_called_once_with(
            "ws", "repo", 5, "Fix this", "src/main.py", 42
        )

    def test_resolve_pr_comment(self):
        result = server.resolve_pr_comment("ws", "repo", 5, 99)
        self._mock.pull_requests.resolve_comment.assert_called_once_with("ws", "repo", 5, 99)
        assert result == {"status": "ok"}

    def test_approve_pr(self):
        result = server.approve_pr("ws", "repo", 5)
        self._mock.pull_requests.approve.assert_called_once_with("ws", "repo", 5)
        assert result == {"status": "ok"}

    def test_decline_pr(self):
        self._mock.pull_requests.decline.return_value = {"id": 5, "state": "DECLINED"}
        result = server.decline_pr("ws", "repo", 5)
        assert result == {"id": 5, "state": "DECLINED"}

    def test_merge_pr_defaults(self):
        self._mock.pull_requests.merge.return_value = {"id": 5, "state": "MERGED"}
        result = server.merge_pr("ws", "repo", 5)
        self._mock.pull_requests.merge.assert_called_once_with(
            "ws", "repo", 5, "merge_commit", None, None
        )
        assert result == {"id": 5, "state": "MERGED"}

    def test_merge_pr_squash_with_close_source(self):
        self._mock.pull_requests.merge.return_value = {"id": 5, "state": "MERGED"}
        server.merge_pr("ws", "repo", 5, strategy="squash", close_source_branch=True)
        self._mock.pull_requests.merge.assert_called_once_with(
            "ws", "repo", 5, "squash", True, None
        )

    def test_merge_pr_with_message(self):
        self._mock.pull_requests.merge.return_value = {"id": 5, "state": "MERGED"}
        server.merge_pr("ws", "repo", 5, message="Merge PR #5")
        self._mock.pull_requests.merge.assert_called_once_with(
            "ws", "repo", 5, "merge_commit", None, "Merge PR #5"
        )

    def test_create_pr_minimal(self):
        self._mock.pull_requests.create.return_value = {"id": 10}
        result = server.create_pr("ws", "repo", "My PR", "feature/foo", "main")
        self._mock.pull_requests.create.assert_called_once_with(
            "ws", "repo", "My PR", "feature/foo", "main", None, None, False
        )
        assert result == {"id": 10}

    def test_create_pr_with_all_options(self):
        self._mock.pull_requests.create.return_value = {"id": 11}
        server.create_pr(
            "ws",
            "repo",
            "My PR",
            "feature/bar",
            "main",
            description="A description",
            reviewers=["user1"],
            close_source_branch=True,
        )
        self._mock.pull_requests.create.assert_called_once_with(
            "ws",
            "repo",
            "My PR",
            "feature/bar",
            "main",
            "A description",
            ["user1"],
            True,
        )
