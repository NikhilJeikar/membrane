"""Models for server-ingested personal data (email, calendar, search)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from shadow_pa.memory.models import _utc_now, new_id

ServerSource = Literal["email", "calendar", "search"]
SERVER_SOURCES: tuple[ServerSource, ...] = ("email", "calendar", "search")


class ServerIngestEnvelope(BaseModel):
    id: str = Field(default_factory=new_id)
    source: ServerSource
    received_at: datetime = Field(default_factory=_utc_now)
    payload: dict[str, Any] | list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmailPayload(BaseModel):
    subject: str = ""
    sender: str = Field(default="", alias="from")
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    snippet: str = ""
    body: str = ""
    date: datetime | None = None
    thread_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    is_self_sent: bool = False

    model_config = {"populate_by_name": True}


class CalendarEventPayload(BaseModel):
    title: str
    start: datetime
    end: datetime | None = None
    location: str = ""
    description: str = ""
    attendees: list[str] = Field(default_factory=list)
    calendar_name: str = ""
    all_day: bool = False


class SearchHistoryPayload(BaseModel):
    query: str
    url: str = ""
    title: str = ""
    timestamp: datetime | None = None
    engine: str = ""


class ParsedEmailRecord(BaseModel):
    record_type: Literal["email"] = "email"
    ingest_id: str
    subject: str = ""
    sender: str = ""
    to: list[str] = Field(default_factory=list)
    snippet: str = ""
    body: str = ""
    date: datetime | None = None
    thread_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    is_self_sent: bool = False


class ParsedCalendarRecord(BaseModel):
    record_type: Literal["calendar"] = "calendar"
    ingest_id: str
    title: str
    start: datetime
    end: datetime | None = None
    location: str = ""
    description: str = ""
    attendees: list[str] = Field(default_factory=list)
    calendar_name: str = ""
    all_day: bool = False


class ParsedSearchRecord(BaseModel):
    record_type: Literal["search"] = "search"
    ingest_id: str
    query: str
    url: str = ""
    title: str = ""
    timestamp: datetime | None = None
    engine: str = ""


ParsedServerRecord = ParsedEmailRecord | ParsedCalendarRecord | ParsedSearchRecord
