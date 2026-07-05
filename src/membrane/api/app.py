"""FastAPI control plane for membrane UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from membrane.config import get_settings, load_persona
from membrane.config_policy import TrainingPolicy, load_training_policy, save_training_policy
from membrane.ingest.lifecycle import parse_all_server_sources, parse_server_source
from membrane.ingest.agents import list_providers
from membrane.ingest.server_models import SERVER_SOURCES
from membrane.llm.ollama import OllamaClient
from membrane.memory.models import MemoryCategory, ProposalStatus
from membrane.memory.review import proposal_to_dict
from membrane.memory.store import MemoryStore
from membrane.server.auth import resolve_server_token
from membrane.tracking.manifest import ManifestStore


def _count_agent_sessions(settings) -> int:
    total = 0
    providers = settings.list_agent_providers() or ["cursor"]
    for provider in providers:
        parsed = settings.resolved_agent_parsed_dir(provider)
        if parsed.exists():
            total += len(list(parsed.glob("*.jsonl")))
    return total


def create_app(ui_dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="membrane", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def store() -> MemoryStore:
        return MemoryStore(get_settings().memory_dir)

    def manifest() -> ManifestStore:
        return ManifestStore(get_settings().manifest_path)

    @app.get("/api/status")
    def api_status() -> dict:
        settings = get_settings()
        persona = load_persona()
        client = OllamaClient(persona.llm)
        m = manifest()
        mem = store()
        pending = len(mem.list_proposed(ProposalStatus.PENDING))
        return {
            "ollama_ok": client.health_check(),
            "ollama_model": persona.llm.model,
            "pending_proposals": pending,
            "approved_archive": len(list((settings.memory_dir / "approved").glob("*.json"))),
            "profile_count": len(mem.load_profile()),
            "preference_count": len(mem.load_preferences()),
            "episode_count": len(mem.load_episodes()),
            "tracked_entries": len(m.manifest.entries),
            "agent_sessions": _count_agent_sessions(settings),
            "agent_providers": settings.list_agent_providers(),
            "stale_extract_agents": sum(
                len(m.list_stale_extracted(provider)) for provider in settings.list_agent_providers()
            ),
            "chats": len(list(settings.chats_dir.glob("*.json"))),
            "phase": load_training_policy().phase,
        }

    @app.get("/api/memory/snapshot")
    def memory_snapshot() -> dict:
        return store().snapshot()

    @app.get("/api/memory/proposed")
    def list_proposed(
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        mem = store()
        proposals = mem.list_proposed(ProposalStatus.PENDING)
        if category:
            try:
                cat = MemoryCategory(category)
                proposals = [p for p in proposals if p.category == cat]
            except ValueError as exc:
                raise HTTPException(400, "invalid category") from exc
        total = len(proposals)
        page = proposals[offset : offset + limit]
        return {
            "total": total,
            "items": [proposal_to_dict(p, mem) for p in page],
        }

    @app.get("/api/memory/proposed/{proposal_id}")
    def get_proposal(proposal_id: str) -> dict:
        path = store().proposed_dir / f"{proposal_id}.json"
        if not path.exists():
            raise HTTPException(404, "proposal not found")
        from membrane.memory.models import MemoryProposal

        proposal = MemoryProposal.model_validate_json(path.read_text(encoding="utf-8"))
        return proposal_to_dict(proposal, store())

    @app.post("/api/memory/proposed/{proposal_id}/approve")
    def approve_proposal(proposal_id: str) -> dict:
        try:
            proposal = store().approve(proposal_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return proposal_to_dict(proposal, store())

    @app.post("/api/memory/proposed/{proposal_id}/reject")
    def reject_proposal(proposal_id: str) -> dict:
        try:
            proposal = store().reject(proposal_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return proposal_to_dict(proposal, store())

    @app.post("/api/memory/proposed/approve-all")
    def approve_all() -> dict:
        approved = store().approve_all_pending()
        return {"count": len(approved)}

    @app.get("/api/ingest/stats")
    def ingest_stats() -> dict:
        settings = get_settings()
        sources: dict[str, tuple] = {
            "whatsapp": (settings.whatsapp_raw_dir, settings.whatsapp_parsed_dir),
        }
        for provider in settings.list_agent_providers() or list_providers():
            sources[provider] = (
                settings.resolved_agent_raw_dir(provider),
                settings.resolved_agent_parsed_dir(provider),
            )
        for src in SERVER_SOURCES:
            sources[src] = (settings.server_raw_dir(src), settings.server_parsed_dir(src))
        out = {}
        for name, (raw_d, parsed_d) in sources.items():
            out[name] = {
                "raw": len(list(raw_d.glob("*"))) if raw_d.exists() else 0,
                "parsed": len(list(parsed_d.glob("*.jsonl"))) if parsed_d.exists() else 0,
            }
        return out

    class ParseRequest(BaseModel):
        source: str = "all"
        force: bool = False

    @app.post("/api/ingest/parse")
    def ingest_parse(body: ParseRequest) -> dict:
        settings = get_settings()
        m = manifest()
        if body.source in ("all", "server"):
            results = parse_all_server_sources(settings, m, force=body.force)
            return {
                src: {"processed": s.processed, "skipped": s.skipped}
                for src, s in results.items()
            }
        if body.source == "whatsapp":
            raise HTTPException(400, "use CLI: membrane ingest whatsapp")
        if body.source in SERVER_SOURCES:
            stats = parse_server_source(
                body.source,  # type: ignore[arg-type]
                settings.server_raw_dir(body.source),
                settings.server_parsed_dir(body.source),
                m,
                force=body.force,
            )
            return {body.source: {"processed": stats.processed, "skipped": stats.skipped}}
        raise HTTPException(400, "unknown source")

    @app.get("/api/server/status")
    def server_status() -> dict:
        settings = get_settings()
        persona = load_persona()
        token = resolve_server_token(settings, persona)
        counts = {}
        for src in SERVER_SOURCES:
            counts[src] = {
                "raw": len(list(settings.server_raw_dir(src).glob("*.json"))),
                "parsed": len(list(settings.server_parsed_dir(src).glob("*.jsonl"))),
            }
        return {
            "host": persona.server.host,
            "port": persona.server.port,
            "parse_interval_seconds": persona.server.parse_interval_seconds,
            "auto_extract": persona.server.auto_extract,
            "token": token,
            "sources": counts,
        }

    @app.get("/api/policy")
    def get_policy() -> dict:
        policy = load_training_policy()
        return policy.model_dump()

    @app.put("/api/policy")
    def put_policy(body: dict) -> dict:
        policy = TrainingPolicy.model_validate(body)
        save_training_policy(policy)
        return policy.model_dump()

    if ui_dist and ui_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(ui_dist), html=True), name="ui")

    return app
