"""Batch parse server-ingested raw files (email, calendar, search)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from membrane.config import Settings
from membrane.ingest.calendar import parse_calendar_raw
from membrane.ingest.email import parse_email_raw
from membrane.ingest.search import parse_search_raw
from membrane.ingest.server_models import SERVER_SOURCES, ServerSource
from membrane.tracking.manifest import ManifestStore
from membrane.tracking.stats import IngestStats

PARSERS: dict[ServerSource, Callable[..., Path | None]] = {
    "email": parse_email_raw,
    "calendar": parse_calendar_raw,
    "search": parse_search_raw,
}


def parse_server_source(
    source: ServerSource,
    raw_dir: Path,
    parsed_dir: Path,
    manifest: ManifestStore | None = None,
    *,
    redact: bool = True,
    force: bool = False,
) -> IngestStats:
    stats = IngestStats()
    parser = PARSERS[source]
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    if manifest:
        for raw_file in raw_dir.glob("*.json"):
            parsed_file = parsed_dir / f"{raw_file.stem}.jsonl"
            manifest.reconcile_existing(source, raw_file, parsed_file)

    for raw_path in sorted(raw_dir.glob("*.json")):
        parsed_out = parsed_dir / f"{raw_path.stem}.jsonl"
        if manifest and not manifest.needs_ingest(source, raw_path, parsed_out, force=force):
            stats.skipped += 1
            continue
        out = parser(raw_path, parsed_out, redact=redact)
        if out is None:
            continue
        stats.processed += 1
        stats.outputs.append(out)
        if manifest:
            manifest.record_ingest(source, raw_path, out)

    return stats


def parse_all_server_sources(
    settings: Settings,
    manifest: ManifestStore | None = None,
    *,
    redact: bool = True,
    force: bool = False,
) -> dict[str, IngestStats]:
    results: dict[str, IngestStats] = {}
    for source in SERVER_SOURCES:
        results[source] = parse_server_source(
            source,
            settings.server_raw_dir(source),
            settings.server_parsed_dir(source),
            manifest,
            redact=redact,
            force=force,
        )
    return results


def clear_ingest_data(
    settings: Settings,
    source: str,
    manifest: ManifestStore | None = None,
) -> dict[str, int]:
    """Delete raw/parsed ingest files and manifest entries for a source."""
    from membrane.ingest.agents.registry import list_providers

    counts = {"raw": 0, "parsed": 0, "chats": 0, "manifest": 0}

    def _unlink_files(directory: Path, pattern: str = "*") -> int:
        if not directory.exists():
            return 0
        removed = 0
        for path in directory.glob(pattern):
            if path.is_file():
                path.unlink()
                removed += 1
        return removed

    if source in list_providers() or source in settings.list_agent_providers():
        counts["raw"] = _unlink_files(settings.resolved_agent_raw_dir(source), "*.jsonl")
        counts["parsed"] = _unlink_files(settings.resolved_agent_parsed_dir(source))
        counts["chats"] = _unlink_files(settings.chats_dir, f"{source}-*.json")
    elif source == "whatsapp":
        counts["raw"] = _unlink_files(settings.whatsapp_raw_dir)
        counts["parsed"] = _unlink_files(settings.whatsapp_parsed_dir, "*.jsonl")
    elif source in SERVER_SOURCES:
        counts["raw"] = _unlink_files(settings.server_raw_dir(source), "*.json")
        counts["parsed"] = _unlink_files(settings.server_parsed_dir(source), "*.jsonl")
    else:
        raise ValueError(f"No ingest layout for source: {source}")

    if manifest:
        counts["manifest"] = manifest.remove_source_entries(source)

    return counts
