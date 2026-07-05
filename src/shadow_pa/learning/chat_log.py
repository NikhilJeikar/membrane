"""Chat session logging for ongoing learning."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from shadow_pa.memory.models import ChatSession, ChatTurn, DPOExample


class ChatLogger:
    def __init__(self, chats_dir: Path) -> None:
        self.chats_dir = chats_dir
        self.chats_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        return self.chats_dir / f"{session_id}.json"

    def save_session(self, session: ChatSession) -> Path:
        path = self._session_path(session.id)
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_session(self, session_id: str) -> ChatSession:
        path = self._session_path(session_id)
        return ChatSession.model_validate_json(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[Path]:
        return sorted(self.chats_dir.glob("*.json"))

    def record_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> ChatSession:
        path = self._session_path(session_id)
        if path.exists():
            session = self.load_session(session_id)
        else:
            session = ChatSession(id=session_id, metadata=metadata or {})
        session.turns.append(
            ChatTurn(role=role, content=content, timestamp=datetime.now().astimezone())  # type: ignore[arg-type]
        )
        self.save_session(session)
        return session

    def record_correction(
        self,
        session_id: str,
        user_prompt: str,
        rejected: str,
        chosen: str,
        dpo_dir: Path,
    ) -> DPOExample:
        example = DPOExample(
            prompt=user_prompt,
            chosen=chosen,
            rejected=rejected,
            metadata={"session_id": session_id, "source": "user_edit"},
        )
        dpo_dir.mkdir(parents=True, exist_ok=True)
        out = dpo_dir / f"{session_id}_{len(list(dpo_dir.glob('*.jsonl')))}.jsonl"
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(example.model_dump(mode="json")) + "\n")
        return example

    def session_to_text(self, session: ChatSession) -> str:
        lines: list[str] = []
        for turn in session.turns:
            lines.append(f"{turn.role.upper()}: {turn.content}")
        return "\n".join(lines)
