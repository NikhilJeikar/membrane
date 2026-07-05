"""Server auth token helpers."""

from __future__ import annotations

import secrets
from pathlib import Path

from shadow_pa.config import PersonaConfig, Settings


def resolve_server_token(settings: Settings, persona: PersonaConfig) -> str:
    if persona.server.token:
        return persona.server.token
    token_path = settings.server_token_path
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")
    return token


def check_bearer_auth(header: str | None, expected_token: str) -> bool:
    if not expected_token:
        return True
    if not header or not header.lower().startswith("bearer "):
        return False
    return header[7:].strip() == expected_token
