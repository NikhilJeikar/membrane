"""Parse raw email ingest into normalized JSONL."""

from __future__ import annotations

from pathlib import Path

from shadow_pa.ingest.server_common import (
    load_raw_envelope,
    normalize_items,
    write_parsed_records,
)
from shadow_pa.ingest.server_models import EmailPayload, ParsedEmailRecord
from shadow_pa.utils.redact import redact_text


def parse_email_payload(
    item: dict,
    ingest_id: str,
    *,
    redact: bool = True,
) -> ParsedEmailRecord:
    email = EmailPayload.model_validate(item)
    subject = redact_text(email.subject) if redact else email.subject
    snippet = redact_text(email.snippet) if redact else email.snippet
    body = redact_text(email.body) if redact else email.body
    sender = redact_text(email.sender) if redact else email.sender
    return ParsedEmailRecord(
        ingest_id=ingest_id,
        subject=subject,
        sender=sender,
        to=email.to,
        snippet=snippet or body[:500],
        body=body,
        date=email.date,
        thread_id=email.thread_id,
        labels=email.labels,
        is_self_sent=email.is_self_sent,
    )


def parse_email_raw(raw_path: Path, parsed_path: Path, *, redact: bool = True) -> Path | None:
    envelope = load_raw_envelope(raw_path)
    items = normalize_items(envelope.payload)
    if not items:
        return None
    records = [parse_email_payload(item, envelope.id, redact=redact) for item in items]
    write_parsed_records(parsed_path, records)
    return parsed_path
