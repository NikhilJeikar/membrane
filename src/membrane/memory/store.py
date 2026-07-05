"""Memory store with propose / approve workflow."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from membrane.memory.models import (
    EpisodeEntry,
    MemoryCategory,
    MemoryProposal,
    PreferenceEntry,
    ProfileEntry,
    ProposalStatus,
)


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.profile_path = root / "profile.json"
        self.preferences_path = root / "preferences.json"
        self.episodes_path = root / "episodes.jsonl"
        self.proposed_dir = root / "proposed"
        self.approved_dir = root / "approved"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for path in (
            self.root,
            self.proposed_dir,
            self.approved_dir,
            self.root / "examples",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _read_json_list(self, path: Path, model: type) -> list:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [model.model_validate(item) for item in data]

    def _write_json_list(self, path: Path, items: list) -> None:
        path.write_text(
            json.dumps([item.model_dump(mode="json") for item in items], indent=2),
            encoding="utf-8",
        )

    def load_profile(self) -> list[ProfileEntry]:
        return self._read_json_list(self.profile_path, ProfileEntry)

    def load_preferences(self) -> list[PreferenceEntry]:
        return self._read_json_list(self.preferences_path, PreferenceEntry)

    def load_episodes(self) -> list[EpisodeEntry]:
        if not self.episodes_path.exists():
            return []
        episodes: list[EpisodeEntry] = []
        for line in self.episodes_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                episodes.append(EpisodeEntry.model_validate(json.loads(line)))
        return episodes

    def save_profile(self, entries: list[ProfileEntry]) -> None:
        self._write_json_list(self.profile_path, entries)

    def save_preferences(self, entries: list[PreferenceEntry]) -> None:
        self._write_json_list(self.preferences_path, entries)

    def save_episodes(self, entries: list[EpisodeEntry]) -> None:
        with self.episodes_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry.model_dump(mode="json")) + "\n")

    def upsert_profile(self, entry: ProfileEntry) -> None:
        entries = self.load_profile()
        entries = [e for e in entries if e.key != entry.key]
        entries.append(entry)
        self.save_profile(entries)

    def upsert_preference(self, entry: PreferenceEntry) -> None:
        entries = self.load_preferences()
        entries = [e for e in entries if e.key != entry.key]
        entries.append(entry)
        self.save_preferences(entries)

    def delete_profile(self, key: str) -> bool:
        entries = self.load_profile()
        kept = [e for e in entries if e.key != key]
        if len(kept) == len(entries):
            return False
        self.save_profile(kept)
        return True

    def delete_preference(self, key: str) -> bool:
        entries = self.load_preferences()
        kept = [e for e in entries if e.key != key]
        if len(kept) == len(entries):
            return False
        self.save_preferences(kept)
        return True

    def append_episode(self, entry: EpisodeEntry) -> None:
        episodes = self.load_episodes()
        episodes.append(entry)
        self.save_episodes(episodes)

    def propose(self, proposal: MemoryProposal) -> Path:
        proposal.status = ProposalStatus.PENDING
        path = self.proposed_dir / f"{proposal.id}.json"
        path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        return path

    def list_proposed(self, status: ProposalStatus = ProposalStatus.PENDING) -> list[MemoryProposal]:
        proposals: list[MemoryProposal] = []
        for path in sorted(self.proposed_dir.glob("*.json")):
            proposal = MemoryProposal.model_validate_json(path.read_text(encoding="utf-8"))
            if proposal.status == status:
                proposals.append(proposal)
        return proposals

    def approve(self, proposal_id: str) -> MemoryProposal:
        path = self.proposed_dir / f"{proposal_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Proposal not found: {proposal_id}")
        proposal = MemoryProposal.model_validate_json(path.read_text(encoding="utf-8"))
        proposal.status = ProposalStatus.APPROVED
        entry = proposal.to_entry()

        if proposal.category == MemoryCategory.PROFILE:
            self.upsert_profile(entry)  # type: ignore[arg-type]
        elif proposal.category == MemoryCategory.PREFERENCE:
            self.upsert_preference(entry)  # type: ignore[arg-type]
        elif proposal.category == MemoryCategory.EPISODE:
            self.append_episode(entry)  # type: ignore[arg-type]

        path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        archive = self.approved_dir / f"{proposal_id}.json"
        archive.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        return proposal

    def reject(self, proposal_id: str) -> MemoryProposal:
        path = self.proposed_dir / f"{proposal_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Proposal not found: {proposal_id}")
        proposal = MemoryProposal.model_validate_json(path.read_text(encoding="utf-8"))
        proposal.status = ProposalStatus.REJECTED
        path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
        return proposal

    def approve_all_pending(self) -> list[MemoryProposal]:
        approved: list[MemoryProposal] = []
        for proposal in self.list_proposed(ProposalStatus.PENDING):
            approved.append(self.approve(proposal.id))
        return approved

    def clear_source(self, source: str) -> dict[str, int]:
        """Remove proposals, archive copies, and live memory for one source."""
        from membrane.memory.models import MemorySource

        try:
            mem_source = MemorySource(source)
        except ValueError as exc:
            raise ValueError(f"Unknown source: {source}") from exc

        counts = {
            "proposals_removed": 0,
            "approved_removed": 0,
            "profile_removed": 0,
            "preferences_removed": 0,
            "episodes_removed": 0,
        }

        for path in list(self.proposed_dir.glob("*.json")):
            proposal = MemoryProposal.model_validate_json(path.read_text(encoding="utf-8"))
            if proposal.source == mem_source:
                path.unlink()
                counts["proposals_removed"] += 1

        for path in list(self.approved_dir.glob("*.json")):
            proposal = MemoryProposal.model_validate_json(path.read_text(encoding="utf-8"))
            if proposal.source == mem_source:
                path.unlink()
                counts["approved_removed"] += 1

        profile = self.load_profile()
        kept_profile = [e for e in profile if e.source != mem_source]
        counts["profile_removed"] = len(profile) - len(kept_profile)
        if counts["profile_removed"]:
            self.save_profile(kept_profile)

        prefs = self.load_preferences()
        kept_prefs = [e for e in prefs if e.source != mem_source]
        counts["preferences_removed"] = len(prefs) - len(kept_prefs)
        if counts["preferences_removed"]:
            self.save_preferences(kept_prefs)

        episodes = self.load_episodes()
        kept_episodes = [e for e in episodes if e.source != mem_source]
        counts["episodes_removed"] = len(episodes) - len(kept_episodes)
        if counts["episodes_removed"]:
            self.save_episodes(kept_episodes)

        return counts

    def snapshot(self) -> dict:
        return {
            "profile": [e.model_dump(mode="json") for e in self.load_profile()],
            "preferences": [e.model_dump(mode="json") for e in self.load_preferences()],
            "episodes": [e.model_dump(mode="json") for e in self.load_episodes()],
        }

    def search_episodes(self, query: str, limit: int = 5) -> list[EpisodeEntry]:
        """Simple keyword search over episode summaries."""
        query_lower = query.lower()
        scored: list[tuple[int, EpisodeEntry]] = []
        for episode in self.load_episodes():
            summary = episode.summary.lower()
            tags = " ".join(episode.tags).lower()
            score = sum(1 for word in query_lower.split() if word in summary or word in tags)
            if score > 0:
                scored.append((score, episode))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]

    def init_from_examples(self) -> None:
        examples = self.root / "examples"
        for name, dest in (
            ("profile.json", self.profile_path),
            ("preferences.json", self.preferences_path),
        ):
            src = examples / name
            if src.exists() and not dest.exists():
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
