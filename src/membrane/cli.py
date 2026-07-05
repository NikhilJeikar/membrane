"""Command-line interface for membrane."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from membrane.config import ensure_data_layout, get_settings, load_persona
from membrane.inference.context import ContextBuilder
from membrane.ingest.agents import (
    agent_sessions_to_chat_sessions,
    ingest_agent_path,
    list_providers,
)
from membrane.ingest.lifecycle import parse_all_server_sources
from membrane.ingest.server_models import SERVER_SOURCES
from membrane.ingest.whatsapp import ingest_whatsapp_file
from membrane.ingest.wikipedia import (
    build_summarization_corpus,
    download_hf_wikipedia,
    fetch_random_articles,
    label_summaries_with_ollama,
    load_articles,
    save_articles,
    save_summarization_jsonl,
)
from membrane.learning.chat_log import ChatLogger
from membrane.learning.export import TrainingExporter
from membrane.llm.ollama import OllamaClient
from membrane.memory.models import MemoryCategory, ProposalStatus
from membrane.memory.review import run_interactive_review
from membrane.memory.store import MemoryStore
from membrane.shadow.extractor import ShadowExtractor
from membrane.shadow.offline import OfflineExtractor
from membrane.server.app import run_server
from membrane.server.auth import resolve_server_token
from membrane.tracking.manifest import ManifestStore
from membrane.utils.parallel import cpu_count, default_workers
from membrane.utils.progress import make_rich_progress, noop_progress

app = typer.Typer(no_args_is_help=True, help="Local personal assistant with memory and learning.")
console = Console()

ingest_app = typer.Typer(help="Ingest external data sources.")
extract_app = typer.Typer(help="Extract memory proposals locally.")
memory_app = typer.Typer(help="Manage memory store and proposals.")
context_app = typer.Typer(help="Build inference context.")
chat_app = typer.Typer(help="Log PA conversations for learning.")
export_app = typer.Typer(help="Export training datasets.")
dataset_app = typer.Typer(help="Prepare task-specific training datasets.")
init_app = typer.Typer(help="Initialize project layout and memory.")
status_app = typer.Typer(help="Check environment and data status.")
tracking_app = typer.Typer(help="Manage ingest/extract hash tracking.")
server_app = typer.Typer(help="Local ingest server (email, calendar, search).")
ui_app = typer.Typer(help="Web control UI (IBM Carbon).")

app.add_typer(ingest_app, name="ingest")
app.add_typer(extract_app, name="extract")
app.add_typer(memory_app, name="memory")
app.add_typer(context_app, name="context")
app.add_typer(chat_app, name="chat")
app.add_typer(export_app, name="export")
app.add_typer(dataset_app, name="dataset")
app.add_typer(init_app, name="init")
app.add_typer(status_app, name="status")
app.add_typer(tracking_app, name="tracking")
app.add_typer(server_app, name="server")
app.add_typer(ui_app, name="ui")


def _settings():
    return get_settings()


def _persona():
    return load_persona()


def _store() -> MemoryStore:
    settings = _settings()
    return MemoryStore(settings.memory_dir)


def _resolve_workers(workers: int) -> int:
    if workers > 0:
        return workers
    return default_workers(_persona().performance.workers)


def _manifest() -> ManifestStore:
    return ManifestStore(_settings().manifest_path)


def _server_sources_for(source: str) -> tuple[str, ...]:
    if source == "server":
        return SERVER_SOURCES
    if source in SERVER_SOURCES:
        return (source,)  # type: ignore[return-value]
    if source == "all":
        return SERVER_SOURCES
    return ()


def _agent_sources_for(source: str) -> list[str]:
    settings = _settings()
    installed = settings.list_agent_providers()
    known = list_providers()
    if source == "all":
        merged: list[str] = []
        for name in installed + known:
            if name not in merged:
                merged.append(name)
        return merged
    if source == "agents":
        return installed or ["cursor"]
    if source in known:
        return [source]
    return []


def _count_agent_sessions() -> int:
    settings = _settings()
    total = 0
    for provider in _agent_sources_for("agents"):
        parsed = settings.resolved_agent_parsed_dir(provider)
        if parsed.exists():
            total += len(list(parsed.glob("*.jsonl")))
    return total


def _add_extract_stats(
    total: tuple[int, int, int],
    stats,
) -> tuple[int, int, int]:
    proposals, processed, skipped = total
    return (
        proposals + stats.proposals,
        processed + stats.processed_files,
        skipped + stats.skipped_files,
    )


@init_app.callback(invoke_without_command=True)
def init_project(
    copy_persona: Annotated[bool, typer.Option(help="Copy persona.example.yaml to persona.yaml")] = True,
) -> None:
    """Create directories and seed example memory files."""
    settings = _settings()
    ensure_data_layout(settings.root)
    store = _store()
    store.init_from_examples()

    example_persona = settings.config_dir / "persona.example.yaml"
    target_persona = settings.persona_path
    if copy_persona and example_persona.exists() and not target_persona.exists():
        target_persona.write_text(example_persona.read_text(encoding="utf-8"), encoding="utf-8")
        console.print(f"[green]Created[/green] {target_persona}")
    console.print("[green]Project initialized.[/green]")


@status_app.callback(invoke_without_command=True)
def status_check() -> None:
    """Show Ollama connectivity and ingested data counts."""
    settings = _settings()
    persona = _persona()
    client = OllamaClient(persona.llm)
    ollama_ok = client.health_check()
    workers = _resolve_workers(0)
    threads = persona.llm.num_threads if persona.llm.num_threads > 0 else cpu_count()
    parallel = client.parallel_requests()

    table = Table(title="membrane status")
    table.add_column("Check")
    table.add_column("Status")
    table.add_row("CPU cores", str(cpu_count()))
    table.add_row("Parallel workers (default)", str(workers))
    table.add_row("Ollama", "[green]reachable[/green]" if ollama_ok else "[red]not running[/red]")
    table.add_row("Ollama model", persona.llm.model)
    table.add_row("Ollama threads / request", str(threads))
    table.add_row("Ollama parallel requests", str(parallel))
    table.add_row(
        "Agent sessions parsed",
        str(_count_agent_sessions()),
    )
    table.add_row(
        "WhatsApp files parsed",
        str(len(list(settings.whatsapp_parsed_dir.glob("*.jsonl")))),
    )
    table.add_row(
        "Pending memory proposals",
        str(len(_store().list_proposed())),
    )
    manifest = _manifest()
    table.add_row("Tracked entries", str(len(manifest.manifest.entries)))
    stale_cursor = len(manifest.list_stale_extracted("cursor"))
    stale_wa = len(manifest.list_stale_extracted("whatsapp"))
    table.add_row("Needs re-extract (cursor)", str(stale_cursor))
    table.add_row("Needs re-extract (whatsapp)", str(stale_wa))
    console.print(table)
    if not ollama_ok:
        console.print(
            "\n[yellow]Tip:[/yellow] Use `membrane extract run --offline` or install Ollama:\n"
            "  curl -fsSL https://ollama.com/install.sh | sh\n"
            "  ollama pull qwen2.5:3b\n"
            "  export OLLAMA_NUM_THREADS=$(nproc)   # use all CPU cores per inference"
        )
    else:
        console.print(
            "\n[cyan]CPU tuning:[/cyan] set in config/persona.yaml → "
            "performance.workers, llm.num_threads, llm.parallel_requests"
        )


@tracking_app.command("reconcile")
def tracking_reconcile(
    source: Annotated[
        str,
        typer.Option(help="Source to reconcile: cursor, whatsapp, or all"),
    ] = "all",
) -> None:
    """Backfill ingest manifest from existing raw+parsed files."""
    settings = _settings()
    manifest = _manifest()
    total = 0
    for provider in list_providers():
        if source in (provider, "agents", "all"):
            parsed = settings.resolved_agent_parsed_dir(provider)
            raw = settings.resolved_agent_raw_dir(provider)
            if parsed.exists() or raw.exists():
                total += manifest.reconcile_parsed_dir(provider, raw, parsed)
    if source in ("whatsapp", "all"):
        total += manifest.reconcile_parsed_dir(
            "whatsapp", settings.whatsapp_raw_dir, settings.whatsapp_parsed_dir
        )
    for src in SERVER_SOURCES:
        if source in (src, "server", "all"):
            total += manifest.reconcile_parsed_dir(
                src, settings.server_raw_dir(src), settings.server_parsed_dir(src)
            )
    allowed = {"whatsapp", "email", "calendar", "search", "server", "all", "agents", *list_providers()}
    if source not in allowed:
        raise typer.BadParameter(
            f"source must be one of: {', '.join(sorted(allowed))}"
        )
    console.print(f"[green]Reconciled[/green] {total} new manifest entry(ies)")


@tracking_app.command("mark-extracted")
def tracking_mark_extracted(
    source: Annotated[
        str,
        typer.Option(help="Source: cursor, whatsapp, or all"),
    ] = "cursor",
    dry_run: Annotated[bool, typer.Option(help="Show count without updating manifest")] = False,
) -> None:
    """Mark parsed files as already extracted (skip on next extract run)."""
    settings = _settings()
    manifest = _manifest()
    if source not in ("whatsapp", "all", "agents", *list_providers()):
        raise typer.BadParameter(f"source must be whatsapp, agents, {', '.join(list_providers())}, or all")

    count = 0
    for provider in _agent_sources_for(source):
        parsed = settings.resolved_agent_parsed_dir(provider)
        if parsed.exists():
            count += len([p for p in parsed.glob("*.jsonl") if ".meta." not in p.name])
    if source in ("whatsapp", "all"):
        count += len(list(settings.whatsapp_parsed_dir.glob("*.jsonl")))

    if dry_run:
        console.print(f"[cyan]Would mark[/cyan] {count} parsed file(s) as extracted")
        return

    marked = 0
    for provider in _agent_sources_for(source):
        marked += manifest.mark_parsed_extracted(provider, settings.resolved_agent_parsed_dir(provider))
    if source in ("whatsapp", "all"):
        marked += manifest.mark_parsed_extracted("whatsapp", settings.whatsapp_parsed_dir)
    console.print(
        f"[green]Marked[/green] {marked} file(s) as extracted "
        f"({count} parsed total; unchanged entries skipped)"
    )


@server_app.command("run")
def server_run(
    host: Annotated[str | None, typer.Option(help="Bind host (default from persona.yaml)")] = None,
    port: Annotated[int, typer.Option(help="Bind port (0 = persona default)")] = 0,
    parse_interval: Annotated[
        int,
        typer.Option(help="Parse interval seconds (0 = persona default)"),
    ] = 0,
) -> None:
    """Run local ingest server; parses raw → parsed on a schedule."""
    settings = _settings()
    persona = _persona()
    ensure_data_layout(settings.root)
    run_server(
        settings,
        persona,
        _manifest(),
        _store(),
        host=host,
        port=port if port > 0 else None,
        parse_interval=parse_interval if parse_interval > 0 else None,
    )


@server_app.command("parse")
def server_parse(
    source: Annotated[
        str,
        typer.Option(help="email, calendar, search, server, or all"),
    ] = "all",
    force: Annotated[bool, typer.Option(help="Re-parse even if raw hash unchanged")] = False,
) -> None:
    """Parse server raw files → JSONL (one-shot, no HTTP server)."""
    settings = _settings()
    manifest = _manifest()
    if source == "all" or source == "server":
        results = parse_all_server_sources(settings, manifest, force=force)
        for src, stats in results.items():
            console.print(
                f"[green]{src}[/green]: parsed {stats.processed}, skipped {stats.skipped}"
            )
        return
    if source not in SERVER_SOURCES:
        raise typer.BadParameter("source must be email, calendar, search, server, or all")
    from membrane.ingest.lifecycle import parse_server_source

    stats = parse_server_source(
        source,  # type: ignore[arg-type]
        settings.server_raw_dir(source),
        settings.server_parsed_dir(source),
        manifest,
        force=force,
    )
    console.print(f"[green]Parsed[/green] {stats.processed}, skipped {stats.skipped}")


@server_app.command("status")
def server_status() -> None:
    """Show server ingest file counts and auth token path."""
    settings = _settings()
    persona = _persona()
    token = resolve_server_token(settings, persona)

    table = Table(title="membrane server ingest")
    table.add_column("Source")
    table.add_column("Raw")
    table.add_column("Parsed")
    for src in SERVER_SOURCES:
        raw_n = len(list(settings.server_raw_dir(src).glob("*.json")))
        parsed_n = len(list(settings.server_parsed_dir(src).glob("*.jsonl")))
        table.add_row(src, str(raw_n), str(parsed_n))
    console.print(table)
    console.print(
        f"\n[cyan]Token:[/cyan] {token}\n"
        f"[dim]Saved at[/dim] {settings.server_token_path}\n"
        f"[dim]Default URL[/dim] http://{persona.server.host}:{persona.server.port}"
    )


@ui_app.command("run")
def ui_run(
    host: Annotated[str, typer.Option(help="Bind host")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="UI + API port")] = 8787,
    dev: Annotated[bool, typer.Option(help="Allow CORS for Vite dev server on :5173")] = False,
) -> None:
    """Start Carbon web UI and control API."""
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.Exit("Install UI deps: pip install 'membrane[ui]'") from exc

    settings = _settings()
    ensure_data_layout(settings.root)
    ui_dist = settings.root / "ui" / "dist"
    if not dev and not ui_dist.is_dir():
        console.print(
            "[yellow]UI not built.[/yellow] Run:\n"
            "  cd ui && npm install && npm run build\n"
            "Or use --dev with `npm run dev` in ui/ (port 5173)"
        )
    from membrane.api.app import create_app

    app = create_app(ui_dist if ui_dist.is_dir() else None)
    console.print(f"[green]membrane UI[/green] → http://{host}:{port}")
    console.print("[dim]API docs[/dim] → http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")


@ingest_app.command("whatsapp")
def ingest_whatsapp(
    file: Annotated[Path, typer.Argument(help="Path to WhatsApp .txt export")],
    self_name: Annotated[
        list[str] | None,
        typer.Option("--self-name", help="Your name as shown in WhatsApp (repeatable)"),
    ] = None,
    no_redact: Annotated[bool, typer.Option(help="Disable PII redaction")] = False,
    force: Annotated[bool, typer.Option(help="Re-parse even if raw file hash unchanged")] = False,
) -> None:
    """Parse a WhatsApp export into JSONL."""
    settings = _settings()
    persona = _persona()
    names = self_name or persona.self_names
    if not file.exists():
        raise typer.BadParameter(f"File not found: {file}")

    out, skipped = ingest_whatsapp_file(
        source=file,
        output_dir=settings.whatsapp_parsed_dir,
        self_names=names,
        redact=not no_redact,
        manifest=_manifest(),
        force=force,
    )
    if skipped:
        console.print(f"[yellow]Skipped[/yellow] {file.name} (unchanged raw hash)")
    elif out:
        console.print(f"[green]Parsed[/green] {file.name} → {out}")


@ingest_app.command("agent")
def ingest_agent(
    path: Annotated[
        Path,
        typer.Argument(
            help="Agent transcript .jsonl file or directory (Cursor, Claude Code, OpenAI-style, etc.)"
        ),
    ],
    provider: Annotated[
        str,
        typer.Option(
            help=f"Agent provider ({', '.join(list_providers())}) or auto to detect from file format"
        ),
    ] = "auto",
    no_redact: Annotated[bool, typer.Option(help="Disable PII/path redaction")] = False,
    to_chats: Annotated[
        bool,
        typer.Option(help="Also copy parsed sessions into data/chats/ for SFT export"),
    ] = True,
    workers: Annotated[
        int,
        typer.Option(help="Parallel workers (0 = all CPU cores - 1)"),
    ] = 0,
    force: Annotated[bool, typer.Option(help="Re-parse all sessions even if raw hash unchanged")] = False,
) -> None:
    """Parse AI agent session transcripts into normalized JSONL."""
    settings = _settings()
    if not path.exists():
        raise typer.BadParameter(f"Path not found: {path}")
    if provider != "auto" and provider not in list_providers():
        raise typer.BadParameter(f"Unknown provider: {provider}. Use auto or one of: {', '.join(list_providers())}")

    n = _resolve_workers(workers)
    stats = ingest_agent_path(
        path,
        provider=provider,
        settings=settings,
        raw_dir=settings.agent_raw_dir(provider) if provider != "auto" else None,
        parsed_dir=settings.agent_parsed_dir(provider) if provider != "auto" else None,
        redact=not no_redact,
        workers=n,
        manifest=_manifest(),
        force=force,
    )
    console.print(
        f"[green]Parsed[/green] {stats.processed} new, "
        f"[yellow]skipped[/yellow] {stats.skipped} unchanged"
    )
    if to_chats:
        saved_total = 0
        for prov in _agent_sources_for("agents" if provider == "auto" else provider):
            saved = agent_sessions_to_chat_sessions(
                settings.resolved_agent_parsed_dir(prov),
                settings.chats_dir,
                provider=prov,
            )
            saved_total += len(saved)
        if saved_total:
            console.print(f"[green]Synced[/green] {saved_total} chat export(s) → data/chats/")
        elif stats.processed == 0:
            console.print("[dim]No new sessions — chats/ unchanged[/dim]")


@ingest_app.command("cursor")
def ingest_cursor(
    path: Annotated[
        Path,
        typer.Argument(
            help="Cursor transcript .jsonl file or directory (e.g. ~/.cursor/projects/.../agent-transcripts/)"
        ),
    ],
    no_redact: Annotated[bool, typer.Option(help="Disable PII/path redaction")] = False,
    to_chats: Annotated[
        bool,
        typer.Option(help="Also copy parsed sessions into data/chats/ for SFT export"),
    ] = True,
    workers: Annotated[
        int,
        typer.Option(help="Parallel workers (0 = all CPU cores - 1)"),
    ] = 0,
    force: Annotated[bool, typer.Option(help="Re-parse all sessions even if raw hash unchanged")] = False,
) -> None:
    """Parse Cursor agent transcripts into normalized JSONL."""
    settings = _settings()
    if not path.exists():
        raise typer.BadParameter(f"Path not found: {path}")

    n = _resolve_workers(workers)
    stats = ingest_agent_path(
        path,
        provider="cursor",
        raw_dir=settings.agent_raw_dir("cursor"),
        parsed_dir=settings.agent_parsed_dir("cursor"),
        redact=not no_redact,
        workers=n,
        manifest=_manifest(),
        force=force,
    )
    console.print(
        f"[green]Parsed[/green] {stats.processed} new, "
        f"[yellow]skipped[/yellow] {stats.skipped} unchanged"
    )
    if to_chats and stats.outputs:
        saved = agent_sessions_to_chat_sessions(
            settings.agent_parsed_dir("cursor"),
            settings.chats_dir,
            provider="cursor",
        )
        console.print(f"[green]Copied[/green] {len(saved)} session(s) → data/chats/ for SFT export")
    elif to_chats and stats.processed == 0:
        console.print("[dim]No new sessions — chats/ unchanged[/dim]")


@ingest_app.command("wiki")
def ingest_wiki(
    limit: Annotated[int, typer.Option(help="Number of articles to download")] = 500,
    lang: Annotated[str, typer.Option(help="Wikipedia language code")] = "en",
    hf: Annotated[
        bool,
        typer.Option(help="Use Hugging Face wikimedia/wikipedia (full corpus stream; needs corpus extra)"),
    ] = False,
    min_chars: Annotated[int, typer.Option(help="Minimum article length")] = 500,
    max_chars: Annotated[int, typer.Option(help="Maximum article length")] = 12000,
) -> None:
    """Download Wikipedia articles for summarization training."""
    settings = _settings()
    raw_path = settings.wiki_corpus_dir / "raw" / f"{lang}_articles.jsonl"

    if hf:
        console.print(f"[cyan]Streaming[/cyan] up to {limit} articles from Hugging Face ({lang})...")
        articles = download_hf_wikipedia(
            lang=lang, limit=limit, min_chars=min_chars, max_chars=max_chars
        )
    else:
        console.print(f"[cyan]Fetching[/cyan] {limit} random articles from Wikipedia API ({lang})...")
        articles = fetch_random_articles(
            lang=lang, limit=limit, min_chars=min_chars, max_chars=max_chars
        )

    save_articles(articles, raw_path)
    console.print(f"[green]Saved[/green] {len(articles)} articles → {raw_path}")


@extract_app.command("run")
def extract_run(
    source: Annotated[str, typer.Option(help="Source: whatsapp, cursor, or all")] = "whatsapp",
    chunk_size: Annotated[int, typer.Option(help="Messages per extraction chunk")] = 40,
    self_only: Annotated[
        bool,
        typer.Option(help="WhatsApp: only your messages; Cursor: only user turns"),
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Extract but do not save proposals")] = False,
    offline: Annotated[
        bool,
        typer.Option(help="Use heuristic extraction without Ollama (CPU-only)"),
    ] = False,
    workers: Annotated[
        int,
        typer.Option(help="Parallel workers for file/chunk processing (0 = all CPU cores - 1)"),
    ] = 0,
    no_progress: Annotated[bool, typer.Option("--no-progress", help="Disable progress bar")] = False,
    timeout: Annotated[
        float,
        typer.Option(help="Ollama read timeout in seconds (overrides persona.yaml)"),
    ] = 0,
    force: Annotated[
        bool,
        typer.Option(help="Re-extract all parsed files even if already extracted"),
    ] = False,
    all_files: Annotated[
        bool,
        typer.Option("--all", help="Extract all parsed files (same as --force)"),
    ] = False,
) -> None:
    """Run shadow extractor and create memory proposals."""
    settings = _settings()
    persona = _persona()
    if timeout > 0:
        persona.llm.timeout_seconds = timeout
    store = _store()
    n_workers = _resolve_workers(workers)
    manifest = _manifest()
    reprocess = force or all_files
    only_new = not reprocess

    if source not in ("whatsapp", "cursor", "agents", "email", "calendar", "search", "server", "all") and source not in list_providers():
        raise typer.BadParameter(
            "source must be whatsapp, cursor, agents, claude, openai, email, calendar, search, server, or all"
        )

    use_offline = offline
    if not use_offline:
        client = OllamaClient(persona.llm)
        if not client.health_check():
            console.print(
                "[yellow]Ollama is not running.[/yellow] "
                "Falling back to [bold]offline[/bold] extraction (heuristic, no LLM).\n"
                "For better results: install Ollama → `ollama pull qwen2.5:3b` → re-run without --offline"
            )
            use_offline = True

    if no_progress:
        on_progress = noop_progress
        stop_progress = lambda: None
    else:
        on_progress, stop_progress = make_rich_progress(console)

    mode_label = "offline" if use_offline else "ollama"
    if use_offline:
        console.print(f"[cyan]Starting[/cyan] {mode_label} extraction ({n_workers} workers)...")
    else:
        client = OllamaClient(persona.llm)
        console.print(
            f"[cyan]Starting[/cyan] {mode_label} extraction — "
            f"{client.parallel_requests()} concurrent LLM call(s), "
            f"{int(persona.llm.timeout_seconds)}s timeout, "
            f"{persona.llm.max_retries + 1} attempt(s) per chunk"
        )
        if client.parallel_requests() > 1:
            console.print(
                "[yellow]Tip:[/yellow] On CPU-only, set llm.parallel_requests: 1 in persona.yaml "
                "to avoid timeouts."
            )

    total_proposals = 0
    total_processed = 0
    total_skipped = 0
    extractor: ShadowExtractor | None = None
    try:
        if use_offline:
            offline_extractor = OfflineExtractor(store=store)
            if source in ("whatsapp", "all"):
                stats = offline_extractor.extract_whatsapp_parsed_dir(
                    settings.whatsapp_parsed_dir,
                    auto_propose=not dry_run,
                    workers=n_workers,
                    on_progress=on_progress,
                    manifest=manifest,
                    only_new=only_new,
                    force=reprocess,
                )
                total_proposals, total_processed, total_skipped = _add_extract_stats(
                    (total_proposals, total_processed, total_skipped), stats
                )
            for agent_source in _agent_sources_for(source):
                stats = offline_extractor.extract_agent_parsed_dir(
                    settings.resolved_agent_parsed_dir(agent_source),
                    agent_source,
                    auto_propose=not dry_run,
                    workers=n_workers,
                    on_progress=on_progress,
                    manifest=manifest,
                    only_new=only_new,
                    force=reprocess,
                )
                total_proposals, total_processed, total_skipped = _add_extract_stats(
                    (total_proposals, total_processed, total_skipped), stats
                )
            for src in _server_sources_for(source):
                stats = offline_extractor.extract_server_parsed_dir(
                    src,
                    settings.server_parsed_dir(src),
                    auto_propose=not dry_run,
                    workers=n_workers,
                    on_progress=on_progress,
                    manifest=manifest,
                    only_new=only_new,
                    force=reprocess,
                )
                total_proposals, total_processed, total_skipped = _add_extract_stats(
                    (total_proposals, total_processed, total_skipped), stats
                )
        else:
            extractor = ShadowExtractor(store=store, persona=persona)
            if source in ("whatsapp", "all"):
                stats = extractor.extract_whatsapp_parsed_dir(
                    settings.whatsapp_parsed_dir,
                    chunk_size=chunk_size,
                    self_only=self_only,
                    auto_propose=not dry_run,
                    workers=n_workers,
                    on_progress=on_progress,
                    manifest=manifest,
                    only_new=only_new,
                    force=reprocess,
                )
                total_proposals, total_processed, total_skipped = _add_extract_stats(
                    (total_proposals, total_processed, total_skipped), stats
                )
            for agent_source in _agent_sources_for(source):
                agent_chunk = 20 if chunk_size == 40 else chunk_size
                stats = extractor.extract_agent_parsed_dir(
                    settings.resolved_agent_parsed_dir(agent_source),
                    agent_source,
                    chunk_size=agent_chunk,
                    user_only=self_only,
                    auto_propose=not dry_run,
                    workers=n_workers,
                    on_progress=on_progress,
                    manifest=manifest,
                    only_new=only_new,
                    force=reprocess,
                )
                total_proposals, total_processed, total_skipped = _add_extract_stats(
                    (total_proposals, total_processed, total_skipped), stats
                )
            for src in _server_sources_for(source):
                stats = extractor.extract_server_parsed_dir(
                    src,
                    settings.server_parsed_dir(src),
                    chunk_size=max(5, chunk_size // 4),
                    auto_propose=not dry_run,
                    workers=n_workers,
                    on_progress=on_progress,
                    manifest=manifest,
                    only_new=only_new,
                    force=reprocess,
                )
                total_proposals, total_processed, total_skipped = _add_extract_stats(
                    (total_proposals, total_processed, total_skipped), stats
                )
    finally:
        stop_progress()

    if total_processed == 0 and total_skipped > 0:
        console.print(
            f"[green]Up to date[/green] — skipped {total_skipped} already-extracted file(s). "
            "Use --force to re-extract."
        )
        return

    if total_proposals == 0 and extractor and extractor.failed_chunks:
        console.print(
            f"[red]All {extractor.failed_chunks} chunk(s) failed.[/red] "
            "Try: `--timeout 900` or `llm.parallel_requests: 1` in persona.yaml"
        )
        for err in extractor.last_errors[:3]:
            console.print(f"  [dim]{err}[/dim]")
        raise typer.Exit(code=1)

    if total_proposals == 0:
        console.print(
            "[yellow]No proposals generated.[/yellow] "
            "Ingest data first: `membrane ingest cursor ...` or `membrane ingest whatsapp ...`"
        )
        return

    mode = "offline" if use_offline else "ollama"
    console.print(
        f"[green]Extracted[/green] {total_proposals} proposal(s) via {mode} "
        f"({total_processed} file(s), skipped {total_skipped} unchanged)"
    )
    if extractor and extractor.failed_chunks:
        console.print(
            f"[yellow]Warning:[/yellow] {extractor.failed_chunks} chunk(s) failed "
            f"(skipped). Increase timeout or use parallel_requests: 1."
        )
        for err in extractor.last_errors[:2]:
            console.print(f"  [dim]{err}[/dim]")
    if dry_run:
        console.print("[dim]Dry run — proposals were not saved[/dim]")


@memory_app.command("list-proposed")
def memory_list_proposed() -> None:
    """List pending memory proposals."""
    store = _store()
    proposals = store.list_proposed(ProposalStatus.PENDING)
    if not proposals:
        console.print("[yellow]No pending proposals.[/yellow]")
        return

    table = Table(title="Pending Memory Proposals")
    table.add_column("ID")
    table.add_column("Category")
    table.add_column("Summary")
    table.add_column("Source")

    for p in proposals:
        summary = ""
        if p.profile:
            summary = f"{p.profile.key} = {p.profile.value}"
        elif p.preference:
            summary = f"{p.preference.key} = {p.preference.value}"
        elif p.episode:
            summary = p.episode.summary[:80]
        table.add_row(p.id, p.category.value, summary, p.source.value)
    console.print(table)
    console.print("\n[dim]Tip:[/dim] Run [bold]membrane memory review[/bold] to approve/reject interactively.")


@memory_app.command("review")
def memory_review(
    category: Annotated[
        str | None,
        typer.Option(help="Filter: profile, preference, or episode"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(help="Max proposals to review (0 = all)"),
    ] = 0,
) -> None:
    """Interactively approve or reject pending proposals one at a time."""
    cat: MemoryCategory | None = None
    if category:
        try:
            cat = MemoryCategory(category.lower())
        except ValueError as exc:
            raise typer.BadParameter("category must be profile, preference, or episode") from exc

    counts = run_interactive_review(
        _store(),
        console,
        category=cat,
        limit=limit if limit > 0 else None,
    )
    remaining = len(_store().list_proposed(ProposalStatus.PENDING))
    if counts["quit"]:
        console.print(f"[dim]{remaining} proposal(s) still pending[/dim]")
    elif remaining:
        console.print(f"[dim]{remaining} proposal(s) still pending[/dim]")


@memory_app.command("approve")
def memory_approve(
    proposal_id: Annotated[str | None, typer.Argument(help="Proposal ID")] = None,
    all_pending: Annotated[bool, typer.Option("--all", help="Approve all pending")] = False,
) -> None:
    """Approve a proposal and commit to memory."""
    store = _store()
    if all_pending:
        approved = store.approve_all_pending()
        console.print(f"[green]Approved[/green] {len(approved)} proposal(s)")
        return
    if not proposal_id:
        raise typer.BadParameter("Provide proposal_id or --all")
    store.approve(proposal_id)
    console.print(f"[green]Approved[/green] {proposal_id}")


@memory_app.command("reject")
def memory_reject(proposal_id: Annotated[str, typer.Argument(help="Proposal ID")]) -> None:
    """Reject a memory proposal."""
    _store().reject(proposal_id)
    console.print(f"[red]Rejected[/red] {proposal_id}")


@memory_app.command("show")
def memory_show() -> None:
    """Show current committed memory."""
    store = _store()
    console.print_json(data=store.snapshot())


@memory_app.command("clear-source")
def memory_clear_source(
    source: Annotated[str, typer.Argument(help="Source to clear: cursor, whatsapp, email, etc.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    ingest: Annotated[
        bool,
        typer.Option(
            "--ingest/--no-ingest",
            help="Also delete raw/parsed ingest files and manifest entries",
        ),
    ] = True,
) -> None:
    """Remove proposals, approved archive, live memory, and optionally ingest data for a source."""
    if not yes:
        parts = [f"all {source} proposals and committed memory"]
        if ingest:
            parts.append("raw/parsed ingest files")
        typer.confirm(f"Remove {' and '.join(parts)}?", abort=True)
    store = _store()
    try:
        counts = store.clear_source(source)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    manifest = _manifest()
    cleared = manifest.clear_extract_state(source)
    ingest_counts: dict[str, int] = {}
    if ingest:
        from membrane.ingest.lifecycle import clear_ingest_data

        try:
            ingest_counts = clear_ingest_data(_settings(), source, manifest=manifest)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    msg = (
        f"[green]Cleared[/green] {source}: "
        f"{counts['proposals_removed']} proposal(s), "
        f"{counts['approved_removed']} archive(s), "
        f"{counts['profile_removed']} profile, "
        f"{counts['preferences_removed']} preference(s), "
        f"{counts['episodes_removed']} episode(s); "
        f"reset {cleared} extract track(s)"
    )
    if ingest_counts:
        msg += (
            f"; {ingest_counts['raw']} raw, "
            f"{ingest_counts['parsed']} parsed, "
            f"{ingest_counts['chats']} chat(s), "
            f"{ingest_counts['manifest']} manifest entry(ies)"
        )
    console.print(msg)


@context_app.command("build")
def context_build(
    message: Annotated[str, typer.Argument(help="User message to build context for")],
) -> None:
    """Build system prompt + memory context for local inference."""
    builder = ContextBuilder(_store(), _persona())
    console.print(builder.dump_context(user_query=message))


@context_app.command("chat")
def context_chat(
    message: Annotated[str, typer.Argument(help="Message to send to local LLM")],
) -> None:
    """Chat with local Ollama using memory-injected context."""
    persona = _persona()
    client = OllamaClient(persona.llm)
    builder = ContextBuilder(_store(), persona)
    messages = builder.build_messages(message)
    if not client.health_check():
        raise typer.Exit("Ollama not reachable. Start with: ollama serve")
    reply = client.chat(messages)
    console.print(f"[bold]Assistant:[/bold] {reply}")


@chat_app.command("record")
def chat_record(
    session_id: Annotated[str | None, typer.Option(help="Session ID")] = None,
    role: Annotated[str, typer.Option(help="user or assistant")] = "user",
    content: Annotated[str, typer.Option(help="Message content")] = "",
) -> None:
    """Record a chat turn for later SFT export."""
    settings = _settings()
    sid = session_id or uuid.uuid4().hex[:12]
    logger = ChatLogger(settings.chats_dir)
    session = logger.record_turn(sid, role=role, content=content)
    console.print(f"[green]Recorded[/green] turn in session {session.id}")


@chat_app.command("correct")
def chat_correct(
    session_id: Annotated[str, typer.Argument(help="Session ID")],
    prompt: Annotated[str, typer.Option(help="Original user prompt")],
    rejected: Annotated[str, typer.Option(help="Assistant draft you rejected")],
    chosen: Annotated[str, typer.Option(help="Your preferred response")],
) -> None:
    """Record a DPO preference pair from your edit."""
    settings = _settings()
    logger = ChatLogger(settings.chats_dir)
    example = logger.record_correction(session_id, prompt, rejected, chosen, settings.training_dir / "dpo")
    console.print(f"[green]Saved DPO example[/green] prompt={example.prompt[:40]}...")


@export_app.command("sft")
def export_sft() -> None:
    """Export SFT JSONL from chats + memory."""
    settings = _settings()
    persona = _persona()
    store = _store()
    builder = ContextBuilder(store, persona)
    exporter = TrainingExporter(
        store=store,
        context_builder=builder,
        chats_dir=settings.chats_dir,
        export_dir=settings.training_dir / "export",
    )
    path = exporter.export_sft()
    console.print(f"[green]Exported SFT[/green] → {path}")


@export_app.command("dpo")
def export_dpo() -> None:
    """Export DPO JSONL from recorded corrections."""
    settings = _settings()
    persona = _persona()
    store = _store()
    builder = ContextBuilder(store, persona)
    exporter = TrainingExporter(
        store=store,
        context_builder=builder,
        chats_dir=settings.chats_dir,
        export_dir=settings.training_dir / "export",
    )
    path = exporter.export_dpo()
    console.print(f"[green]Exported DPO[/green] → {path}")


@export_app.command("memory")
def export_memory_snapshot() -> None:
    """Export memory snapshot JSON."""
    settings = _settings()
    persona = _persona()
    store = _store()
    builder = ContextBuilder(store, persona)
    exporter = TrainingExporter(
        store=store,
        context_builder=builder,
        chats_dir=settings.chats_dir,
        export_dir=settings.training_dir / "export",
    )
    path = exporter.export_memory_snapshot()
    console.print(f"[green]Exported memory[/green] → {path}")


@dataset_app.command("prepare-summarization")
def dataset_prepare_summarization(
    lang: Annotated[str, typer.Option(help="Language code used in corpus filename")] = "en",
    label: Annotated[
        bool,
        typer.Option(help="Label summaries with local Ollama (slow; CPU ok but patience needed)"),
    ] = False,
    workers: Annotated[
        int,
        typer.Option(help="Parallel Ollama requests when labeling (0 = auto)"),
    ] = 0,
) -> None:
    """Build summarization JSONL from downloaded Wikipedia corpus."""
    settings = _settings()
    persona = _persona()
    raw_path = settings.wiki_corpus_dir / "raw" / f"{lang}_articles.jsonl"
    if not raw_path.exists():
        raise typer.BadParameter(f"Corpus not found: {raw_path}. Run: membrane ingest wiki")

    articles = load_articles(raw_path)
    examples = build_summarization_corpus(articles)
    if label:
        client = OllamaClient(persona.llm)
        if not client.health_check():
            raise typer.Exit("Ollama not reachable. Start with: ollama serve")
        n = _resolve_workers(workers)
        console.print(
            f"[cyan]Labeling[/cyan] {len(examples)} articles with {persona.llm.model} "
            f"({n} parallel requests, {client._ollama_options(None)['num_thread']} threads each)..."
        )
        examples = label_summaries_with_ollama(
            examples, client=client, model=persona.llm.model, workers=n
        )

    out_path = settings.datasets_dir / "summarization" / f"wiki_{lang}.jsonl"
    save_summarization_jsonl(examples, out_path)
    labeled = sum(1 for e in examples if e.metadata.get("labeled"))
    console.print(f"[green]Wrote[/green] {len(examples)} rows ({labeled} labeled) → {out_path}")


@export_app.command("summarization")
def export_summarization(
    lang: Annotated[str, typer.Option(help="Language suffix for wiki dataset")] = "en",
) -> None:
    """Copy prepared Wikipedia summarization dataset to training export folder."""
    settings = _settings()
    src = settings.datasets_dir / "summarization" / f"wiki_{lang}.jsonl"
    if not src.exists():
        raise typer.BadParameter(f"Dataset not found: {src}. Run: membrane dataset prepare-summarization")
    dest = settings.training_dir / "export" / f"summarization_wiki_{lang}.jsonl"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    console.print(f"[green]Exported summarization[/green] → {dest}")


if __name__ == "__main__":
    app()
