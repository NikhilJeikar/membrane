"""Dot-path helpers for reading and writing nested config documents."""

from __future__ import annotations

import json
from typing import Any


def parse_config_value(raw: str) -> Any:
    text = raw.strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if text.lower() in ("null", "none"):
        return None
    if (text.startswith("[") and text.endswith("]")) or (
        text.startswith("{") and text.endswith("}")
    ):
        return json.loads(text)
    if text.startswith('"') and text.endswith('"'):
        return json.loads(text)
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def get_nested(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def set_nested(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: dict[str, Any] = data
    for part in parts[:-1]:
        nxt = current.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            current[part] = nxt
        current = nxt
    current[parts[-1]] = value
