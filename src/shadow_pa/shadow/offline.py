"""Heuristic memory extraction without a local LLM (CPU-only)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from shadow_pa.ingest.cursor import load_parsed_cursor_turns
from shadow_pa.ingest.server_common import format_records_for_extraction, load_parsed_records
from shadow_pa.ingest.whatsapp import load_parsed_messages
from shadow_pa.memory.models import (
    EpisodeEntry,
    MemoryCategory,
    MemoryProposal,
    MemorySource,
    PreferenceEntry,
    ProfileEntry,
)
from shadow_pa.memory.store import MemoryStore
from shadow_pa.tracking.manifest import IngestManifest, ManifestStore
from shadow_pa.tracking.stats import ExtractStats
from shadow_pa.utils.parallel import default_workers
from shadow_pa.utils.progress import ProgressCallback, noop_progress

SOURCE_EXTRACT_CONFIG: dict[str, tuple[MemorySource, str]] = {
    "email": (MemorySource.EMAIL, "Email"),
    "calendar": (MemorySource.CALENDAR, "Calendar"),
    "search": (MemorySource.SEARCH, "Search"),
}

TOPIC_KEYWORDS: dict[str, str] = {
    "fedora": "Uses Fedora Linux",
    "hyprland": "Uses Hyprland",
    "python": "Works with Python",
    "openrgb": "Works on OpenRGB project",
    "ollama": "Uses local Ollama / LLMs",
    "whatsapp": "Uses WhatsApp for personal data",
    "wikipedia": "Building Wikipedia summarization data",
    "distill": "Interested in model distillation",
    "summariz": "Interested in summarization",
}


def _keyword_profiles(text: str, source: MemorySource) -> list[MemoryProposal]:
    lowered = text.lower()
    proposals: list[MemoryProposal] = []
    for key, value in TOPIC_KEYWORDS.items():
        if key in lowered:
            proposals.append(
                MemoryProposal(
                    category=MemoryCategory.PROFILE,
                    source=source,
                    reason="Offline: keyword match",
                    profile=ProfileEntry(
                        key=f"interest_{key}",
                        value=value,
                        confidence=0.6,
                        source=source,
                        evidence=[key],
                    ),
                )
            )
    return proposals


def offline_extract_cursor_file(parsed_path: Path, parsed_dir: Path) -> list[MemoryProposal]:
    turns = load_parsed_cursor_turns(parsed_path)
    user_msgs = [t.content for t in turns if t.role == "user"]
    if not user_msgs:
        return []

    proposals: list[MemoryProposal] = []
    meta_path = parsed_dir / f"{parsed_path.stem}.meta.json"
    workspace: str | None = None
    if meta_path.exists():
        workspace = json.loads(meta_path.read_text(encoding="utf-8")).get("workspace_hint")

    if workspace:
        proposals.append(
            MemoryProposal(
                category=MemoryCategory.PROFILE,
                source=MemorySource.CURSOR,
                reason="Offline: Cursor workspace",
                profile=ProfileEntry(
                    key="cursor_project",
                    value=workspace.replace("-", " "),
                    confidence=0.85,
                    source=MemorySource.CURSOR,
                    evidence=[workspace],
                ),
            )
        )

    combined = "\n".join(user_msgs)
    proposals.extend(_keyword_profiles(combined, MemorySource.CURSOR))

    topics = "; ".join(msg[:100].replace("\n", " ") for msg in user_msgs[:6])
    if len(topics) > 400:
        topics = topics[:397] + "..."
    proposals.append(
        MemoryProposal(
            category=MemoryCategory.EPISODE,
            source=MemorySource.CURSOR,
            reason="Offline: Cursor session topics",
            episode=EpisodeEntry(
                summary=f"Cursor session ({parsed_path.stem}): {topics}",
                tags=["cursor", "dev", workspace or "general"],
                source=MemorySource.CURSOR,
                raw_ref=parsed_path.name,
            ),
        )
    )

    avg_len = sum(len(m) for m in user_msgs) / len(user_msgs)
    if avg_len < 120:
        pref = "writes short, direct prompts in Cursor"
    elif avg_len > 400:
        pref = "writes long, detailed prompts in Cursor"
    else:
        pref = "writes medium-length prompts in Cursor"

    proposals.append(
        MemoryProposal(
            category=MemoryCategory.PREFERENCE,
            source=MemorySource.CURSOR,
            reason="Offline: inferred from prompt length",
            preference=PreferenceEntry(
                key="cursor_prompt_style",
                value=pref,
                strength=0.55,
                source=MemorySource.CURSOR,
                evidence=[f"avg_chars={avg_len:.0f}"],
            ),
        )
    )
    return proposals


def offline_extract_whatsapp_file(parsed_path: Path) -> list[MemoryProposal]:
    messages = load_parsed_messages(parsed_path)
    self_msgs = [m.text for m in messages if m.is_self]
    if not self_msgs:
        return []

    combined = "\n".join(self_msgs)
    proposals = _keyword_profiles(combined, MemorySource.WHATSAPP)

    sample = "; ".join(m[:80].replace("\n", " ") for m in self_msgs[:5])
    proposals.append(
        MemoryProposal(
            category=MemoryCategory.EPISODE,
            source=MemorySource.WHATSAPP,
            reason="Offline: WhatsApp self messages",
            episode=EpisodeEntry(
                summary=f"WhatsApp ({parsed_path.stem}): {sample[:400]}",
                tags=["whatsapp"],
                source=MemorySource.WHATSAPP,
                raw_ref=parsed_path.name,
            ),
        )
    )
    return proposals


def offline_extract_server_file(
    parsed_path: Path,
    source: MemorySource,
    *,
    tag: str,
) -> list[MemoryProposal]:
    records = load_parsed_records(parsed_path)
    if not records:
        return []

    text = format_records_for_extraction(records)
    proposals = _keyword_profiles(text, source)

    sample = text[:400].replace("\n", " ")
    if len(sample) == 400:
        sample = sample[:397] + "..."
    proposals.append(
        MemoryProposal(
            category=MemoryCategory.EPISODE,
            source=source,
            reason=f"Offline: {tag} batch summary",
            episode=EpisodeEntry(
                summary=f"{tag} ({parsed_path.stem}): {sample}",
                tags=[tag.lower(), "server"],
                source=source,
                raw_ref=parsed_path.name,
            ),
        )
    )

    queries = [r.get("query", "") for r in records if r.get("record_type") == "search"]
    if queries:
        top = ", ".join(q[:60] for q in queries[:8])
        proposals.append(
            MemoryProposal(
                category=MemoryCategory.EPISODE,
                source=source,
                reason="Offline: recent search topics",
                episode=EpisodeEntry(
                    summary=f"Search interests: {top}",
                    tags=["search", "interests"],
                    source=source,
                    raw_ref=parsed_path.name,
                ),
            )
        )

    events = [r.get("title", "") for r in records if r.get("record_type") == "calendar"]
    if events:
        top = ", ".join(e[:60] for e in events[:6])
        proposals.append(
            MemoryProposal(
                category=MemoryCategory.EPISODE,
                source=source,
                reason="Offline: calendar events",
                episode=EpisodeEntry(
                    summary=f"Calendar: {top}",
                    tags=["calendar", "schedule"],
                    source=source,
                    raw_ref=parsed_path.name,
                ),
            )
        )

    return proposals


class OfflineExtractor:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def _extract_paths_parallel(
        self,
        paths: list[Path],
        extract_fn,
        *,
        workers: int = 0,
        auto_propose: bool = True,
        on_progress: ProgressCallback | None = None,
        progress_label: str = "Offline extract",
    ) -> list[MemoryProposal]:
        if not paths:
            return []

        report = on_progress or noop_progress
        total = len(paths)
        report(0, total, f"{progress_label} (0/{total})")

        all_proposals: list[MemoryProposal] = []
        pool_size = min(default_workers(workers), len(paths))
        completed = 0

        if pool_size <= 1:
            for path in paths:
                all_proposals.extend(extract_fn(path))
                completed += 1
                report(completed, total, f"{progress_label} ({completed}/{total})")
        else:
            with ThreadPoolExecutor(max_workers=pool_size) as pool:
                futures = {pool.submit(extract_fn, path): path for path in paths}
                for future in as_completed(futures):
                    all_proposals.extend(future.result())
                    completed += 1
                    report(completed, total, f"{progress_label} ({completed}/{total})")

        if auto_propose:
            report(completed, total, f"{progress_label} — saving proposals…")
            for proposal in all_proposals:
                self.store.propose(proposal)
        return all_proposals

    def extract_cursor_parsed_dir(
        self,
        parsed_dir: Path,
        *,
        auto_propose: bool = True,
        workers: int = 0,
        on_progress: ProgressCallback | None = None,
        manifest: ManifestStore | None = None,
        only_new: bool = True,
        force: bool = False,
    ) -> ExtractStats:
        all_paths = sorted(p for p in parsed_dir.glob("*.jsonl") if ".meta." not in p.name)
        paths: list[Path] = []
        skipped = 0
        for path in all_paths:
            raw_key = IngestManifest.logical_key(path)
            if manifest and only_new and not force:
                if not manifest.needs_extract("cursor", raw_key, path, force=False):
                    skipped += 1
                    continue
            paths.append(path)

        def extract_one(path: Path) -> list[MemoryProposal]:
            return offline_extract_cursor_file(path, parsed_dir)

        proposals = self._extract_paths_parallel(
            paths,
            extract_one,
            workers=workers,
            auto_propose=auto_propose,
            on_progress=on_progress,
            progress_label="Cursor sessions",
        )
        if manifest and auto_propose:
            for path in paths:
                manifest.record_extract("cursor", IngestManifest.logical_key(path), path)
        return ExtractStats(
            processed_files=len(paths),
            skipped_files=skipped,
            proposals=len(proposals),
        )

    def extract_whatsapp_parsed_dir(
        self,
        parsed_dir: Path,
        *,
        auto_propose: bool = True,
        workers: int = 0,
        on_progress: ProgressCallback | None = None,
        manifest: ManifestStore | None = None,
        only_new: bool = True,
        force: bool = False,
    ) -> ExtractStats:
        all_paths = sorted(parsed_dir.glob("*.jsonl"))
        paths: list[Path] = []
        skipped = 0
        for path in all_paths:
            raw_key = IngestManifest.logical_key(path)
            if manifest and only_new and not force:
                if not manifest.needs_extract("whatsapp", raw_key, path, force=False):
                    skipped += 1
                    continue
            paths.append(path)

        proposals = self._extract_paths_parallel(
            paths,
            offline_extract_whatsapp_file,
            workers=workers,
            auto_propose=auto_propose,
            on_progress=on_progress,
            progress_label="WhatsApp files",
        )
        if manifest and auto_propose:
            for path in paths:
                manifest.record_extract("whatsapp", IngestManifest.logical_key(path), path)
        return ExtractStats(
            processed_files=len(paths),
            skipped_files=skipped,
            proposals=len(proposals),
        )

    def extract_server_parsed_dir(
        self,
        source_key: str,
        parsed_dir: Path,
        *,
        auto_propose: bool = True,
        workers: int = 0,
        on_progress: ProgressCallback | None = None,
        manifest: ManifestStore | None = None,
        only_new: bool = True,
        force: bool = False,
    ) -> ExtractStats:
        mem_source, label = SOURCE_EXTRACT_CONFIG[source_key]
        all_paths = sorted(parsed_dir.glob("*.jsonl"))
        paths: list[Path] = []
        skipped = 0
        for path in all_paths:
            raw_key = IngestManifest.logical_key(path)
            if manifest and only_new and not force:
                if not manifest.needs_extract(source_key, raw_key, path, force=False):
                    skipped += 1
                    continue
            paths.append(path)

        def extract_one(path: Path) -> list[MemoryProposal]:
            return offline_extract_server_file(path, mem_source, tag=label)

        proposals = self._extract_paths_parallel(
            paths,
            extract_one,
            workers=workers,
            auto_propose=auto_propose,
            on_progress=on_progress,
            progress_label=f"{label} batches",
        )
        if manifest and auto_propose:
            for path in paths:
                manifest.record_extract(source_key, IngestManifest.logical_key(path), path)
        return ExtractStats(
            processed_files=len(paths),
            skipped_files=skipped,
            proposals=len(proposals),
        )

    def extract_email_parsed_dir(self, parsed_dir: Path, **kwargs) -> ExtractStats:
        return self.extract_server_parsed_dir("email", parsed_dir, **kwargs)

    def extract_calendar_parsed_dir(self, parsed_dir: Path, **kwargs) -> ExtractStats:
        return self.extract_server_parsed_dir("calendar", parsed_dir, **kwargs)

    def extract_search_parsed_dir(self, parsed_dir: Path, **kwargs) -> ExtractStats:
        return self.extract_server_parsed_dir("search", parsed_dir, **kwargs)
