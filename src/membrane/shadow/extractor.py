"""Local memory extraction from chats (no cloud)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from membrane.config import PersonaConfig
from membrane.ingest.agents import (
    chunk_turns,
    format_chunk_for_extraction,
    get_adapter,
    load_parsed_turns,
)
from membrane.ingest.server_common import (
    chunk_records,
    format_records_for_extraction,
    load_parsed_records,
)
from membrane.ingest.whatsapp import (
    chunk_messages,
    format_chunk_for_extraction,
    load_parsed_messages,
)
from membrane.llm.ollama import OllamaClient, OllamaError
from membrane.memory.models import (
    EpisodeEntry,
    MemoryCategory,
    MemoryProposal,
    MemorySource,
    PreferenceEntry,
    ProfileEntry,
    memory_source_for_agent,
)
from membrane.memory.store import MemoryStore
from membrane.utils.parallel import default_workers
from membrane.tracking.manifest import IngestManifest, ManifestStore
from membrane.tracking.stats import ExtractStats
from membrane.utils.progress import ProgressCallback, noop_progress

SERVER_SOURCE_LABELS: dict[str, tuple[MemorySource, str]] = {
    "email": (MemorySource.EMAIL, "Email"),
    "calendar": (MemorySource.CALENDAR, "Calendar"),
    "search": (MemorySource.SEARCH, "Search"),
}

EXTRACTION_SYSTEM = """You extract structured memory about ONE person (the SELF user) from chat logs.
Rules:
- Extract facts about SELF only, not other people's private details.
- Prefer stable profile facts, communication preferences, and episodic summaries of plans/events.
- Do not invent information not supported by the chat.
- Return valid JSON only."""

EXTRACTION_USER_TEMPLATE = """Analyze this {source_label} chat chunk. The SELF user is: {self_names}.
Messages labeled SELF are from the user; ASSISTANT are from their coding assistant.

Return JSON with this shape:
{{
  "profiles": [{{"key": "snake_case", "value": "...", "confidence": 0.0-1.0, "evidence": ["quote snippet"]}}],
  "preferences": [{{"key": "snake_case", "value": "...", "strength": 0.0-1.0, "evidence": ["..."]}}],
  "episodes": [{{"summary": "...", "tags": ["work"], "date": "YYYY-MM-DD or null"}}]
}}

If nothing useful, return empty arrays.

Chat:
{chunk}
"""

ChunkTask = tuple[str, MemorySource, str, str | None]


class ShadowExtractor:
    def __init__(
        self,
        store: MemoryStore,
        persona: PersonaConfig,
        client: OllamaClient | None = None,
    ) -> None:
        self.store = store
        self.persona = persona
        self.client = client or OllamaClient(persona.llm)
        self.failed_chunks: int = 0
        self.last_errors: list[str] = []

    def extract_from_text_chunk(
        self,
        chunk_text: str,
        source: MemorySource,
        *,
        source_label: str = "chat",
    ) -> list[MemoryProposal]:
        user_prompt = EXTRACTION_USER_TEMPLATE.format(
            self_names=", ".join(self.persona.self_names),
            chunk=chunk_text,
            source_label=source_label,
        )
        raw = self.client.chat(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            model=self.persona.llm.extractor_model,
            temperature=0.2,
            json_mode=True,
        )
        data = self.client.parse_json_response(raw)
        return self._data_to_proposals(data, source=source)

    def _extract_task(self, task: ChunkTask) -> list[MemoryProposal]:
        chunk_text, source, source_label, raw_ref = task
        try:
            proposals = self.extract_from_text_chunk(
                chunk_text, source, source_label=source_label
            )
        except (OllamaError, httpx.HTTPError, json.JSONDecodeError) as exc:
            self.failed_chunks += 1
            if len(self.last_errors) < 5:
                self.last_errors.append(str(exc))
            return []
        for proposal in proposals:
            if raw_ref and proposal.episode:
                proposal.episode.raw_ref = raw_ref
        return proposals

    def _extract_tasks(
        self,
        tasks: list[ChunkTask],
        *,
        workers: int = 0,
        auto_propose: bool = True,
        on_progress: ProgressCallback | None = None,
        progress_label: str = "Extracting",
    ) -> list[MemoryProposal]:
        if not tasks:
            return []

        self.failed_chunks = 0
        self.last_errors = []

        report = on_progress or noop_progress
        total = len(tasks)
        report(0, total, f"{progress_label} (0/{total})")

        all_proposals: list[MemoryProposal] = []
        pool_size = min(default_workers(workers), self.client.parallel_requests(), len(tasks))
        completed = 0

        if pool_size <= 1:
            for task in tasks:
                all_proposals.extend(self._extract_task(task))
                completed += 1
                report(completed, total, f"{progress_label} ({completed}/{total})")
        else:
            with ThreadPoolExecutor(max_workers=pool_size) as pool:
                futures = [pool.submit(self._extract_task, task) for task in tasks]
                for future in as_completed(futures):
                    all_proposals.extend(future.result())
                    completed += 1
                    report(completed, total, f"{progress_label} ({completed}/{total})")

        if auto_propose:
            report(completed, total, f"{progress_label} — saving proposals…")
            for proposal in all_proposals:
                self.store.propose(proposal)
        return all_proposals

    def _data_to_proposals(self, data: dict, source: MemorySource) -> list[MemoryProposal]:
        proposals: list[MemoryProposal] = []

        for item in data.get("profiles", []):
            profile = ProfileEntry(
                key=item["key"],
                value=item["value"],
                confidence=float(item.get("confidence", 0.7)),
                source=source,
                evidence=item.get("evidence", []),
            )
            proposals.append(
                MemoryProposal(
                    category=MemoryCategory.PROFILE,
                    source=source,
                    reason="Extracted profile fact from chat",
                    profile=profile,
                )
            )

        for item in data.get("preferences", []):
            preference = PreferenceEntry(
                key=item["key"],
                value=item["value"],
                strength=float(item.get("strength", 0.7)),
                source=source,
                evidence=item.get("evidence", []),
            )
            proposals.append(
                MemoryProposal(
                    category=MemoryCategory.PREFERENCE,
                    source=source,
                    reason="Extracted preference from chat",
                    preference=preference,
                )
            )

        for item in data.get("episodes", []):
            date = None
            if item.get("date"):
                from datetime import datetime

                try:
                    date = datetime.fromisoformat(item["date"])
                except ValueError:
                    date = None
            episode = EpisodeEntry(
                summary=item["summary"],
                tags=item.get("tags", []),
                date=date,
                source=source,
            )
            proposals.append(
                MemoryProposal(
                    category=MemoryCategory.EPISODE,
                    source=source,
                    reason="Extracted episodic summary from chat",
                    episode=episode,
                )
            )

        return proposals

    def _select_parsed_files(
        self,
        parsed_dir: Path,
        source: str,
        manifest: ManifestStore | None,
        *,
        only_new: bool,
        force: bool,
        skip_meta: bool = False,
    ) -> tuple[list[Path], int]:
        selected: list[Path] = []
        skipped = 0
        for path in sorted(parsed_dir.glob("*.jsonl")):
            if skip_meta and ".meta." in path.name:
                continue
            raw_key = IngestManifest.logical_key(path)
            if manifest and only_new and not force:
                if not manifest.needs_extract(source, raw_key, path, force=False):
                    skipped += 1
                    continue
            selected.append(path)
        return selected, skipped

    def _finalize_extract(
        self,
        source: str,
        processed_paths: list[Path],
        manifest: ManifestStore | None,
        *,
        record: bool = True,
    ) -> None:
        if not manifest or not record:
            return
        for path in processed_paths:
            manifest.record_extract(source, IngestManifest.logical_key(path), path)

    def extract_whatsapp_parsed_dir(
        self,
        parsed_dir: Path,
        chunk_size: int = 40,
        self_only: bool = False,
        auto_propose: bool = True,
        workers: int = 0,
        on_progress: ProgressCallback | None = None,
        manifest: ManifestStore | None = None,
        only_new: bool = True,
        force: bool = False,
    ) -> ExtractStats:
        paths, skipped = self._select_parsed_files(
            parsed_dir, "whatsapp", manifest, only_new=only_new, force=force
        )
        tasks: list[ChunkTask] = []
        for path in paths:
            messages = load_parsed_messages(path)
            for chunk in chunk_messages(messages, chunk_size=chunk_size, self_only=self_only):
                tasks.append(
                    (
                        format_chunk_for_extraction(chunk),
                        MemorySource.WHATSAPP,
                        "WhatsApp",
                        path.name,
                    )
                )
        proposals = self._extract_tasks(
            tasks,
            workers=workers,
            auto_propose=auto_propose,
            on_progress=on_progress,
            progress_label="WhatsApp chunks",
        )
        self._finalize_extract("whatsapp", paths, manifest, record=auto_propose)
        return ExtractStats(
            processed_files=len(paths),
            skipped_files=skipped,
            proposals=len(proposals),
            failed_chunks=self.failed_chunks,
        )

    def extract_agent_parsed_dir(
        self,
        parsed_dir: Path,
        provider: str,
        chunk_size: int = 20,
        user_only: bool = False,
        auto_propose: bool = True,
        workers: int = 0,
        on_progress: ProgressCallback | None = None,
        manifest: ManifestStore | None = None,
        only_new: bool = True,
        force: bool = False,
    ) -> ExtractStats:
        paths, skipped = self._select_parsed_files(
            parsed_dir, provider, manifest, only_new=only_new, force=force, skip_meta=True
        )
        try:
            label = get_adapter(provider).label
        except ValueError:
            label = provider.title()
        mem_source = memory_source_for_agent(provider)
        tasks: list[ChunkTask] = []
        for path in paths:
            turns = load_parsed_turns(path)
            for chunk in chunk_turns(turns, chunk_size=chunk_size, user_only=user_only):
                tasks.append(
                    (
                        format_chunk_for_extraction(chunk),
                        mem_source,
                        label,
                        path.name,
                    )
                )
        proposals = self._extract_tasks(
            tasks,
            workers=workers,
            auto_propose=auto_propose,
            on_progress=on_progress,
            progress_label=f"{label} chunks",
        )
        self._finalize_extract(provider, paths, manifest, record=auto_propose)
        return ExtractStats(
            processed_files=len(paths),
            skipped_files=skipped,
            proposals=len(proposals),
            failed_chunks=self.failed_chunks,
        )

    def extract_cursor_parsed_dir(
        self,
        parsed_dir: Path,
        chunk_size: int = 20,
        user_only: bool = False,
        auto_propose: bool = True,
        workers: int = 0,
        on_progress: ProgressCallback | None = None,
        manifest: ManifestStore | None = None,
        only_new: bool = True,
        force: bool = False,
    ) -> ExtractStats:
        return self.extract_agent_parsed_dir(
            parsed_dir,
            "cursor",
            chunk_size=chunk_size,
            user_only=user_only,
            auto_propose=auto_propose,
            workers=workers,
            on_progress=on_progress,
            manifest=manifest,
            only_new=only_new,
            force=force,
        )

    def extract_server_parsed_dir(
        self,
        source_key: str,
        parsed_dir: Path,
        chunk_size: int = 10,
        auto_propose: bool = True,
        workers: int = 0,
        on_progress: ProgressCallback | None = None,
        manifest: ManifestStore | None = None,
        only_new: bool = True,
        force: bool = False,
    ) -> ExtractStats:
        mem_source, label = SERVER_SOURCE_LABELS[source_key]
        paths, skipped = self._select_parsed_files(
            parsed_dir, source_key, manifest, only_new=only_new, force=force
        )
        tasks: list[ChunkTask] = []
        for path in paths:
            records = load_parsed_records(path)
            for chunk in chunk_records(records, chunk_size=chunk_size):
                tasks.append(
                    (
                        format_records_for_extraction(chunk),
                        mem_source,
                        label,
                        path.name,
                    )
                )
        proposals = self._extract_tasks(
            tasks,
            workers=workers,
            auto_propose=auto_propose,
            on_progress=on_progress,
            progress_label=f"{label} chunks",
        )
        self._finalize_extract(source_key, paths, manifest, record=auto_propose)
        return ExtractStats(
            processed_files=len(paths),
            skipped_files=skipped,
            proposals=len(proposals),
            failed_chunks=self.failed_chunks,
        )

    def extract_email_parsed_dir(self, parsed_dir: Path, **kwargs) -> ExtractStats:
        return self.extract_server_parsed_dir("email", parsed_dir, **kwargs)

    def extract_calendar_parsed_dir(self, parsed_dir: Path, **kwargs) -> ExtractStats:
        return self.extract_server_parsed_dir("calendar", parsed_dir, **kwargs)

    def extract_search_parsed_dir(self, parsed_dir: Path, **kwargs) -> ExtractStats:
        return self.extract_server_parsed_dir("search", parsed_dir, **kwargs)

    def extract_from_chat_session(self, session_text: str) -> list[MemoryProposal]:
        proposals = self.extract_from_text_chunk(
            session_text, source=MemorySource.CHAT, source_label="chat"
        )
        for proposal in proposals:
            self.store.propose(proposal)
        return proposals
