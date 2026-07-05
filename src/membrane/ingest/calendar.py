"""Parse raw calendar ingest into normalized JSONL."""

from __future__ import annotations

from pathlib import Path

from membrane.ingest.server_common import (
    load_raw_envelope,
    normalize_items,
    write_parsed_records,
)
from membrane.ingest.server_models import CalendarEventPayload, ParsedCalendarRecord
from membrane.utils.redact import redact_text


def parse_calendar_payload(
    item: dict,
    ingest_id: str,
    *,
    redact: bool = True,
) -> ParsedCalendarRecord:
    event = CalendarEventPayload.model_validate(item)
    title = redact_text(event.title) if redact else event.title
    description = redact_text(event.description) if redact else event.description
    location = redact_text(event.location) if redact else event.location
    return ParsedCalendarRecord(
        ingest_id=ingest_id,
        title=title,
        start=event.start,
        end=event.end,
        location=location,
        description=description,
        attendees=event.attendees,
        calendar_name=event.calendar_name,
        all_day=event.all_day,
    )


def parse_calendar_raw(raw_path: Path, parsed_path: Path, *, redact: bool = True) -> Path | None:
    envelope = load_raw_envelope(raw_path)
    items = normalize_items(envelope.payload)
    if not items:
        return None
    records = [parse_calendar_payload(item, envelope.id, redact=redact) for item in items]
    write_parsed_records(parsed_path, records)
    return parsed_path
