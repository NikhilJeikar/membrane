"""Tests for clearing memory by source."""

from shadow_pa.memory.models import (
    MemoryCategory,
    MemoryProposal,
    MemorySource,
    ProfileEntry,
)
from shadow_pa.memory.store import MemoryStore
from shadow_pa.tracking.manifest import ManifestEntry, ManifestStore


def test_clear_source_removes_proposals_and_profile(tmp_path):
    store = MemoryStore(tmp_path)
    store.upsert_profile(ProfileEntry(key="manual", value="keep", source=MemorySource.MANUAL))
    store.upsert_profile(ProfileEntry(key="cursor_key", value="go", source=MemorySource.CURSOR))

    proposal = MemoryProposal(
        category=MemoryCategory.PROFILE,
        source=MemorySource.CURSOR,
        profile=ProfileEntry(key="x", value="y", source=MemorySource.CURSOR),
    )
    store.propose(proposal)
    store.approve(proposal.id)

    counts = store.clear_source("cursor")
    assert counts["proposals_removed"] >= 1
    assert counts["profile_removed"] == 2
    profile = store.load_profile()
    assert len(profile) == 1
    assert profile[0].key == "manual"


def test_clear_extract_state(tmp_path):
    manifest = ManifestStore(tmp_path / "manifest.json")
    manifest._manifest.entries["cursor:abc"] = ManifestEntry(
        source="cursor",
        raw_key="abc",
        raw_sha256="x",
        extracted_parsed_sha256="hash",
    )
    manifest.save()
    cleared = manifest.clear_extract_state("cursor")
    assert cleared == 1
    entry = manifest._manifest.entries["cursor:abc"]
    assert entry.extracted_parsed_sha256 is None


def test_remove_source_entries(tmp_path):
    manifest = ManifestStore(tmp_path / "manifest.json")
    manifest._manifest.entries["cursor:abc"] = ManifestEntry(
        source="cursor", raw_key="abc", raw_sha256="x"
    )
    manifest._manifest.entries["email:msg1"] = ManifestEntry(
        source="email", raw_key="msg1", raw_sha256="y"
    )
    manifest.save()
    removed = manifest.remove_source_entries("cursor")
    assert removed == 1
    assert "cursor:abc" not in manifest._manifest.entries
    assert "email:msg1" in manifest._manifest.entries


def test_clear_ingest_data_cursor(tmp_path):
    from shadow_pa.config import Settings
    from shadow_pa.ingest.lifecycle import clear_ingest_data

    settings = Settings(root=tmp_path)
    settings.cursor_raw_dir.mkdir(parents=True)
    settings.cursor_parsed_dir.mkdir(parents=True)
    settings.chats_dir.mkdir(parents=True)
    (settings.cursor_raw_dir / "s1.jsonl").write_text("{}", encoding="utf-8")
    (settings.cursor_parsed_dir / "s1.jsonl").write_text("{}", encoding="utf-8")
    (settings.cursor_parsed_dir / "s1.meta.json").write_text("{}", encoding="utf-8")
    (settings.chats_dir / "cursor-s1.json").write_text("{}", encoding="utf-8")
    (settings.chats_dir / "other.json").write_text("{}", encoding="utf-8")

    manifest = ManifestStore(settings.data_dir / "ingest_manifest.json")
    manifest._manifest.entries["cursor:s1"] = ManifestEntry(
        source="cursor", raw_key="s1", raw_sha256="x"
    )
    manifest.save()

    counts = clear_ingest_data(settings, "cursor", manifest=manifest)
    assert counts == {"raw": 1, "parsed": 2, "chats": 1, "manifest": 1}
    assert list(settings.cursor_raw_dir.glob("*")) == []
    assert list(settings.cursor_parsed_dir.glob("*")) == []
    assert (settings.chats_dir / "other.json").exists()
    assert "cursor:s1" not in manifest._manifest.entries
