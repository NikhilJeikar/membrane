"""Backward-compatible Cursor ingest API (delegates to agents package)."""

from __future__ import annotations

from pathlib import Path

from membrane.ingest.agents import (
    AgentSession,
    AgentTurn,
    agent_sessions_to_chat_sessions,
    chunk_turns,
    discover_transcripts,
    format_chunk_for_extraction,
    ingest_agent_path,
    load_parsed_turns,
    save_parsed_session,
)
from membrane.tracking.stats import IngestStats

CursorTurn = AgentTurn
CursorSession = AgentSession


def parse_cursor_transcript(path: Path, **kwargs) -> CursorSession:
    from membrane.ingest.agents.registry import get_adapter

    return get_adapter("cursor").parse(path, **kwargs)


def discover_cursor_transcripts(root: Path, *, include_subagents: bool = False) -> list[Path]:
    from membrane.ingest.agents.registry import get_adapter

    adapter = get_adapter("cursor")
    paths = adapter.discover(root)
    if include_subagents:
        return paths
    return [p for p in paths if "subagents" not in p.parts]


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
    return ingest_agent_path(
        source,
        provider="cursor",
        raw_dir=raw_dir,
        parsed_dir=parsed_dir,
        redact=redact,
        copy_raw=copy_raw,
        workers=workers,
        manifest=manifest,
        force=force,
    )


def load_parsed_cursor_turns(path: Path) -> list[CursorTurn]:
    return load_parsed_turns(path)


def chunk_cursor_turns(
    turns: list[CursorTurn],
    chunk_size: int = 20,
    user_only: bool = False,
) -> list[list[CursorTurn]]:
    return chunk_turns(turns, chunk_size=chunk_size, user_only=user_only)


def format_cursor_chunk_for_extraction(chunk: list[CursorTurn]) -> str:
    return format_chunk_for_extraction(chunk)


def cursor_sessions_to_chat_sessions(parsed_dir: Path, chats_dir: Path) -> list[Path]:
    return agent_sessions_to_chat_sessions(parsed_dir, chats_dir, provider="cursor")
