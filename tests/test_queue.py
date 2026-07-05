"""Tests for ingest queue counting."""

from pathlib import Path

from membrane.config_policy import TrainingPolicy
from membrane.tracking.manifest import ManifestStore
from membrane.tracking.queue import build_ingest_queue_stats
from membrane.config import Settings


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_queue_counts_needs_parse_and_extract(tmp_path):
    settings = Settings(root=tmp_path)
    manifest = ManifestStore(settings.manifest_path)
    policy = TrainingPolicy.default()

    raw = settings.server_raw_dir("email")
    parsed = settings.server_parsed_dir("email")
    _write(raw / "msg1.json", '{"subject":"hi"}')
    _write(raw / "msg2.json", '{"subject":"bye"}')
    _write(parsed / "msg1.jsonl", '{"role":"user","content":"hello"}\n')

    stats = build_ingest_queue_stats(settings, manifest, policy)
    email = stats["sources"]["email"]
    assert email["raw"] == 2
    assert email["parsed"] == 1
    assert email["needs_parse"] == 1
    assert email["needs_extract"] == 1
    assert email["needs_train"] == 1
    assert email["train_enabled"] is True
    assert stats["totals"]["needs_parse"] == 1
    assert stats["totals"]["needs_extract"] == 1


def test_queue_ignores_gitkeep(tmp_path):
    settings = Settings(root=tmp_path)
    manifest = ManifestStore(settings.manifest_path)
    policy = TrainingPolicy.default()

    raw = settings.whatsapp_raw_dir
    parsed = settings.whatsapp_parsed_dir
    raw.mkdir(parents=True, exist_ok=True)
    parsed.mkdir(parents=True, exist_ok=True)
    (raw / ".gitkeep").write_text("", encoding="utf-8")
    (parsed / ".gitkeep").write_text("", encoding="utf-8")

    stats = build_ingest_queue_stats(settings, manifest, policy)
    whatsapp = stats["sources"]["whatsapp"]
    assert whatsapp["raw"] == 0
    assert whatsapp["needs_parse"] == 0


def test_queue_skips_extract_when_already_extracted(tmp_path):
    settings = Settings(root=tmp_path)
    manifest = ManifestStore(settings.manifest_path)
    policy = TrainingPolicy.default()

    raw = settings.server_raw_dir("search")
    parsed = settings.server_parsed_dir("search")
    raw_file = _write(raw / "q1.json", '{"query":"test"}')
    parsed_file = _write(parsed / "q1.jsonl", '{"role":"user","content":"test"}\n')
    manifest.record_ingest("search", raw_file, parsed_file)
    manifest.record_extract("search", "q1", parsed_file)

    stats = build_ingest_queue_stats(settings, manifest, policy)
    search = stats["sources"]["search"]
    assert search["needs_parse"] == 0
    assert search["needs_extract"] == 0
    assert search["needs_train"] == 0
