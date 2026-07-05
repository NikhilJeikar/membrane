"""Ingest AI agent session transcripts from any supported provider."""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from membrane.config import Settings
from membrane.ingest.agents.io import save_parsed_session
from membrane.ingest.agents.registry import detect_provider, discover_transcripts, get_adapter
from membrane.tracking.stats import IngestStats


def ingest_agent_path(
    source: Path,
    *,
    provider: str = "auto",
    raw_dir: Path | None = None,
    parsed_dir: Path | None = None,
    settings: Settings | None = None,
    redact: bool = True,
    copy_raw: bool = True,
    workers: int = 0,
    manifest: object | None = None,
    force: bool = False,
) -> IngestStats:
    pairs = discover_transcripts(source, provider=provider)
    if not pairs:
        raise FileNotFoundError(f"No agent transcript JSONL found under {source}")

    if settings is not None and provider == "auto":
        combined = IngestStats()
        by_provider: dict[str, list[tuple[str, Path]]] = defaultdict(list)
        for prov, path in pairs:
            by_provider[prov].append((prov, path))
        for prov, items in sorted(by_provider.items()):
            stats = _ingest_agent_items(
                items,
                raw_dir=settings.agent_raw_dir(prov),
                parsed_dir=settings.agent_parsed_dir(prov),
                redact=redact,
                copy_raw=copy_raw,
                workers=workers,
                manifest=manifest,
                force=force,
                default_provider=prov,
            )
            combined.processed += stats.processed
            combined.skipped += stats.skipped
            combined.outputs.extend(stats.outputs)
        combined.outputs = sorted(combined.outputs, key=lambda p: p.name)
        return combined

    if raw_dir is None or parsed_dir is None:
        raise ValueError("raw_dir and parsed_dir are required when provider is not auto with settings")
    return _ingest_agent_items(
        pairs,
        raw_dir=raw_dir,
        parsed_dir=parsed_dir,
        redact=redact,
        copy_raw=copy_raw,
        workers=workers,
        manifest=manifest,
        force=force,
        default_provider=provider if provider != "auto" else "openai",
    )


def _ingest_agent_items(
    items: list[tuple[str, Path]],
    *,
    raw_dir: Path,
    parsed_dir: Path,
    redact: bool,
    copy_raw: bool,
    workers: int,
    manifest: object | None,
    force: bool,
    default_provider: str,
) -> IngestStats:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from membrane.tracking.manifest import ManifestStore
    from membrane.utils.parallel import default_workers

    stats = IngestStats()
    store: ManifestStore | None = manifest  # type: ignore[assignment]

    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    if store:
        for raw_file in raw_dir.glob("*.jsonl"):
            parsed_file = parsed_dir / raw_file.name
            manifest_provider = _manifest_provider_for_raw(raw_file, parsed_dir, default_provider)
            store.reconcile_existing(manifest_provider, raw_file, parsed_file)

    def ingest_one(item: tuple[str, Path]) -> tuple[Path | None, bool]:
        agent_provider, transcript = item
        adapter = get_adapter(agent_provider)
        dest_raw = raw_dir / transcript.name
        if copy_raw and transcript.resolve() != dest_raw.resolve():
            shutil.copy2(transcript, dest_raw)
        raw_for_hash = dest_raw if dest_raw.exists() else transcript
        parsed_out = parsed_dir / f"{transcript.stem}.jsonl"

        if store and not store.needs_ingest(agent_provider, raw_for_hash, parsed_out, force=force):
            return None, True

        session = adapter.parse(raw_for_hash, redact=redact)
        if not session.turns:
            return None, False
        out = save_parsed_session(session, parsed_dir)
        if store:
            store.record_ingest(agent_provider, raw_for_hash, out)
        return out, False

    pool_size = min(default_workers(workers), len(items))
    if pool_size <= 1:
        for item in items:
            out, skipped = ingest_one(item)
            if skipped:
                stats.skipped += 1
            elif out:
                stats.processed += 1
                stats.outputs.append(out)
    else:
        with ThreadPoolExecutor(max_workers=pool_size) as pool:
            futures = [pool.submit(ingest_one, item) for item in items]
            for future in as_completed(futures):
                out, skipped = future.result()
                if skipped:
                    stats.skipped += 1
                elif out:
                    stats.processed += 1
                    stats.outputs.append(out)

    stats.outputs = sorted(stats.outputs, key=lambda p: p.name)
    return stats


def _manifest_provider_for_raw(raw_file: Path, parsed_dir: Path, default_provider: str) -> str:
    from membrane.ingest.agents.io import read_session_meta

    parsed = parsed_dir / raw_file.name
    if parsed.exists():
        meta = read_session_meta(parsed)
        if meta.get("agent"):
            return str(meta["agent"])
    if default_provider != "auto":
        return default_provider
    try:
        return detect_provider(raw_file)
    except ValueError:
        return "openai"
