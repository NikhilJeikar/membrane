"""Track raw → parsed → extracted state via content hashes."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> datetime:
    return datetime.now().astimezone()


class ManifestEntry(BaseModel):
    source: str
    raw_key: str
    raw_sha256: str
    raw_path: str | None = None
    parsed_path: str | None = None
    parsed_sha256: str | None = None
    parsed_at: datetime | None = None
    extracted_parsed_sha256: str | None = None
    extracted_at: datetime | None = None


class IngestManifest(BaseModel):
    version: int = 1
    entries: dict[str, ManifestEntry] = Field(default_factory=dict)

    @staticmethod
    def entry_key(source: str, raw_key: str) -> str:
        return f"{source}:{raw_key}"

    @staticmethod
    def logical_key(path: Path) -> str:
        """Stable id shared by raw/parsed variants (e.g. session uuid or chat name)."""
        return path.stem

    def get_entry(self, source: str, raw_key: str) -> ManifestEntry | None:
        return self.entries.get(self.entry_key(source, raw_key))


class ManifestStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._manifest = self._load()

    def _load(self) -> IngestManifest:
        if not self.path.exists():
            return IngestManifest()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return IngestManifest.model_validate(data)

    def save(self) -> None:
        self.path.write_text(
            self._manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @property
    def manifest(self) -> IngestManifest:
        return self._manifest

    def reconcile_existing(
        self,
        source: str,
        raw_path: Path,
        parsed_path: Path,
    ) -> None:
        """Register an already-ingested pair without re-parsing."""
        if not raw_path.exists() or not parsed_path.exists():
            return
        key = IngestManifest.entry_key(source, IngestManifest.logical_key(raw_path))
        if key in self._manifest.entries:
            return
        self._manifest.entries[key] = ManifestEntry(
            source=source,
            raw_key=IngestManifest.logical_key(raw_path),
            raw_sha256=file_sha256(raw_path),
            raw_path=str(raw_path),
            parsed_path=str(parsed_path),
            parsed_sha256=file_sha256(parsed_path),
            parsed_at=_utc_now(),
        )
        self.save()

    def needs_ingest(
        self,
        source: str,
        raw_path: Path,
        parsed_path: Path,
        *,
        force: bool = False,
    ) -> bool:
        if force or not raw_path.exists():
            return bool(raw_path.exists())
        raw_hash = file_sha256(raw_path)
        key = IngestManifest.entry_key(source, IngestManifest.logical_key(raw_path))
        entry = self._manifest.entries.get(key)
        if entry is None:
            return True
        if entry.raw_sha256 != raw_hash:
            return True
        if not parsed_path.exists():
            return True
        return False

    def record_ingest(
        self,
        source: str,
        raw_path: Path,
        parsed_path: Path,
    ) -> ManifestEntry:
        key = IngestManifest.entry_key(source, IngestManifest.logical_key(raw_path))
        entry = ManifestEntry(
            source=source,
            raw_key=IngestManifest.logical_key(raw_path),
            raw_sha256=file_sha256(raw_path),
            raw_path=str(raw_path),
            parsed_path=str(parsed_path),
            parsed_sha256=file_sha256(parsed_path) if parsed_path.exists() else None,
            parsed_at=_utc_now(),
            extracted_parsed_sha256=None,
            extracted_at=None,
        )
        self._manifest.entries[key] = entry
        self.save()
        return entry

    def needs_extract(
        self,
        source: str,
        raw_key: str,
        parsed_path: Path,
        *,
        force: bool = False,
    ) -> bool:
        if force or not parsed_path.exists():
            return parsed_path.exists()
        parsed_hash = file_sha256(parsed_path)
        entry = self._manifest.get_entry(source, raw_key)
        if entry is None:
            return True
        if entry.parsed_sha256 and entry.parsed_sha256 != parsed_hash:
            return True
        if entry.extracted_parsed_sha256 == parsed_hash:
            return False
        return True

    def record_extract(self, source: str, raw_key: str, parsed_path: Path) -> None:
        key = IngestManifest.entry_key(source, raw_key)
        entry = self._manifest.entries.get(key)
        parsed_hash = file_sha256(parsed_path)
        if entry is None:
            entry = ManifestEntry(
                source=source,
                raw_key=raw_key,
                raw_sha256="",
                parsed_path=str(parsed_path),
                parsed_sha256=parsed_hash,
            )
        entry.parsed_sha256 = parsed_hash
        entry.parsed_path = str(parsed_path)
        entry.extracted_parsed_sha256 = parsed_hash
        entry.extracted_at = _utc_now()
        self._manifest.entries[key] = entry
        self.save()

    def list_stale_extracted(self, source: str) -> list[str]:
        """Raw keys where parsed changed since last extract."""
        stale: list[str] = []
        for key, entry in self._manifest.entries.items():
            if not key.startswith(f"{source}:"):
                continue
            if not entry.parsed_path:
                continue
            parsed = Path(entry.parsed_path)
            if not parsed.exists():
                continue
            current = file_sha256(parsed)
            if entry.extracted_parsed_sha256 != current:
                stale.append(entry.raw_key)
        return stale

    def summary(self) -> dict[str, int]:
        by_source: dict[str, dict[str, int]] = {}
        for entry in self._manifest.entries.values():
            bucket = by_source.setdefault(entry.source, {"ingested": 0, "extracted": 0})
            bucket["ingested"] += 1
            if entry.extracted_at:
                bucket["extracted"] += 1
        return {f"{src}_{k}": v for src, counts in by_source.items() for k, v in counts.items()}

    def reconcile_parsed_dir(
        self,
        source: str,
        raw_dir: Path,
        parsed_dir: Path,
    ) -> int:
        """Backfill manifest entries for existing raw+parsed pairs."""
        added = 0
        for raw_file in sorted(raw_dir.glob("*.jsonl")):
            parsed_file = parsed_dir / raw_file.name
            if not parsed_file.exists():
                continue
            key = IngestManifest.entry_key(source, IngestManifest.logical_key(raw_file))
            if key in self._manifest.entries:
                continue
            self.reconcile_existing(source, raw_file, parsed_file)
            added += 1
        if added:
            self.save()
        return added

    def mark_parsed_extracted(self, source: str, parsed_dir: Path) -> int:
        """Mark all parsed files as extracted (migration helper)."""
        marked = 0
        for path in sorted(parsed_dir.glob("*.jsonl")):
            if ".meta." in path.name:
                continue
            raw_key = IngestManifest.logical_key(path)
            key = IngestManifest.entry_key(source, raw_key)
            entry = self._manifest.entries.get(key)
            parsed_hash = file_sha256(path)
            if entry and entry.extracted_parsed_sha256 == parsed_hash:
                continue
            self.record_extract(source, raw_key, path)
            marked += 1
        return marked

    def clear_extract_state(self, source: str) -> int:
        """Reset extract tracking so source can be re-extracted from scratch."""
        cleared = 0
        for key, entry in self._manifest.entries.items():
            if not key.startswith(f"{source}:"):
                continue
            if entry.extracted_at or entry.extracted_parsed_sha256:
                entry.extracted_at = None
                entry.extracted_parsed_sha256 = None
                cleared += 1
        if cleared:
            self.save()
        return cleared

    def remove_source_entries(self, source: str) -> int:
        """Remove all manifest entries for a source."""
        to_remove = [k for k in self._manifest.entries if k.startswith(f"{source}:")]
        for key in to_remove:
            del self._manifest.entries[key]
        if to_remove:
            self.save()
        return len(to_remove)
