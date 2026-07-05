"""Parse raw search history ingest into normalized JSONL."""

from __future__ import annotations

from pathlib import Path

from membrane.ingest.server_common import (
    load_raw_envelope,
    normalize_items,
    write_parsed_records,
)
from membrane.ingest.server_models import ParsedSearchRecord, SearchHistoryPayload
from membrane.utils.redact import redact_text


def parse_search_payload(
    item: dict,
    ingest_id: str,
    *,
    redact: bool = True,
) -> ParsedSearchRecord:
    entry = SearchHistoryPayload.model_validate(item)
    query = redact_text(entry.query) if redact else entry.query
    title = redact_text(entry.title) if redact else entry.title
    url = redact_text(entry.url) if redact else entry.url
    return ParsedSearchRecord(
        ingest_id=ingest_id,
        query=query,
        url=url,
        title=title,
        timestamp=entry.timestamp,
        engine=entry.engine,
    )


def parse_search_raw(raw_path: Path, parsed_path: Path, *, redact: bool = True) -> Path | None:
    envelope = load_raw_envelope(raw_path)
    items = normalize_items(envelope.payload)
    if not items:
        return None
    records = [parse_search_payload(item, envelope.id, redact=redact) for item in items]
    write_parsed_records(parsed_path, records)
    return parsed_path
