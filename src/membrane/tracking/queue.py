"""Pending parse / extract / train counts from the ingest manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from membrane.config import Settings
from membrane.config_policy import SourcePolicy, TrainingPolicy
from membrane.ingest.agents import list_providers
from membrane.ingest.server_models import SERVER_SOURCES
from membrane.tracking.manifest import IngestManifest, ManifestStore


@dataclass
class SourceQueueStats:
    raw: int
    parsed: int
    needs_parse: int
    needs_extract: int
    needs_train: int
    train_enabled: bool

    def as_dict(self) -> dict:
        return {
            "raw": self.raw,
            "parsed": self.parsed,
            "needs_parse": self.needs_parse,
            "needs_extract": self.needs_extract,
            "needs_train": self.needs_train,
            "train_enabled": self.train_enabled,
        }


def _is_ingest_file(path: Path) -> bool:
    """Ignore placeholder files like .gitkeep that keep empty dirs in git."""
    return path.is_file() and not path.name.startswith(".")


def _count_parsed(parsed_dir: Path) -> int:
    if not parsed_dir.exists():
        return 0
    return len([p for p in parsed_dir.glob("*.jsonl") if ".meta." not in p.name])


def _count_raw(raw_dir: Path, pattern: str = "*") -> int:
    if not raw_dir.exists():
        return 0
    return len([p for p in raw_dir.glob(pattern) if _is_ingest_file(p)])


def _reconcile_server(manifest: ManifestStore, source: str, raw_dir: Path, parsed_dir: Path) -> None:
    if not raw_dir.exists():
        return
    for raw_file in raw_dir.glob("*.json"):
        parsed_file = parsed_dir / f"{raw_file.stem}.jsonl"
        manifest.reconcile_existing(source, raw_file, parsed_file)


def _reconcile_agents(manifest: ManifestStore, source: str, raw_dir: Path, parsed_dir: Path) -> None:
    if not raw_dir.exists():
        return
    for raw_file in raw_dir.glob("*.jsonl"):
        parsed_file = parsed_dir / raw_file.name
        if parsed_file.exists():
            manifest.reconcile_existing(source, raw_file, parsed_file)


def _reconcile_whatsapp(manifest: ManifestStore, raw_dir: Path, parsed_dir: Path) -> None:
    if not raw_dir.exists():
        return
    for raw_file in raw_dir.glob("*"):
        if not _is_ingest_file(raw_file):
            continue
        parsed_file = parsed_dir / f"{raw_file.stem}.jsonl"
        if parsed_file.exists():
            manifest.reconcile_existing("whatsapp", raw_file, parsed_file)


def _count_needs_parse(
    manifest: ManifestStore,
    source: str,
    raw_dir: Path,
    parsed_dir: Path,
    *,
    raw_pattern: str = "*",
    parsed_name: str | None = None,
) -> int:
    if not raw_dir.exists():
        return 0
    count = 0
    for raw_path in raw_dir.glob(raw_pattern):
        if not _is_ingest_file(raw_path):
            continue
        if parsed_name:
            parsed_out = parsed_dir / parsed_name.format(stem=raw_path.stem, name=raw_path.name)
        else:
            parsed_out = parsed_dir / f"{raw_path.stem}.jsonl"
        if manifest.needs_ingest(source, raw_path, parsed_out):
            count += 1
    return count


def _count_needs_extract(manifest: ManifestStore, source: str, parsed_dir: Path) -> int:
    if not parsed_dir.exists():
        return 0
    count = 0
    for parsed_path in parsed_dir.glob("*.jsonl"):
        if ".meta." in parsed_path.name:
            continue
        raw_key = IngestManifest.logical_key(parsed_path)
        if manifest.needs_extract(source, raw_key, parsed_path):
            count += 1
    return count


def _source_policy(policy: TrainingPolicy, source: str) -> SourcePolicy:
    return policy.sources.get(source, SourcePolicy())


def build_source_queue_stats(
    manifest: ManifestStore,
    policy: TrainingPolicy,
    source: str,
    raw_dir: Path,
    parsed_dir: Path,
    *,
    raw_pattern: str = "*",
    parsed_name: str | None = None,
    reconcile: str = "server",
) -> SourceQueueStats:
    if reconcile == "server":
        _reconcile_server(manifest, source, raw_dir, parsed_dir)
    elif reconcile == "agents":
        _reconcile_agents(manifest, source, raw_dir, parsed_dir)
    elif reconcile == "whatsapp":
        _reconcile_whatsapp(manifest, raw_dir, parsed_dir)

    src_policy = _source_policy(policy, source)
    needs_parse = _count_needs_parse(
        manifest,
        source,
        raw_dir,
        parsed_dir,
        raw_pattern=raw_pattern,
        parsed_name=parsed_name,
    )
    needs_extract = _count_needs_extract(manifest, source, parsed_dir)
    needs_train = needs_extract if src_policy.train else 0

    return SourceQueueStats(
        raw=_count_raw(raw_dir, raw_pattern),
        parsed=_count_parsed(parsed_dir),
        needs_parse=needs_parse,
        needs_extract=needs_extract,
        needs_train=needs_train,
        train_enabled=src_policy.train,
    )


def build_ingest_queue_stats(
    settings: Settings,
    manifest: ManifestStore,
    policy: TrainingPolicy,
) -> dict:
    sources: dict[str, SourceQueueStats] = {}

    sources["whatsapp"] = build_source_queue_stats(
        manifest,
        policy,
        "whatsapp",
        settings.whatsapp_raw_dir,
        settings.whatsapp_parsed_dir,
        reconcile="whatsapp",
    )

    for provider in settings.list_agent_providers() or list_providers():
        sources[provider] = build_source_queue_stats(
            manifest,
            policy,
            provider,
            settings.resolved_agent_raw_dir(provider),
            settings.resolved_agent_parsed_dir(provider),
            raw_pattern="*.jsonl",
            parsed_name="{name}",
            reconcile="agents",
        )

    for src in SERVER_SOURCES:
        sources[src] = build_source_queue_stats(
            manifest,
            policy,
            src,
            settings.server_raw_dir(src),
            settings.server_parsed_dir(src),
            raw_pattern="*.json",
            reconcile="server",
        )

    totals = {
        "needs_parse": sum(s.needs_parse for s in sources.values()),
        "needs_extract": sum(s.needs_extract for s in sources.values()),
        "needs_train": sum(s.needs_train for s in sources.values()),
    }

    return {
        "sources": {name: stats.as_dict() for name, stats in sources.items()},
        "totals": totals,
    }
