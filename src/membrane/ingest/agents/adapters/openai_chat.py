"""OpenAI-style chat JSONL adapter (Continue, Codex exports, generic tools)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from membrane.ingest.agents.adapters.base import AgentAdapter
from membrane.ingest.agents.adapters.common import (
    extract_openai_content,
    sanitize_agent_text,
    workspace_hint_from_path,
)
from membrane.ingest.agents.models import AgentSession, AgentTurn


class OpenAIChatAdapter(AgentAdapter):
    name = "openai"
    label = "OpenAI-style chat"

    def can_parse(self, sample_rows: list[dict[str, Any]]) -> bool:
        return any(
            row.get("role") in ("user", "assistant", "human", "gpt", "bot")
            and ("content" in row or "text" in row)
            and "message" not in row
            for row in sample_rows
        )

    def discover(self, root: Path) -> list[Path]:
        if root.is_file() and root.suffix == ".jsonl":
            return [root]
        return sorted(root.rglob("*.jsonl"))

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

            if "messages" in row and isinstance(row["messages"], list):
                for msg in row["messages"]:
                    if not isinstance(msg, dict):
                        continue
                    self._append_message(
                        msg,
                        session_id=session_id,
                        source_file=path.name,
                        turns=turns,
                        turn_index_ref=[turn_index],
                        include_assistant=include_assistant,
                        min_assistant_chars=min_assistant_chars,
                        max_assistant_chars=max_assistant_chars,
                        skip_tool_heavy=skip_tool_heavy,
                        redact=redact,
                    )
                turn_index = turns[-1].turn_index + 1 if turns else 0
                continue

            role = self._normalize_role(row.get("role", ""))
            if role not in ("user", "assistant"):
                continue
            if role == "assistant" and not include_assistant:
                continue

            content_raw = row.get("content", row.get("text", ""))
            text, has_tools = extract_openai_content(content_raw)
            text = sanitize_agent_text(text, redact=redact)
            if role == "user" and len(text) < 3:
                continue
            if role == "assistant":
                if skip_tool_heavy and has_tools and len(text) < min_assistant_chars:
                    continue
                if len(text) < min_assistant_chars:
                    continue
                if len(text) > max_assistant_chars:
                    text = text[: max_assistant_chars - 3] + "..."

            turns.append(
                AgentTurn(
                    role=role,
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

    def _append_message(
        self,
        msg: dict[str, Any],
        *,
        session_id: str,
        source_file: str,
        turns: list[AgentTurn],
        turn_index_ref: list[int],
        include_assistant: bool,
        min_assistant_chars: int,
        max_assistant_chars: int,
        skip_tool_heavy: bool,
        redact: bool,
    ) -> None:
        role = self._normalize_role(msg.get("role", ""))
        if role not in ("user", "assistant"):
            return
        if role == "assistant" and not include_assistant:
            return
        text, has_tools = extract_openai_content(msg.get("content", msg.get("text", "")))
        text = sanitize_agent_text(text, redact=redact)
        if role == "user" and len(text) < 3:
            return
        if role == "assistant":
            if skip_tool_heavy and has_tools and len(text) < min_assistant_chars:
                return
            if len(text) < min_assistant_chars:
                return
            if len(text) > max_assistant_chars:
                text = text[: max_assistant_chars - 3] + "..."
        turns.append(
            AgentTurn(
                role=role,
                content=text,
                session_id=session_id,
                source_file=source_file,
                turn_index=turn_index_ref[0],
                has_tool_calls=has_tools,
                agent=self.name,
            )
        )
        turn_index_ref[0] += 1

    @staticmethod
    def _normalize_role(role: str) -> str:
        role = role.lower()
        if role in ("human", "user"):
            return "user"
        if role in ("gpt", "assistant", "bot", "ai"):
            return "assistant"
        return role
