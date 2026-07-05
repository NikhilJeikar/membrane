"""Agent adapter registry and auto-detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from membrane.ingest.agents.adapters.base import AgentAdapter
from membrane.ingest.agents.adapters.claude_code import ClaudeCodeAdapter
from membrane.ingest.agents.adapters.cursor import CursorAdapter
from membrane.ingest.agents.adapters.openai_chat import OpenAIChatAdapter

ADAPTERS: dict[str, AgentAdapter] = {
    "cursor": CursorAdapter(),
    "claude": ClaudeCodeAdapter(),
    "openai": OpenAIChatAdapter(),
}

# Detection order: most specific first.
DETECTION_ORDER = ("cursor", "claude", "openai")

DEFAULT_AGENT_PATHS: dict[str, list[str]] = {
    "cursor": ["~/.cursor/projects"],
    "claude": ["~/.claude/projects"],
    "openai": [],
}


def list_providers() -> list[str]:
    return list(ADAPTERS.keys())


def get_adapter(provider: str) -> AgentAdapter:
    adapter = ADAPTERS.get(provider)
    if adapter is None:
        known = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"Unknown agent provider: {provider}. Known: {known}")
    return adapter


def sample_rows(path: Path, limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def detect_provider(path: Path) -> str:
    rows = sample_rows(path)
    if not rows:
        raise ValueError(f"No JSONL rows found in {path}")
    for name in DETECTION_ORDER:
        adapter = ADAPTERS[name]
        if adapter.can_parse(rows):
            return name
    raise ValueError(f"Unrecognized agent transcript format: {path}")


def discover_transcripts(
    root: Path,
    provider: str = "auto",
) -> list[tuple[str, Path]]:
    """Return (provider, path) pairs for transcripts under root."""
    if not root.exists():
        raise FileNotFoundError(f"Path not found: {root}")

    if root.is_file():
        detected = detect_provider(root) if provider == "auto" else provider
        return [(detected, root)]

    if provider == "auto":
        pairs: list[tuple[str, Path]] = []
        for path in sorted(root.rglob("*.jsonl")):
            if path.name.endswith(".meta.json") or ".meta." in path.name:
                continue
            if any(part in path.parts for part in ("subagents", "workflows", "remote-agents")):
                continue
            try:
                pairs.append((detect_provider(path), path))
            except ValueError:
                continue
        return pairs

    adapter = get_adapter(provider)
    return [(provider, path) for path in adapter.discover(root)]
