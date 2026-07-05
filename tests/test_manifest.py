"""Tests for hash-based ingest/extract tracking."""

from pathlib import Path

from shadow_pa.tracking.manifest import IngestManifest, ManifestStore, file_sha256


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_file_sha256_stable(tmp_path: Path):
    path = _write(tmp_path / "a.txt", "hello")
    assert file_sha256(path) == file_sha256(path)
    assert file_sha256(path) != file_sha256(_write(tmp_path / "b.txt", "world"))


def test_needs_ingest_skips_unchanged(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    store = ManifestStore(manifest_path)
    raw = _write(tmp_path / "raw" / "sess.jsonl", '{"role":"user"}\n')
    parsed = _write(tmp_path / "parsed" / "sess.jsonl", '{"role":"user","content":"hi"}\n')

    assert store.needs_ingest("cursor", raw, parsed) is True
    store.record_ingest("cursor", raw, parsed)
    assert store.needs_ingest("cursor", raw, parsed) is False

    raw.write_text('{"role":"user","updated":true}\n', encoding="utf-8")
    assert store.needs_ingest("cursor", raw, parsed) is True


def test_needs_extract_skips_already_extracted(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    store = ManifestStore(manifest_path)
    raw = _write(tmp_path / "raw" / "sess.jsonl", "raw")
    parsed = _write(tmp_path / "parsed" / "sess.jsonl", "parsed")

    store.record_ingest("cursor", raw, parsed)
    assert store.needs_extract("cursor", "sess", parsed) is True
    store.record_extract("cursor", "sess", parsed)
    assert store.needs_extract("cursor", "sess", parsed) is False

    parsed.write_text("parsed v2", encoding="utf-8")
    assert store.needs_extract("cursor", "sess", parsed) is True


def test_reconcile_existing_backfills(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    store = ManifestStore(manifest_path)
    raw = _write(tmp_path / "raw" / "abc.jsonl", "raw content")
    parsed = _write(tmp_path / "parsed" / "abc.jsonl", "parsed content")

    store.reconcile_existing("cursor", raw, parsed)
    entry = store.manifest.get_entry("cursor", "abc")
    assert entry is not None
    assert entry.raw_sha256 == file_sha256(raw)
    assert entry.parsed_sha256 == file_sha256(parsed)
    assert entry.extracted_at is None


def test_reconcile_parsed_dir(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    store = ManifestStore(manifest_path)
    raw_dir = tmp_path / "raw"
    parsed_dir = tmp_path / "parsed"
    raw_dir.mkdir()
    parsed_dir.mkdir()
    _write(raw_dir / "one.jsonl", "r1")
    _write(parsed_dir / "one.jsonl", "p1")
    _write(raw_dir / "two.jsonl", "r2")
    _write(parsed_dir / "two.jsonl", "p2")

    added = store.reconcile_parsed_dir("cursor", raw_dir, parsed_dir)
    assert added == 2
    assert len(store.manifest.entries) == 2

    added_again = store.reconcile_parsed_dir("cursor", raw_dir, parsed_dir)
    assert added_again == 0


def test_mark_parsed_extracted(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    store = ManifestStore(manifest_path)
    parsed_dir = tmp_path / "parsed"
    parsed_dir.mkdir()
    path = _write(parsed_dir / "sess.jsonl", "content")

    marked = store.mark_parsed_extracted("cursor", parsed_dir)
    assert marked == 1
    entry = store.manifest.get_entry("cursor", "sess")
    assert entry is not None
    assert entry.extracted_parsed_sha256 == file_sha256(path)

    assert store.mark_parsed_extracted("cursor", parsed_dir) == 0


def test_logical_key_uses_stem():
    assert IngestManifest.logical_key(Path("/data/cursor/parsed/uuid-here.jsonl")) == "uuid-here"
