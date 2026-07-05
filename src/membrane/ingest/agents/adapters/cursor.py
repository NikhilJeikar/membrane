"""Cursor agent transcript adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from membrane.ingest.agents.adapters.base import AgentAdapter
from membrane.ingest.agents.adapters.common import (
    extract_structured_content_parts,
    sanitize_agent_text,
    strip_cursor_user_message,
    workspace_hint_from_path,
)
from membrane.ingest.agents.models import AgentSession, AgentTurn


class CursorAdapter(AgentAdapter):
    name = "cursor"
    label = "Cursor"

    def can_parse(self, sample_rows: list[dict[str, Any]]) -> bool:
        return any(
            row.get("role") in ("user", "assistant")
            and isinstance(row.get("message"), dict)
            and isinstance(row["message"].get("content"), list)
            for row in sample_rows
        )

    def discover(self, root: Path) -> list[Path]:
        if root.is_file() and root.suffix == ".jsonl":
            return [root]
        paths: list[Path] = []
        for path in root.rglob("*.jsonl"):
            if "subagents" in path.parts:
                continue
            if "agent-transcripts" in path.parts or path.parent.name == path.stem:
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
            role = row.get("role", "")
            message = row.get("message", {})
            content_parts = message.get("content", [])
            if not isinstance(content_parts, list):
                continue

            if role == "user":
                for part in content_parts:
                    if part.get("type") != "text":
                        continue
                    text = strip_cursor_user_message(part.get("text", ""))
                    text = sanitize_agent_text(text, redact=redact)
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

            elif role == "assistant" and include_assistant:
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
