"""Local OAuth helpers for integration connect flows."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from membrane.config import get_settings
from membrane.integrations.credentials import get_credential, upsert_tool_credentials

_OAUTH_PROVIDERS: dict[str, dict[str, Any]] = {
    "google": {
        "tool_id": "google",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "openid",
            "email",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
        "requires": ["client_id", "client_secret"],
        "token_keys": {"refresh_token": "refresh_token", "access_token": "access_token"},
    },
    "github": {
        "tool_id": "github",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": ["read:user", "repo", "read:org"],
        "requires": ["client_id", "client_secret"],
        "token_keys": {"access_token": "access_token"},
    },
    "linkedin": {
        "tool_id": "linkedin",
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": ["openid", "profile", "email", "w_member_social"],
        "requires": ["client_id", "client_secret"],
        "token_keys": {"access_token": "access_token"},
    },
}


def _state_path() -> Path:
    return get_settings().data_dir / "server" / "oauth_state.json"


def _load_states() -> dict[str, dict[str, Any]]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_states(states: dict[str, dict[str, Any]]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(states, indent=2), encoding="utf-8")


def _prune_states(states: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=15)
    kept: dict[str, dict[str, Any]] = {}
    for token, meta in states.items():
        created = datetime.fromisoformat(meta["created_at"])
        if created >= cutoff:
            kept[token] = meta
    return kept


def oauth_redirect_uri(provider: str, base_url: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/api/oauth/{provider}/callback"


def start_oauth(provider: str, base_url: str) -> str:
    cfg = _OAUTH_PROVIDERS.get(provider)
    if cfg is None:
        raise ValueError(f"unsupported OAuth provider: {provider}")
    tool_id = cfg["tool_id"]
    missing = [k for k in cfg["requires"] if not get_credential(tool_id, k)]
    if missing:
        labels = ", ".join(missing)
        raise ValueError(f"Save {labels} for {tool_id} before connecting.")

    state = secrets.token_urlsafe(24)
    states = _prune_states(_load_states())
    states[state] = {
        "provider": provider,
        "tool_id": tool_id,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    _save_states(states)

    redirect_uri = oauth_redirect_uri(provider, base_url)
    params: dict[str, str] = {
        "client_id": get_credential(tool_id, "client_id"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": " ".join(cfg["scopes"]),
    }
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    return f"{cfg['authorize_url']}?{urlencode(params)}"


def _exchange_code(provider: str, code: str, redirect_uri: str) -> dict[str, str]:
    cfg = _OAUTH_PROVIDERS[provider]
    tool_id = cfg["tool_id"]
    payload = {
        "client_id": get_credential(tool_id, "client_id"),
        "client_secret": get_credential(tool_id, "client_secret"),
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    headers = {"Accept": "application/json"}
    with httpx.Client(timeout=30.0) as client:
        if provider == "github":
            resp = client.post(
                cfg["token_url"],
                json=payload,
                headers={**headers, "Content-Type": "application/json"},
            )
        else:
            resp = client.post(cfg["token_url"], data=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    tokens: dict[str, str] = {}
    for cred_key, resp_key in cfg["token_keys"].items():
        val = data.get(resp_key)
        if val:
            tokens[cred_key] = str(val)
    if not tokens:
        raise ValueError("OAuth provider returned no tokens")
    return tokens


def finish_oauth(provider: str, code: str, state: str, base_url: str) -> str:
    cfg = _OAUTH_PROVIDERS.get(provider)
    if cfg is None:
        raise ValueError(f"unsupported OAuth provider: {provider}")

    states = _load_states()
    meta = states.pop(state, None)
    _save_states(_prune_states(states))
    if meta is None or meta.get("provider") != provider:
        raise ValueError("invalid or expired OAuth state")

    redirect_uri = oauth_redirect_uri(provider, base_url)
    tokens = _exchange_code(provider, code, redirect_uri)
    upsert_tool_credentials(cfg["tool_id"], tokens)
    return cfg["tool_id"]


def oauth_providers() -> list[dict[str, Any]]:
    return [
        {
            "id": provider,
            "tool_id": cfg["tool_id"],
            "label": provider.replace("_", " ").title(),
            "requires": cfg["requires"],
        }
        for provider, cfg in _OAUTH_PROVIDERS.items()
    ]
