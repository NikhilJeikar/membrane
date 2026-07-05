"""Tests for server ingest (email, calendar, search)."""

import json
from pathlib import Path

from membrane.ingest.email import parse_email_raw
from membrane.ingest.lifecycle import parse_server_source
from membrane.ingest.server_common import load_parsed_records, save_raw_envelope
from membrane.tracking.manifest import ManifestStore


def test_save_and_parse_email(tmp_path: Path):
    raw_dir = tmp_path / "email" / "raw"
    parsed_dir = tmp_path / "email" / "parsed"
    save_raw_envelope(
        "email",
        {
            "items": [
                {
                    "from": "friend@example.com",
                    "subject": "Gym schedule",
                    "snippet": "Can we move gym to Tue/Thu?",
                    "date": "2026-07-05T10:00:00+05:30",
                }
            ]
        },
        raw_dir,
    )
    raw_file = next(raw_dir.glob("*.json"))
    parsed_out = parsed_dir / f"{raw_file.stem}.jsonl"
    result = parse_email_raw(raw_file, parsed_out, redact=False)
    assert result is not None
    records = load_parsed_records(parsed_out)
    assert len(records) == 1
    assert records[0]["subject"] == "Gym schedule"
    assert records[0]["record_type"] == "email"


def test_parse_server_source_skips_unchanged(tmp_path: Path):
    raw_dir = tmp_path / "search" / "raw"
    parsed_dir = tmp_path / "search" / "parsed"
    manifest = ManifestStore(tmp_path / "manifest.json")

    save_raw_envelope("search", {"query": "fedora hyprland", "engine": "google"}, raw_dir)
    stats1 = parse_server_source("search", raw_dir, parsed_dir, manifest)
    assert stats1.processed == 1

    stats2 = parse_server_source("search", raw_dir, parsed_dir, manifest)
    assert stats2.processed == 0
    assert stats2.skipped == 1


def test_search_payload_single_item(tmp_path: Path):
    from membrane.ingest.search import parse_search_raw

    raw_dir = tmp_path / "raw"
    parsed_dir = tmp_path / "parsed"
    path = save_raw_envelope(
        "search",
        {"query": "shadow pa memory", "url": "https://example.com", "title": "Example"},
        raw_dir,
    )
    out = parse_search_raw(path, parsed_dir / f"{path.stem}.jsonl", redact=False)
    assert out is not None
    records = json.loads(out.read_text(encoding="utf-8").strip())
    assert records["query"] == "shadow pa memory"
