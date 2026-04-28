import json
import os
import tomllib
from pathlib import Path


def _resolve_auth_kwargs() -> dict:
    """Return kwargs for BitbucketClient, supplementing with the bb CLI config as a fallback.

    The SDK natively reads BITBUCKET_ACCESS_TOKEN, BITBUCKET_EMAIL, and BITBUCKET_API_TOKEN
    from the environment, so this function only needs to act when none of those are set.
    """
    if os.getenv("BITBUCKET_ACCESS_TOKEN"):
        return {}
    if os.getenv("BITBUCKET_EMAIL") and os.getenv("BITBUCKET_API_TOKEN"):
        return {}
    bb_dir = Path.home() / ".config" / "bb"
    # bb stores OAuth tokens in tokens.json (used by both oauth and apitoken auth methods)
    tokens_path = bb_dir / "tokens.json"
    if tokens_path.exists():
        token = json.loads(tokens_path.read_text()).get("access_token")
        if token:
            return {"access_token": token}
    # legacy: older bb versions stored the password directly in config.toml
    config_path = bb_dir / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            password = tomllib.load(f).get("auth", {}).get("password")
        if password:
            return {"access_token": password}
    raise RuntimeError(
        "No Bitbucket credentials found. "
        "Set BITBUCKET_ACCESS_TOKEN, run 'bb auth login', "
        "or set BITBUCKET_EMAIL and BITBUCKET_API_TOKEN."
    )
