"""Cursor agent transcript parser and ingest."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from shadow_pa.utils.redact import redact_text

USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL | re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"<timestamp>.*?</timestamp>\s*", re.DOTALL | re.IGNORECASE)
HOME_PATH_RE = re.compile(r"/home/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._~/-]*)*")
PROJECTS_PATH_RE = re.compile(r"~/Projects/[A-Za-z0-9._/-]+")
CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")


class CursorTurn(BaseModel):
    role: str
    content: str
    session_id: str
    source_file: str
    turn_index: int
    has_tool_calls: bool = False


class CursorSession(BaseModel):
    session_id: str
    source_file: str
    workspace_hint: str | None = None
    turns: list[CursorTurn] = Field(default_factory=list)


def _strip_user_message(text: str) -> str:
    match = USER_QUERY_RE.search(text)
    if match:
        text = match.group(1).strip()
    text = TIMESTAMP_RE.sub("", text).strip()
    return text


def _extract_assistant_text(content_parts: list[dict]) -> tuple[str, bool]:
    texts: list[str] = []
    has_tools = False
    for part in content_parts:
        part_type = part.get("type", "")
        if part_type == "tool_use":
            has_tools = True
            continue
        if part_type == "text":
            text = part.get("text", "").strip()
            if text:
                texts.append(text)
    combined = "\n\n".join(texts)
    combined = CODE_FENCE_RE.sub("[code omitted]", combined)
    return combined.strip(), has_tools


def _sanitize_content(text: str, redact: bool) -> str:
    text = HOME_PATH_RE.sub("[PATH]", text)
    text = PROJECTS_PATH_RE.sub("[PATH]", text)
    if redact:
        text = redact_text(text)
    return text.strip()


def parse_cursor_transcript(
    path: Path,
    *,
    include_assistant: bool = True,
    min_assistant_chars: int = 40,
    max_assistant_chars: int = 4000,
    skip_tool_heavy: bool = True,
    redact: bool = True,
) -> CursorSession:
    session_id = path.stem
    turns: list[CursorTurn] = []
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
                text = _strip_user_message(part.get("text", ""))
                text = _sanitize_content(text, redact=redact)
                if len(text) < 3:
                    continue
                turns.append(
                    CursorTurn(
                        role="user",
                        content=text,
                        session_id=session_id,
                        source_file=path.name,
                        turn_index=turn_index,
                    )
                )
                turn_index += 1

        elif role == "assistant" and include_assistant:
            text, has_tools = _extract_assistant_text(content_parts)
            text = _sanitize_content(text, redact=redact)
            if skip_tool_heavy and has_tools and len(text) < min_assistant_chars:
                continue
            if len(text) < min_assistant_chars:
                continue
            if len(text) > max_assistant_chars:
                text = text[: max_assistant_chars - 3] + "..."
            turns.append(
                CursorTurn(
                    role="assistant",
                    content=text,
                    session_id=session_id,
                    source_file=path.name,
                    turn_index=turn_index,
                    has_tool_calls=has_tools,
                )
            )
            turn_index += 1

    workspace_hint = _workspace_hint_from_path(path)
    return CursorSession(
        session_id=session_id,
        source_file=path.name,
        workspace_hint=workspace_hint,
        turns=turns,
    )


def _workspace_hint_from_path(path: Path) -> str | None:
    parts = path.parts
    for part in parts:
        if part.startswith("home-nikhil-Projects-"):
            return part.replace("home-nikhil-Projects-", "")
        if part.startswith("home-nikhil-"):
            return part.replace("home-nikhil-", "")
    return None


def discover_cursor_transcripts(root: Path, *, include_subagents: bool = False) -> list[Path]:
    if root.is_file() and root.suffix == ".jsonl":
        return [root]
    paths: list[Path] = []
    for path in root.rglob("*.jsonl"):
        if not include_subagents and "subagents" in path.parts:
            continue
        if path.parent.name == path.stem or path.name.endswith(".jsonl"):
            if "agent-transcripts" in path.parts or path.suffix == ".jsonl":
                paths.append(path)
    return sorted(set(paths))


def save_parsed_session(session: CursorSession, output_dir: Path) -> Path:
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
                "workspace_hint": session.workspace_hint,
                "turn_count": len(session.turns),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def ingest_cursor_path(
    source: Path,
    *,
    raw_dir: Path,
    parsed_dir: Path,
    redact: bool = True,
    copy_raw: bool = True,
    workers: int = 0,
    manifest: object | None = None,
    force: bool = False,
) -> IngestStats:
    from shadow_pa.tracking.manifest import ManifestStore
    from shadow_pa.tracking.stats import IngestStats
    from shadow_pa.utils.parallel import default_workers

    stats = IngestStats()
    store: ManifestStore | None = manifest  # type: ignore[assignment]

    transcripts = discover_cursor_transcripts(source)
    if not transcripts:
        raise FileNotFoundError(f"No Cursor transcript JSONL found under {source}")

    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    if store:
        for raw_file in raw_dir.glob("*.jsonl"):
            parsed_file = parsed_dir / raw_file.name
            store.reconcile_existing("cursor", raw_file, parsed_file)

    def ingest_one(transcript: Path) -> tuple[Path | None, bool]:
        dest_raw = raw_dir / transcript.name
        if copy_raw and transcript.resolve() != dest_raw.resolve():
            shutil.copy2(transcript, dest_raw)
        raw_for_hash = dest_raw if dest_raw.exists() else transcript
        parsed_out = parsed_dir / f"{transcript.stem}.jsonl"

        if store and not store.needs_ingest("cursor", raw_for_hash, parsed_out, force=force):
            return None, True

        session = parse_cursor_transcript(raw_for_hash, redact=redact)
        if not session.turns:
            return None, False
        out = save_parsed_session(session, parsed_dir)
        if store:
            store.record_ingest("cursor", raw_for_hash, out)
        return out, False

    pool_size = min(default_workers(workers), len(transcripts))
    if pool_size <= 1:
        for transcript in transcripts:
            out, skipped = ingest_one(transcript)
            if skipped:
                stats.skipped += 1
            elif out:
                stats.processed += 1
                stats.outputs.append(out)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=pool_size) as pool:
            futures = [pool.submit(ingest_one, t) for t in transcripts]
            for future in as_completed(futures):
                out, skipped = future.result()
                if skipped:
                    stats.skipped += 1
                elif out:
                    stats.processed += 1
                    stats.outputs.append(out)

    stats.outputs = sorted(stats.outputs, key=lambda p: p.name)
    return stats


def load_parsed_cursor_turns(path: Path) -> list[CursorTurn]:
    turns: list[CursorTurn] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            turns.append(CursorTurn.model_validate(json.loads(line)))
    return turns


def chunk_cursor_turns(
    turns: list[CursorTurn],
    chunk_size: int = 20,
    user_only: bool = False,
) -> list[list[CursorTurn]]:
    filtered = [t for t in turns if not user_only or t.role == "user"]
    return [filtered[i : i + chunk_size] for i in range(0, len(filtered), chunk_size)]


def format_cursor_chunk_for_extraction(chunk: list[CursorTurn]) -> str:
    lines: list[str] = []
    for turn in chunk:
        label = "SELF" if turn.role == "user" else "ASSISTANT"
        lines.append(f"[{label}]: {turn.content}")
    return "\n".join(lines)


def cursor_sessions_to_chat_sessions(parsed_dir: Path, chats_dir: Path) -> list[Path]:
    """Convert parsed Cursor sessions into shadow-pa chat JSON for SFT export."""
    from shadow_pa.memory.models import ChatSession, ChatTurn

    chats_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for path in sorted(parsed_dir.glob("*.jsonl")):
        turns = load_parsed_cursor_turns(path)
        if not turns:
            continue
        chat_turns = [
            ChatTurn(role=t.role, content=t.content)  # type: ignore[arg-type]
            for t in turns
            if t.role in ("user", "assistant")
        ]
        if len(chat_turns) < 2:
            continue
        session = ChatSession(
            id=f"cursor-{path.stem}",
            turns=chat_turns,
            metadata={"source": "cursor", "session_id": path.stem},
        )
        out = chats_dir / f"{session.id}.json"
        out.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        saved.append(out)

    return saved
