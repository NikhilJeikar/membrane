"""Pydantic models for memory and learning artifacts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now().astimezone()


def new_id() -> str:
    return uuid4().hex[:12]


class MemoryCategory(StrEnum):
    PROFILE = "profile"
    PREFERENCE = "preference"
    EPISODE = "episode"


class MemorySource(StrEnum):
    MANUAL = "manual"
    WHATSAPP = "whatsapp"
    CURSOR = "cursor"
    CLAUDE = "claude"
    OPENAI = "openai"
    CHAT = "chat"
    EXTRACTOR = "extractor"
    EMAIL = "email"
    CALENDAR = "calendar"
    SEARCH = "search"
    BOOKS = "books"


AGENT_PROVIDERS = frozenset({"cursor", "claude", "openai", "continue", "codex", "windsurf"})


def memory_source_for_agent(provider: str) -> MemorySource:
    try:
        return MemorySource(provider)
    except ValueError:
        return MemorySource.CHAT


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProfileEntry(BaseModel):
    id: str = Field(default_factory=new_id)
    key: str
    value: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source: MemorySource = MemorySource.MANUAL
    updated_at: datetime = Field(default_factory=_utc_now)
    evidence: list[str] = Field(default_factory=list)


class PreferenceEntry(BaseModel):
    id: str = Field(default_factory=new_id)
    key: str
    value: str
    strength: float = Field(default=0.7, ge=0.0, le=1.0)
    source: MemorySource = MemorySource.MANUAL
    updated_at: datetime = Field(default_factory=_utc_now)
    evidence: list[str] = Field(default_factory=list)


class EpisodeEntry(BaseModel):
    id: str = Field(default_factory=new_id)
    summary: str
    date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    source: MemorySource = MemorySource.MANUAL
    created_at: datetime = Field(default_factory=_utc_now)
    raw_ref: str | None = None


class MemoryProposal(BaseModel):
    """A proposed memory update awaiting human review."""

    id: str = Field(default_factory=new_id)
    category: MemoryCategory
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = Field(default_factory=_utc_now)
    source: MemorySource = MemorySource.EXTRACTOR
    reason: str = ""
    profile: ProfileEntry | None = None
    preference: PreferenceEntry | None = None
    episode: EpisodeEntry | None = None

    def to_entry(self) -> ProfileEntry | PreferenceEntry | EpisodeEntry:
        if self.category == MemoryCategory.PROFILE and self.profile:
            return self.profile
        if self.category == MemoryCategory.PREFERENCE and self.preference:
            return self.preference
        if self.category == MemoryCategory.EPISODE and self.episode:
            return self.episode
        raise ValueError(f"Proposal {self.id} has no entry for category {self.category}")


class WhatsAppMessage(BaseModel):
    timestamp: datetime
    sender: str
    text: str
    is_self: bool = False


class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSession(BaseModel):
    id: str = Field(default_factory=new_id)
    turns: list[ChatTurn] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DPOExample(BaseModel):
    prompt: str
    chosen: str
    rejected: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SFTExample(BaseModel):
    messages: list[dict[str, str]]
    memory_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
