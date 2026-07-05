"""Claude Code session transcript adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from membrane.ingest.agents.adapters.base import AgentAdapter
from membrane.ingest.agents.adapters.common import (
    extract_structured_content_parts,
    sanitize_agent_text,
    workspace_hint_from_path,
)
from membrane.ingest.agents.models import AgentSession, AgentTurn

_SKIP_TYPES = frozenset(
    {
        "summary",
        "system",
        "attachment",
        "custom-title",
        "ai-title",
        "last-prompt",
        "tag",
        "agent-name",
        "agent-color",
        "agent-setting",
        "mode",
        "worktree-state",
        "pr-link",
        "file-history-snapshot",
        "attribution-snapshot",
        "content-replacement",
        "queue-operation",
    }
)


class ClaudeCodeAdapter(AgentAdapter):
    name = "claude"
    label = "Claude Code"

    def can_parse(self, sample_rows: list[dict[str, Any]]) -> bool:
        return any(
            row.get("type") in ("user", "assistant")
            and isinstance(row.get("message"), dict)
            and "role" not in row
            for row in sample_rows
        )

    def discover(self, root: Path) -> list[Path]:
        if root.is_file() and root.suffix == ".jsonl":
            return [root]
        paths: list[Path] = []
        for path in root.rglob("*.jsonl"):
            if any(part in path.parts for part in ("subagents", "workflows", "remote-agents")):
                continue
            if path.name.endswith(".meta.json"):
                continue
            paths.append(path)
        return sorted(set(paths))

    def parse(
        self,
        path: Path,
        *,
        include_assistant: bool = True,
        min_assistant_chars: int = 40,
        max_assistant_chars: int = 4000,
        skip_tool_heavy: bool = True,
        redact: bool = True,
    ) -> AgentSession:
        session_id = path.stem
        turns: list[AgentTurn] = []
        turn_index = 0

        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            event_type = row.get("type", "")
            if event_type in _SKIP_TYPES:
                continue

            message = row.get("message", {})
            if not isinstance(message, dict):
                continue
            content_parts = message.get("content", [])
            if not isinstance(content_parts, list):
                continue

            if event_type == "user":
                for part in content_parts:
                    if part.get("type") != "text":
                        continue
                    text = sanitize_agent_text(part.get("text", ""), redact=redact)
                    if len(text) < 3:
                        continue
                    turns.append(
                        AgentTurn(
                            role="user",
                            content=text,
                            session_id=session_id,
                            source_file=path.name,
                            turn_index=turn_index,
                            agent=self.name,
                        )
                    )
                    turn_index += 1

            elif event_type == "assistant" and include_assistant:
                text, has_tools = extract_structured_content_parts(
                    content_parts,
                    skip_tool_heavy=skip_tool_heavy,
                    min_assistant_chars=min_assistant_chars,
                )
                text = sanitize_agent_text(text, redact=redact)
                if len(text) < min_assistant_chars:
                    continue
                if len(text) > max_assistant_chars:
                    text = text[: max_assistant_chars - 3] + "..."
                turns.append(
                    AgentTurn(
                        role="assistant",
                        content=text,
                        session_id=session_id,
                        source_file=path.name,
                        turn_index=turn_index,
                        has_tool_calls=has_tools,
                        agent=self.name,
                    )
                )
                turn_index += 1

        return AgentSession(
            session_id=session_id,
            source_file=path.name,
            agent=self.name,
            workspace_hint=workspace_hint_from_path(path),
            turns=turns,
        )
