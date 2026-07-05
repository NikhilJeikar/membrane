"""Local credential storage for integrations (never committed to git)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from membrane.config import get_settings

_ENV_ALIASES: dict[str, dict[str, list[str]]] = {
    "google": {
        "client_id": ["GOOGLE_CLIENT_ID"],
        "client_secret": ["GOOGLE_CLIENT_SECRET"],
        "refresh_token": ["GOOGLE_REFRESH_TOKEN"],
        "access_token": ["GOOGLE_ACCESS_TOKEN"],
    },
    "github": {
        "client_id": ["GITHUB_CLIENT_ID"],
        "client_secret": ["GITHUB_CLIENT_SECRET"],
        "access_token": ["GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"],
    },
    "linkedin": {
        "client_id": ["LINKEDIN_CLIENT_ID"],
        "client_secret": ["LINKEDIN_CLIENT_SECRET"],
        "access_token": ["LINKEDIN_ACCESS_TOKEN"],
    },
    "instagram": {
        "app_id": ["META_APP_ID", "INSTAGRAM_APP_ID"],
        "access_token": ["INSTAGRAM_ACCESS_TOKEN"],
    },
    "twitter": {
        "bearer_token": ["TWITTER_BEARER_TOKEN"],
        "api_key": ["X_API_KEY", "TWITTER_API_KEY"],
        "api_secret": ["X_API_SECRET", "TWITTER_API_SECRET"],
    },
    "slack": {
        "bot_token": ["SLACK_BOT_TOKEN"],
        "user_token": ["SLACK_USER_TOKEN"],
    },
    "notion": {
        "integration_token": ["NOTION_TOKEN", "NOTION_API_KEY"],
    },
}


class CredentialFieldSchema(BaseModel):
    key: str
    label: str
    secret: bool = True
    placeholder: str = ""
    helper: str = ""
    oauth_only: bool = False


CREDENTIAL_SCHEMAS: dict[str, list[CredentialFieldSchema]] = {
    "google": [
        CredentialFieldSchema(
            key="client_id",
            label="OAuth client ID",
            secret=False,
            placeholder="….apps.googleusercontent.com",
            helper="From Google Cloud Console → APIs & Services → Credentials.",
        ),
        CredentialFieldSchema(
            key="client_secret",
            label="OAuth client secret",
            helper="Web application client secret from the same OAuth client.",
        ),
        CredentialFieldSchema(
            key="refresh_token",
            label="Refresh token",
            oauth_only=True,
            helper="Filled automatically after you click Sign in with Google.",
        ),
    ],
    "github": [
        CredentialFieldSchema(
            key="client_id",
            label="OAuth app client ID",
            secret=False,
            helper="Optional — for Sign in with GitHub. Or paste a PAT below.",
        ),
        CredentialFieldSchema(
            key="client_secret",
            label="OAuth app client secret",
            helper="Optional — paired with the OAuth app client ID.",
        ),
        CredentialFieldSchema(
            key="access_token",
            label="Personal access token",
            placeholder="ghp_…",
            helper="Alternative to OAuth — paste a classic or fine-grained PAT.",
        ),
    ],
    "linkedin": [
        CredentialFieldSchema(
            key="client_id",
            label="App client ID",
            secret=False,
        ),
        CredentialFieldSchema(
            key="client_secret",
            label="App client secret",
        ),
        CredentialFieldSchema(
            key="access_token",
            label="Access token",
            oauth_only=True,
            helper="Filled automatically after Sign in with LinkedIn, or paste manually.",
        ),
    ],
    "instagram": [
        CredentialFieldSchema(
            key="app_id",
            label="Meta app ID",
            secret=False,
        ),
        CredentialFieldSchema(
            key="access_token",
            label="Long-lived access token",
            helper="From Meta developer portal → Instagram Basic Display.",
        ),
    ],
    "twitter": [
        CredentialFieldSchema(
            key="bearer_token",
            label="Bearer token",
            helper="From X developer portal → Keys and tokens.",
        ),
        CredentialFieldSchema(
            key="api_key",
            label="API key",
            secret=False,
        ),
        CredentialFieldSchema(
            key="api_secret",
            label="API secret",
        ),
    ],
    "slack": [
        CredentialFieldSchema(
            key="bot_token",
            label="Bot token",
            placeholder="xoxb-…",
            helper="Slack app → OAuth & Permissions → Bot User OAuth Token.",
        ),
        CredentialFieldSchema(
            key="user_token",
            label="User token (optional)",
            placeholder="xoxp-…",
        ),
    ],
    "notion": [
        CredentialFieldSchema(
            key="integration_token",
            label="Integration token",
            placeholder="secret_…",
            helper="Notion → Settings → Integrations → your integration → Internal Integration Secret.",
        ),
    ],
}

# Minimum fields required to mark a tool as connected.
_REQUIRED_KEYS: dict[str, list[str]] = {
    "google": ["refresh_token"],
    "github": ["access_token"],
    "linkedin": ["access_token"],
    "instagram": ["access_token"],
    "twitter": ["bearer_token"],
    "slack": ["bot_token"],
    "notion": ["integration_token"],
}


def load_credentials_raw() -> dict[str, dict[str, str]]:
    from membrane.config_store import NAMESPACE_CREDENTIALS, ensure_config_db, load_config_raw

    ensure_config_db()
    raw = load_config_raw(NAMESPACE_CREDENTIALS)
    if raw is None:
        return {}
    tools = raw.get("tools") or raw
    if not isinstance(tools, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for tool_id, values in tools.items():
        if isinstance(values, dict):
            result[str(tool_id)] = {str(k): str(v) for k, v in values.items() if v}
    return result


def save_credentials_raw(creds: dict[str, dict[str, str]]) -> Path:
    from membrane.config_store import NAMESPACE_CREDENTIALS, save_config_raw

    return save_config_raw(NAMESPACE_CREDENTIALS, {"tools": creds})


def _resolve_value(tool_id: str, key: str, stored: dict[str, dict[str, str]]) -> str:
    tool_vals = stored.get(tool_id, {})
    if key in tool_vals and tool_vals[key].strip():
        return tool_vals[key].strip()
    for env_key in _ENV_ALIASES.get(tool_id, {}).get(key, []):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    return ""


def get_credential(tool_id: str, key: str) -> str:
    stored = load_credentials_raw()
    return _resolve_value(tool_id, key, stored)


def get_tool_credentials(tool_id: str) -> dict[str, str]:
    stored = load_credentials_raw()
    schema = CREDENTIAL_SCHEMAS.get(tool_id, [])
    result: dict[str, str] = {}
    for field in schema:
        val = _resolve_value(tool_id, field.key, stored)
        if val:
            result[field.key] = val
    return result


def mask_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


def _has_required(tool_id: str, stored: dict[str, dict[str, str]]) -> bool:
    required = _REQUIRED_KEYS.get(tool_id, [])
    return bool(required) and all(_resolve_value(tool_id, k, stored) for k in required)


def tool_connection_status(tool_id: str) -> bool:
    if tool_id == "web_search":
        from membrane.config import load_persona

        return load_persona().web_search.enabled
    if tool_id == "shell":
        from membrane.config import load_persona

        return load_persona().shell.enabled
    if tool_id in ("whatsapp", "email", "calendar"):
        return True
    if tool_id not in CREDENTIAL_SCHEMAS:
        return False
    return _has_required(tool_id, load_credentials_raw())


def upsert_tool_credentials(tool_id: str, values: dict[str, str]) -> dict[str, dict[str, str]]:
    if tool_id not in CREDENTIAL_SCHEMAS:
        raise ValueError(f"unknown tool: {tool_id}")
    stored = load_credentials_raw()
    current = stored.get(tool_id, {})
    for key, value in values.items():
        stripped = value.strip()
        if stripped:
            current[key] = stripped
        elif key in current:
            del current[key]
    if current:
        stored[tool_id] = current
    elif tool_id in stored:
        del stored[tool_id]
    save_credentials_raw(stored)
    return stored


def clear_tool_credentials(tool_id: str) -> None:
    stored = load_credentials_raw()
    if tool_id in stored:
        del stored[tool_id]
        save_credentials_raw(stored)


def credentials_catalog() -> dict:
    stored = load_credentials_raw()
    tools: dict[str, Any] = {}
    for tool_id, fields in CREDENTIAL_SCHEMAS.items():
        masked: dict[str, str] = {}
        for field in fields:
            val = _resolve_value(tool_id, field.key, stored)
            masked[field.key] = mask_value(val) if val else ""
        tools[tool_id] = {
            "fields": [f.model_dump() for f in fields],
            "values": masked,
            "connected": tool_connection_status(tool_id),
            "has_stored": tool_id in stored,
        }
    return {"tools": tools}
