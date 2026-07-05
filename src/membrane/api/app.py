"""FastAPI control plane for membrane UI."""

from __future__ import annotations

import httpx
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from membrane.config import (
    BoundariesConfig,
    FirecrawlConfig,
    MemoryConfig,
    PerformanceConfig,
    ServerConfig,
    ShellConfig,
    StyleConfig,
    WebSearchConfig,
    get_settings,
    load_persona,
    save_persona,
)
from membrane.config_integrations import (
    FineTuneConfig,
    IntegrationsConfig,
    McpServerConfig,
    ToolIntegrationConfig,
    integrations_status,
    load_integrations,
    save_integrations,
)
from membrane.config_policy import (
    SOURCE_CAPABILITIES,
    SOURCE_DESCRIPTIONS,
    TrainingPolicy,
    load_training_policy,
    save_training_policy,
)
from membrane.inference.context import ContextBuilder
from membrane.inference.shell import (
    format_shell_results_block,
    iter_shell_loop,
    shell_result_to_dict,
    shell_results_to_metadata,
)
from membrane.inference.websearch import (
    SearchError,
    decide_search,
    enrich_search_with_pages,
    format_results_block,
    search_web,
)
from membrane.integrations.credentials import (
    clear_tool_credentials,
    credentials_catalog,
    upsert_tool_credentials,
)
from membrane.integrations.oauth import finish_oauth, oauth_providers, start_oauth
from membrane.ingest.lifecycle import parse_all_server_sources, parse_server_source
from membrane.ingest.server_models import SERVER_SOURCES
from membrane.learning.chat_log import ChatLogger
from membrane.learning.chat_memory import suggest_memory_from_turn
from membrane.learning.export import TrainingExporter
from membrane.learning.job import FineTuneBusyError, is_fine_tune_running, start_fine_tune_job
from membrane.learning.trainer import (
    FineTuneRunner,
    training_deps_available,
    training_requirements_hint,
)
from membrane.llm.ollama import OllamaClient, OllamaError
from membrane.memory.models import (
    MemoryCategory,
    MemorySource,
    PreferenceEntry,
    ProfileEntry,
    ProposalStatus,
    ChatSession,
    ChatTurn,
    new_id,
)
from membrane.memory.books import (
    BookEntry,
    BooksStore,
    remove_book_episode,
    sync_book_episode,
)
from membrane.memory.review import proposal_to_dict
from membrane.memory.store import MemoryStore
from membrane.server.auth import resolve_server_token
from membrane.tracking.manifest import ManifestStore
from membrane.tracking.queue import build_ingest_queue_stats


class ProfileUpsertRequest(BaseModel):
    key: str
    value: str
    confidence: float = 0.8


class PreferenceUpsertRequest(BaseModel):
    key: str
    value: str
    strength: float = 0.7


class PersonaLLMUpdate(BaseModel):
    model: str | None = None
    extractor_model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None
    num_threads: int | None = None
    parallel_requests: int | None = None
    context_window: int | None = None
    thinking_enabled: bool | None = None


class PersonaPerformanceUpdate(BaseModel):
    workers: int | None = None


class PersonaMemoryUpdate(BaseModel):
    use_profile: bool | None = None
    use_preferences: bool | None = None
    use_episodes: bool | None = None
    max_episodes_in_context: int | None = None
    confirm_before_save: bool | None = None


class PersonaStyleUpdate(BaseModel):
    format: str | None = None
    max_length: str | None = None
    empathy_level: float | None = None
    proactivity: float | None = None
    independent_opinions: bool | None = None


class PersonaBoundariesUpdate(BaseModel):
    never_claim_to_have_done: list[str] | None = None
    ask_when_unsure: bool | None = None


class PersonaWebSearchUpdate(BaseModel):
    enabled: bool | None = None
    max_results: int | None = None
    timeout_seconds: float | None = None


class PersonaFirecrawlUpdate(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = None
    max_chars: int | None = None
    scrape_in_chat: bool | None = None
    max_pages_in_chat: int | None = None


class PersonaShellUpdate(BaseModel):
    enabled: bool | None = None
    timeout_seconds: float | None = None
    max_output_chars: int | None = None
    max_commands_per_turn: int | None = None
    workspace_dir: str | None = None
    allow_network: bool | None = None


class PersonaServerUpdate(BaseModel):
    host: str | None = None
    port: int | None = None
    token: str | None = None
    parse_interval_seconds: int | None = None
    auto_extract: bool | None = None


class PersonaUpdateRequest(BaseModel):
    llm: PersonaLLMUpdate | None = None
    performance: PersonaPerformanceUpdate | None = None
    memory: PersonaMemoryUpdate | None = None
    style: PersonaStyleUpdate | None = None
    boundaries: PersonaBoundariesUpdate | None = None
    identity: dict[str, str] | None = None
    self_names: list[str] | None = None
    server: PersonaServerUpdate | None = None
    web_search: PersonaWebSearchUpdate | None = None
    firecrawl: PersonaFirecrawlUpdate | None = None
    shell: PersonaShellUpdate | None = None


class BookUpsertRequest(BaseModel):
    title: str
    author: str = ""
    rating: int | None = None
    notes: str = ""
    read_year: int | None = None


class ChatMessageRequest(BaseModel):
    content: str


class ChatSessionPatchRequest(BaseModel):
    include_in_training: bool | None = None


class ParseRequest(BaseModel):
    source: str = "all"
    force: bool = False


class IntegrationsUpdateRequest(BaseModel):
    mcp_servers: list[McpServerConfig] | None = None
    tools: list[ToolIntegrationConfig] | None = None
    fine_tune: FineTuneConfig | None = None


class TrainingExportRequest(BaseModel):
    kind: str = "sft"


class FineTuneRequest(BaseModel):
    base_model: str | None = None
    output_model: str | None = None


class ToolCredentialsUpdate(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


def _request_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


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

    def context_builder(session_id: str | None = None) -> ContextBuilder:
        settings = get_settings()
        return ContextBuilder(store(), load_persona())

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
        policy = load_training_policy()
        queue = build_ingest_queue_stats(settings, m, policy)
        return {
            "ollama_ok": client.health_check(),
            "model_ready": client.model_ready(persona.llm.model),
            "ollama_model": persona.llm.model,
            "extractor_model": persona.llm.extractor_model,
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
            "needs_parse": queue["totals"]["needs_parse"],
            "needs_extract": queue["totals"]["needs_extract"],
            "needs_train": queue["totals"]["needs_train"],
            "chats": len(list(settings.chats_dir.glob("*.json"))),
            "phase": policy.phase,
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

    @app.post("/api/memory/profile")
    def upsert_profile(body: ProfileUpsertRequest) -> dict:
        mem = store()
        existing = next((e for e in mem.load_profile() if e.key == body.key), None)
        entry = ProfileEntry(
            id=existing.id if existing else new_id(),
            key=body.key.strip(),
            value=body.value.strip(),
            confidence=body.confidence,
            source=MemorySource.MANUAL,
        )
        if not entry.key or not entry.value:
            raise HTTPException(400, "key and value are required")
        mem.upsert_profile(entry)
        return entry.model_dump(mode="json")

    @app.delete("/api/memory/profile/{key}")
    def delete_profile(key: str) -> dict:
        if not store().delete_profile(key):
            raise HTTPException(404, "profile entry not found")
        return {"deleted": key}

    @app.post("/api/memory/preferences")
    def upsert_preference(body: PreferenceUpsertRequest) -> dict:
        mem = store()
        existing = next((e for e in mem.load_preferences() if e.key == body.key), None)
        entry = PreferenceEntry(
            id=existing.id if existing else new_id(),
            key=body.key.strip(),
            value=body.value.strip(),
            strength=body.strength,
            source=MemorySource.MANUAL,
        )
        if not entry.key or not entry.value:
            raise HTTPException(400, "key and value are required")
        mem.upsert_preference(entry)
        return entry.model_dump(mode="json")

    @app.delete("/api/memory/preferences/{key}")
    def delete_preference(key: str) -> dict:
        if not store().delete_preference(key):
            raise HTTPException(404, "preference entry not found")
        return {"deleted": key}

    def books() -> BooksStore:
        return BooksStore(get_settings().books_path)

    @app.get("/api/books")
    def list_books() -> dict:
        items = sorted(books().load(), key=lambda b: b.added_at, reverse=True)
        return {"items": [b.model_dump(mode="json") for b in items]}

    @app.post("/api/books")
    def add_book(body: BookUpsertRequest) -> dict:
        title = body.title.strip()
        if not title:
            raise HTTPException(400, "title is required")
        try:
            book = BookEntry(
                title=title,
                author=body.author.strip(),
                rating=body.rating,
                notes=body.notes.strip(),
                read_year=body.read_year,
            )
        except ValidationError as exc:
            raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        book = sync_book_episode(store(), book)
        books().upsert(book)
        return book.model_dump(mode="json")

    @app.put("/api/books/{book_id}")
    def update_book(book_id: str, body: BookUpsertRequest) -> dict:
        existing = books().get(book_id)
        if existing is None:
            raise HTTPException(404, "book not found")
        title = body.title.strip()
        if not title:
            raise HTTPException(400, "title is required")
        try:
            updated = existing.model_copy(
                update={
                    "title": title,
                    "author": body.author.strip(),
                    "rating": body.rating,
                    "notes": body.notes.strip(),
                    "read_year": body.read_year,
                }
            )
            BookEntry.model_validate(updated.model_dump())
        except ValidationError as exc:
            raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        updated = sync_book_episode(store(), updated)
        books().upsert(updated)
        return updated.model_dump(mode="json")

    @app.delete("/api/books/{book_id}")
    def delete_book(book_id: str) -> dict:
        deleted = books().delete(book_id)
        if deleted is None:
            raise HTTPException(404, "book not found")
        remove_book_episode(store(), deleted)
        return {"deleted": book_id}

    @app.get("/api/ingest/stats")
    def ingest_stats() -> dict:
        settings = get_settings()
        policy = load_training_policy()
        return build_ingest_queue_stats(settings, manifest(), policy)

    @app.get("/api/persona")
    def get_persona() -> dict:
        return load_persona().model_dump()

    @app.put("/api/persona")
    def put_persona(body: PersonaUpdateRequest) -> dict:
        persona = load_persona()
        if body.llm:
            updates = body.llm.model_dump(exclude_none=True)
            persona.llm = persona.llm.model_copy(update=updates)
        if body.performance:
            updates = body.performance.model_dump(exclude_none=True)
            persona.performance = persona.performance.model_copy(update=updates)
        if body.memory:
            updates = body.memory.model_dump(exclude_none=True)
            try:
                persona.memory = MemoryConfig.model_validate(
                    {**persona.memory.model_dump(), **updates}
                )
            except ValidationError as exc:
                raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        if body.style:
            updates = body.style.model_dump(exclude_none=True)
            try:
                persona.style = StyleConfig.model_validate(
                    {**persona.style.model_dump(), **updates}
                )
            except ValidationError as exc:
                raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        if body.boundaries:
            updates = body.boundaries.model_dump(exclude_none=True)
            try:
                persona.boundaries = BoundariesConfig.model_validate(
                    {**persona.boundaries.model_dump(), **updates}
                )
            except ValidationError as exc:
                raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        if body.identity is not None:
            persona.identity = {**persona.identity, **body.identity}
        if body.self_names is not None:
            persona.self_names = body.self_names
        if body.server:
            updates = body.server.model_dump(exclude_none=True)
            try:
                persona.server = ServerConfig.model_validate(
                    {**persona.server.model_dump(), **updates}
                )
            except ValidationError as exc:
                raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        if body.web_search:
            updates = body.web_search.model_dump(exclude_none=True)
            try:
                persona.web_search = WebSearchConfig.model_validate(
                    {**persona.web_search.model_dump(), **updates}
                )
            except ValidationError as exc:
                raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        if body.firecrawl:
            updates = body.firecrawl.model_dump(exclude_none=True)
            try:
                persona.firecrawl = FirecrawlConfig.model_validate(
                    {**persona.firecrawl.model_dump(), **updates}
                )
            except ValidationError as exc:
                raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        if body.shell:
            updates = body.shell.model_dump(exclude_none=True)
            try:
                persona.shell = ShellConfig.model_validate(
                    {**persona.shell.model_dump(), **updates}
                )
            except ValidationError as exc:
                raise HTTPException(400, str(exc.errors()[0]["msg"])) from exc
        save_persona(persona)
        return persona.model_dump()

    @app.get("/api/ollama/models")
    def ollama_models() -> dict:
        persona = load_persona()
        client = OllamaClient(persona.llm)
        models = client.list_models()
        return {
            "models": models,
            "ollama_ok": client.health_check(),
            "configured_model": persona.llm.model,
            "model_ready": client.has_model(persona.llm.model),
        }

    @app.get("/api/policy/capabilities")
    def policy_capabilities() -> dict:
        return {
            "sources": SOURCE_CAPABILITIES,
            "descriptions": SOURCE_DESCRIPTIONS,
        }

    @app.get("/api/chat/sessions")
    def list_chat_sessions() -> dict:
        settings = get_settings()
        logger = ChatLogger(settings.chats_dir)
        items = []
        for path in reversed(logger.list_sessions()):
            session = ChatSession.model_validate_json(path.read_text(encoding="utf-8"))
            preview = next((t.content for t in reversed(session.turns) if t.role == "user"), "")
            last_turn = session.turns[-1] if session.turns else None
            items.append(
                {
                    "id": session.id,
                    "turns": len(session.turns),
                    "preview": preview[:120],
                    "updated_at": last_turn.timestamp.isoformat()
                    if last_turn and last_turn.timestamp
                    else None,
                    "include_in_training": session.metadata.get("include_in_training", True)
                    is not False,
                }
            )
        return {"items": items}

    @app.post("/api/chat/sessions")
    def create_chat_session() -> dict:
        settings = get_settings()
        logger = ChatLogger(settings.chats_dir)
        session = ChatSession()
        logger.save_session(session)
        return session.model_dump(mode="json")

    @app.get("/api/chat/sessions/{session_id}")
    def get_chat_session(session_id: str) -> dict:
        settings = get_settings()
        logger = ChatLogger(settings.chats_dir)
        path = logger._session_path(session_id)
        if not path.exists():
            raise HTTPException(404, "session not found")
        session = logger.load_session(session_id)
        return session.model_dump(mode="json")

    @app.delete("/api/chat/sessions/{session_id}")
    def delete_chat_session(session_id: str) -> dict:
        settings = get_settings()
        logger = ChatLogger(settings.chats_dir)
        if not logger.delete_session(session_id):
            raise HTTPException(404, "session not found")
        return {"deleted": session_id}

    @app.get("/api/chat/sessions/{session_id}/context-usage")
    def chat_context_usage(session_id: str, draft: str = "") -> dict:
        settings = get_settings()
        logger = ChatLogger(settings.chats_dir)
        path = logger._session_path(session_id)
        if not path.exists():
            raise HTTPException(404, "session not found")
        session = logger.load_session(session_id)
        builder = context_builder(session_id)
        turns = list(session.turns)
        draft_text = draft.strip()
        usage = builder.estimate_context_usage(turns, draft_user=draft_text or None)
        usage["include_in_training"] = session.metadata.get("include_in_training", True) is not False
        usage["session_turns"] = len(session.turns)
        return usage

    @app.patch("/api/chat/sessions/{session_id}")
    def patch_chat_session(session_id: str, body: ChatSessionPatchRequest) -> dict:
        settings = get_settings()
        logger = ChatLogger(settings.chats_dir)
        path = logger._session_path(session_id)
        if not path.exists():
            raise HTTPException(404, "session not found")
        session = logger.load_session(session_id)
        if body.include_in_training is not None:
            session.metadata["include_in_training"] = body.include_in_training
        logger.save_session(session)
        return session.model_dump(mode="json")

    @app.post("/api/chat/sessions/{session_id}/message")
    def chat_message(session_id: str, body: ChatMessageRequest) -> StreamingResponse:
        content = body.content.strip()
        if not content:
            raise HTTPException(400, "message content is required")

        settings = get_settings()
        persona = load_persona()
        client = OllamaClient(persona.llm)
        if not client.health_check():
            raise HTTPException(503, "Ollama not reachable. Start with: ollama serve")
        if not client.has_model(persona.llm.model):
            raise HTTPException(
                400,
                f"Model '{persona.llm.model}' is not installed. "
                f"Run: ollama pull {persona.llm.model}",
            )

        logger = ChatLogger(settings.chats_dir)
        path = logger._session_path(session_id)
        if not path.exists():
            raise HTTPException(404, "session not found")

        session = logger.load_session(session_id)
        builder = context_builder(session_id)
        draft_turns = [*session.turns, ChatTurn(role="user", content=content)]
        messages = builder.build_conversation_messages(draft_turns)

        def event_stream() -> Iterator[str]:
            memory_context = builder.build_memory_context_dict(user_query=content)
            yield json.dumps({"context": memory_context}) + "\n"
            yield json.dumps(
                {"context_usage": builder.estimate_context_usage(session.turns, draft_user=content)}
            ) + "\n"

            web_search_ref: dict | None = None
            shell_ref: dict | None = None
            tool_tokens: dict[str, int] = {}
            if persona.web_search.enabled:
                query = decide_search(client, draft_turns)
                if query:
                    yield json.dumps(
                        {"web_search": {"status": "searching", "query": query}}
                    ) + "\n"
                    try:
                        results = search_web(query, persona.web_search)
                    except SearchError:
                        results = []
                    search_content = ""
                    if results:
                        search_content = format_results_block(query, results)
                        tool_tokens["web_search"] = len(search_content) // 4
                        if persona.firecrawl.enabled and persona.firecrawl.scrape_in_chat:
                            page_block = enrich_search_with_pages(results, persona.firecrawl)
                            if page_block:
                                tool_tokens["firecrawl"] = len(page_block) // 4
                                search_content = f"{search_content}\n\n{page_block}"
                        messages.insert(
                            1,
                            {
                                "role": "system",
                                "content": search_content,
                            },
                        )
                    web_search_ref = {
                        "query": query,
                        "results": [{"title": r.title, "url": r.url} for r in results],
                        "content_chars": len(search_content),
                        "tool_tokens": dict(tool_tokens),
                    }
                    yield json.dumps(
                        {
                            "web_search": {
                                "status": "done",
                                "query": query,
                                "results": web_search_ref["results"],
                            }
                        }
                    ) + "\n"

            if persona.shell.enabled:
                shell_results: list = []
                yield json.dumps({"shell": {"status": "running"}}) + "\n"
                for phase, command, snapshot in iter_shell_loop(
                    client, draft_turns, persona.shell
                ):
                    payload: dict = {
                        "status": "running",
                        "commands": [shell_result_to_dict(r) for r in snapshot],
                    }
                    if phase == "start":
                        payload["command"] = command
                    yield json.dumps({"shell": payload}) + "\n"
                    if phase == "complete":
                        shell_results = snapshot
                if shell_results:
                    shell_content = format_shell_results_block(shell_results, persona.shell)
                    if shell_content:
                        tool_tokens["shell"] = len(shell_content) // 4
                        messages.insert(1, {"role": "system", "content": shell_content})
                    shell_ref = shell_results_to_metadata(shell_results, shell_content)
                    yield json.dumps(
                        {
                            "shell": {
                                "status": "done",
                                "commands": shell_ref["commands"],
                            }
                        }
                    ) + "\n"
                else:
                    yield json.dumps({"shell": {"status": "done", "commands": []}}) + "\n"

            if tool_tokens:
                yield json.dumps(
                    {
                        "context_usage": builder.estimate_context_usage(
                            session.turns,
                            draft_user=content,
                            tools_breakdown=tool_tokens,
                        )
                    }
                ) + "\n"

            parts: list[str] = []
            thinking_parts: list[str] = []
            try:
                for chunk in client.chat_stream(messages):
                    if chunk.kind == "thinking":
                        thinking_parts.append(chunk.text)
                        yield json.dumps({"thinking_delta": chunk.text}) + "\n"
                    else:
                        parts.append(chunk.text)
                        yield json.dumps({"delta": chunk.text}) + "\n"
            except OllamaError as exc:
                yield json.dumps({"error": str(exc)}) + "\n"
                return
            reply = "".join(parts)
            logger.record_turn(session_id, "user", content)
            turn_meta: dict = {"memory_context": memory_context}
            if web_search_ref:
                turn_meta["web_search"] = web_search_ref
            if shell_ref:
                turn_meta["shell"] = shell_ref
            if thinking_parts:
                turn_meta["thinking"] = "".join(thinking_parts)
            final = logger.record_turn(session_id, "assistant", reply, turn_metadata=turn_meta)

            yield json.dumps(
                {
                    "context_usage": builder.estimate_context_usage(
                        final.turns,
                        tools_breakdown=tool_tokens or None,
                    )
                }
            ) + "\n"

            memory_suggestions: list[dict] = []
            if persona.memory.confirm_before_save:
                try:
                    mem = store()
                    proposals = suggest_memory_from_turn(mem, persona, content, reply)
                    for proposal in proposals:
                        mem.propose(proposal)
                        memory_suggestions.append(proposal_to_dict(proposal, mem))
                except Exception:
                    pass

            yield json.dumps(
                {
                    "done": True,
                    "reply": reply,
                    "session": final.model_dump(mode="json"),
                    "memory_suggestions": memory_suggestions,
                }
            ) + "\n"

        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

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
    def put_policy(policy: TrainingPolicy) -> dict:
        save_training_policy(policy)
        return policy.model_dump()

    @app.get("/api/integrations")
    def get_integrations() -> dict:
        return integrations_status()

    @app.put("/api/integrations")
    def put_integrations(body: IntegrationsUpdateRequest) -> dict:
        config = load_integrations()
        if body.mcp_servers is not None:
            config.mcp_servers = body.mcp_servers
        if body.tools is not None:
            config.tools = body.tools
        if body.fine_tune is not None:
            config.fine_tune = body.fine_tune
        save_integrations(config)
        return integrations_status(config)

    @app.get("/api/integrations/credentials")
    def get_integration_credentials() -> dict:
        catalog = credentials_catalog()
        catalog["oauth_providers"] = oauth_providers()
        return catalog

    @app.put("/api/integrations/credentials/{tool_id}")
    def put_integration_credentials(tool_id: str, body: ToolCredentialsUpdate) -> dict:
        try:
            upsert_tool_credentials(tool_id, body.values)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return credentials_catalog()["tools"][tool_id]

    @app.delete("/api/integrations/credentials/{tool_id}")
    def delete_integration_credentials(tool_id: str) -> dict:
        try:
            clear_tool_credentials(tool_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"deleted": tool_id}

    @app.get("/api/oauth/{provider}/authorize")
    def oauth_authorize(provider: str, request: Request):
        try:
            url = start_oauth(provider, _request_base_url(request))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(url)

    @app.get("/api/oauth/{provider}/callback")
    def oauth_callback(provider: str, request: Request, code: str = "", state: str = ""):
        if not code or not state:
            raise HTTPException(400, "missing code or state")
        try:
            tool_id = finish_oauth(provider, code, state, _request_base_url(request))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"OAuth token exchange failed: {exc}") from exc
        return RedirectResponse(f"/tools?connected={tool_id}")

    def _training_exporter() -> TrainingExporter:
        settings = get_settings()
        persona = load_persona()
        integrations = load_integrations()
        client = OllamaClient(persona.llm)
        search_client = client if client.health_check() else None
        return TrainingExporter(
            store=store(),
            context_builder=ContextBuilder(store(), persona),
            chats_dir=settings.chats_dir,
            export_dir=settings.training_dir / "export",
            books_path=settings.books_path,
            settings=settings,
            fine_tune=integrations.fine_tune,
            persona=persona,
            search_client=search_client,
        )

    @app.get("/api/training/status")
    def training_status() -> dict:
        settings = get_settings()
        persona = load_persona()
        policy = load_training_policy()
        queue = build_ingest_queue_stats(settings, manifest(), policy)
        export_dir = settings.training_dir / "export"
        exports = []
        if export_dir.exists():
            for path in sorted(export_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
                if path.is_file():
                    stat = path.stat()
                    exports.append(
                        {
                            "name": path.name,
                            "size_bytes": stat.st_size,
                            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                        }
                    )
        integrations = load_integrations()
        exporter = _training_exporter()
        sft_preview = exporter.sft_preview()
        return {
            "needs_train": queue["totals"]["needs_train"],
            "chat_model": persona.llm.model,
            "extractor_model": persona.llm.extractor_model,
            "fine_tune": integrations.fine_tune.model_dump(),
            "fine_tune_running": is_fine_tune_running(),
            "training_available": training_deps_available(),
            "training_requirements": training_requirements_hint(),
            "exports": exports,
            "nightly_enabled": policy.nightly.enabled,
            "sft_sources": {
                "ui_sessions": sft_preview.ui_sessions,
                "agent_sessions": sft_preview.agent_sessions,
                "total_sessions": sft_preview.total_sessions,
                "chat_examples": sft_preview.chat_examples,
                "memory_examples": sft_preview.memory_examples,
                "book_examples": sft_preview.book_examples,
                "web_examples": sft_preview.web_examples,
                "total_examples": sft_preview.total_examples,
                "include_chats": sft_preview.include_chats,
                "enrich_from_web": sft_preview.enrich_from_web,
                "fetch_search_pages": sft_preview.fetch_search_pages,
            },
        }

    @app.post("/api/training/export")
    def training_export(body: TrainingExportRequest) -> dict:
        kind = body.kind.strip().lower()
        if kind not in ("sft", "dpo", "all"):
            raise HTTPException(400, "kind must be sft, dpo, or all")
        exporter = _training_exporter()
        paths: dict[str, str] = {}
        sft_stats = None
        if kind in ("sft", "all"):
            _, sft_stats = exporter.build_sft_examples()
            path = exporter.export_sft()
            paths["sft"] = str(path)
        if kind in ("dpo", "all"):
            path = exporter.export_dpo()
            paths["dpo"] = str(path)
        config = load_integrations()
        config.fine_tune.last_export_at = datetime.now(tz=UTC).isoformat()
        config.fine_tune.status = "ready"
        if not config.fine_tune.base_model:
            config.fine_tune.base_model = load_persona().llm.model
        save_integrations(config)
        result = {"paths": paths, "fine_tune": config.fine_tune.model_dump()}
        if sft_stats is not None:
            result["sft_stats"] = {
                "ui_sessions": sft_stats.ui_sessions,
                "agent_sessions": sft_stats.agent_sessions,
                "total_sessions": sft_stats.total_sessions,
                "chat_examples": sft_stats.chat_examples,
                "memory_examples": sft_stats.memory_examples,
                "book_examples": sft_stats.book_examples,
                "web_examples": sft_stats.web_examples,
                "total_examples": sft_stats.total_examples,
                "include_chats": sft_stats.include_chats,
                "enrich_from_web": sft_stats.enrich_from_web,
                "fetch_search_pages": sft_stats.fetch_search_pages,
            }
        return result

    @app.post("/api/training/fine-tune")
    def training_fine_tune(body: FineTuneRequest) -> dict:
        if is_fine_tune_running():
            raise HTTPException(409, "A fine-tune job is already running")
        if not training_deps_available():
            raise HTTPException(
                501,
                training_requirements_hint(),
            )

        persona = load_persona()
        config = load_integrations()
        base_model = (body.base_model or config.fine_tune.base_model or persona.llm.model).strip()
        output_model = (body.output_model or config.fine_tune.output_model).strip()
        if not base_model or not output_model:
            raise HTTPException(400, "base_model and output_model are required")

        config.fine_tune.base_model = base_model
        config.fine_tune.output_model = output_model
        config.fine_tune.status = "queued"
        config.fine_tune.status_message = "Fine-tune queued"
        config.fine_tune.progress_pct = 0
        config.fine_tune.last_error = None
        save_integrations(config)

        def runner_factory() -> FineTuneRunner:
            current = load_integrations().fine_tune
            return FineTuneRunner(
                config=current,
                settings=get_settings(),
                persona=load_persona(),
                exporter=_training_exporter(),
                ollama=OllamaClient(load_persona().llm),
            )

        try:
            fine_tune = start_fine_tune_job(runner_factory)
        except FineTuneBusyError as exc:
            raise HTTPException(409, str(exc)) from exc

        return {
            "status": fine_tune.status,
            "message": "Fine-tune started. Poll /api/training/status for progress.",
            "fine_tune": fine_tune.model_dump(),
        }

    if ui_dist and ui_dist.is_dir():
        index_path = ui_dist / "index.html"

        @app.get("/{full_path:path}")
        def serve_ui(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path == "api":
                raise HTTPException(404)
            if full_path:
                candidate = ui_dist / full_path
                if candidate.is_file():
                    return FileResponse(candidate)
            if not index_path.is_file():
                raise HTTPException(404, "UI not built")
            return FileResponse(index_path)

    return app
