"""Normalized models for AI agent session transcripts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentTurn(BaseModel):
    role: str
    content: str
    session_id: str
    source_file: str
    turn_index: int
    has_tool_calls: bool = False
    agent: str = "unknown"


class AgentSession(BaseModel):
    session_id: str
    source_file: str
    agent: str
    workspace_hint: str | None = None
    turns: list[AgentTurn] = Field(default_factory=list)
