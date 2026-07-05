"""Shared helpers for server ingest sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shadow_pa.ingest.server_models import SERVER_SOURCES, ServerIngestEnvelope, ServerSource
from shadow_pa.memory.models import new_id


def normalize_items(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if "items" in payload and isinstance(payload["items"], list):
        return payload["items"]
    return [payload]


def save_raw_envelope(
    source: ServerSource,
    payload: dict[str, Any] | list[dict[str, Any]],
    raw_dir: Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    envelope = ServerIngestEnvelope(
        id=new_id(),
        source=source,
        payload=payload,
        metadata=metadata or {},
    )
    path = raw_dir / f"{envelope.id}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_raw_envelope(path: Path) -> ServerIngestEnvelope:
    return ServerIngestEnvelope.model_validate_json(path.read_text(encoding="utf-8"))


def write_parsed_records(parsed_path: Path, records: list[Any]) -> None:
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    with parsed_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.model_dump(mode="json")) + "\n")


def load_parsed_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def format_records_for_extraction(records: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for record in records:
        kind = record.get("record_type")
        if kind == "email":
            header = f"[EMAIL {record.get('date', '')}]"
            if record.get("is_self_sent"):
                header += " (sent by self)"
            lines.append(
                f"{header}\nFrom: {record.get('sender', '')}\n"
                f"Subject: {record.get('subject', '')}\n"
                f"{record.get('snippet') or record.get('body', '')}"
            )
        elif kind == "calendar":
            lines.append(
                f"[CALENDAR {record.get('start', '')}] {record.get('title', '')}\n"
                f"Location: {record.get('location', '')}\n"
                f"{record.get('description', '')[:300]}"
            )
        elif kind == "search":
            lines.append(
                f"[SEARCH {record.get('timestamp', '')}] {record.get('query', '')}\n"
                f"{record.get('title', '')} {record.get('url', '')}"
            )
    return "\n\n".join(lines)


def chunk_records(records: list[dict[str, Any]], chunk_size: int = 10) -> list[list[dict[str, Any]]]:
    return [records[i : i + chunk_size] for i in range(0, len(records), chunk_size)]
