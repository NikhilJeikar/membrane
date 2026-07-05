"""Read/write normalized agent sessions."""

from __future__ import annotations

import json
from pathlib import Path

from membrane.ingest.agents.models import AgentSession, AgentTurn


def save_parsed_session(session: AgentSession, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{session.session_id}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for turn in session.turns:
            f.write(json.dumps(turn.model_dump(mode="json")) + "\n")
    meta_path = output_dir / f"{session.session_id}.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "session_id": session.session_id,
                "source_file": session.source_file,
                "agent": session.agent,
                "workspace_hint": session.workspace_hint,
                "turn_count": len(session.turns),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def load_parsed_turns(path: Path) -> list[AgentTurn]:
    turns: list[AgentTurn] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            turns.append(AgentTurn.model_validate(json.loads(line)))
    return turns


def read_session_meta(parsed_path: Path) -> dict:
    meta_path = parsed_path.parent / f"{parsed_path.stem}.meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


def chunk_turns(
    turns: list[AgentTurn],
    chunk_size: int = 20,
    user_only: bool = False,
) -> list[list[AgentTurn]]:
    filtered = [t for t in turns if not user_only or t.role == "user"]
    return [filtered[i : i + chunk_size] for i in range(0, len(filtered), chunk_size)]


def format_chunk_for_extraction(chunk: list[AgentTurn]) -> str:
    lines: list[str] = []
    for turn in chunk:
        label = "SELF" if turn.role == "user" else "ASSISTANT"
        lines.append(f"[{label}]: {turn.content}")
    return "\n".join(lines)


def agent_sessions_to_chat_sessions(
    parsed_dir: Path,
    chats_dir: Path,
    *,
    provider: str | None = None,
) -> list[Path]:
    """Convert parsed agent sessions into membrane chat JSON for SFT export."""
    from membrane.memory.models import ChatSession, ChatTurn

    chats_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for path in sorted(parsed_dir.glob("*.jsonl")):
        if ".meta." in path.name:
            continue
        turns = load_parsed_turns(path)
        if not turns:
            continue
        meta = read_session_meta(path)
        agent = provider or meta.get("agent") or turns[0].agent or "agent"
        chat_turns = [
            ChatTurn(role=t.role, content=t.content)  # type: ignore[arg-type]
            for t in turns
            if t.role in ("user", "assistant")
        ]
        if len(chat_turns) < 2:
            continue
        session = ChatSession(
            id=f"{agent}-{path.stem}",
            turns=chat_turns,
            metadata={"source": agent, "session_id": path.stem, "agent": agent},
        )
        out = chats_dir / f"{session.id}.json"
        out.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        saved.append(out)

    return saved
