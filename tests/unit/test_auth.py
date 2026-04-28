import json
from unittest.mock import patch

import pytest

from bitbucket_mcp.auth import _resolve_auth_kwargs


def test_returns_empty_when_access_token_set(monkeypatch):
    monkeypatch.setenv("BITBUCKET_ACCESS_TOKEN", "tok123")
    monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    assert _resolve_auth_kwargs() == {}


def test_returns_empty_when_email_and_api_token_set(monkeypatch):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("BITBUCKET_EMAIL", "user@example.com")
    monkeypatch.setenv("BITBUCKET_API_TOKEN", "apitoken")
    assert _resolve_auth_kwargs() == {}


def test_only_email_without_api_token_falls_through(monkeypatch, tmp_path):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("BITBUCKET_EMAIL", "user@example.com")
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    with (
        patch("bitbucket_mcp.auth.Path.home", return_value=tmp_path),
        pytest.raises(RuntimeError, match="No Bitbucket credentials found"),
    ):
        _resolve_auth_kwargs()


def test_reads_token_from_bb_tokens_json(monkeypatch, tmp_path):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    bb_dir = tmp_path / ".config" / "bb"
    bb_dir.mkdir(parents=True)
    (bb_dir / "tokens.json").write_text(
        json.dumps({"access_token": "oauth-token", "refresh_token": "r", "expires_at": 9999})
    )
    with patch("bitbucket_mcp.auth.Path.home", return_value=tmp_path):
        result = _resolve_auth_kwargs()
    assert result == {"access_token": "oauth-token"}


def test_tokens_json_takes_priority_over_config_toml(monkeypatch, tmp_path):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    bb_dir = tmp_path / ".config" / "bb"
    bb_dir.mkdir(parents=True)
    (bb_dir / "tokens.json").write_text(json.dumps({"access_token": "tokens-json-token"}))
    (bb_dir / "config.toml").write_bytes(b'[auth]\npassword = "config-toml-token"\n')
    with patch("bitbucket_mcp.auth.Path.home", return_value=tmp_path):
        result = _resolve_auth_kwargs()
    assert result == {"access_token": "tokens-json-token"}


def test_falls_back_to_config_toml_password(monkeypatch, tmp_path):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    bb_dir = tmp_path / ".config" / "bb"
    bb_dir.mkdir(parents=True)
    (bb_dir / "config.toml").write_bytes(b'[auth]\npassword = "legacy-token"\n')
    with patch("bitbucket_mcp.auth.Path.home", return_value=tmp_path):
        result = _resolve_auth_kwargs()
    assert result == {"access_token": "legacy-token"}


def test_raises_when_no_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    with (
        patch("bitbucket_mcp.auth.Path.home", return_value=tmp_path),
        pytest.raises(RuntimeError, match="No Bitbucket credentials found"),
    ):
        _resolve_auth_kwargs()


def test_raises_when_tokens_json_has_no_access_token(monkeypatch, tmp_path):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    bb_dir = tmp_path / ".config" / "bb"
    bb_dir.mkdir(parents=True)
    (bb_dir / "tokens.json").write_text(json.dumps({"refresh_token": "r"}))
    with (
        patch("bitbucket_mcp.auth.Path.home", return_value=tmp_path),
        pytest.raises(RuntimeError, match="No Bitbucket credentials found"),
    ):
        _resolve_auth_kwargs()


def test_raises_when_bb_config_has_no_password(monkeypatch, tmp_path):
    monkeypatch.delenv("BITBUCKET_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_EMAIL", raising=False)
    monkeypatch.delenv("BITBUCKET_API_TOKEN", raising=False)
    bb_dir = tmp_path / ".config" / "bb"
    bb_dir.mkdir(parents=True)
    (bb_dir / "config.toml").write_bytes(b"[auth]\n")
    with (
        patch("bitbucket_mcp.auth.Path.home", return_value=tmp_path),
        pytest.raises(RuntimeError, match="No Bitbucket credentials found"),
    ):
        _resolve_auth_kwargs()
