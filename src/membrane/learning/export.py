"""Export training datasets (SFT / DPO) from local memory and chats."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from membrane.config_integrations import FineTuneConfig
from membrane.inference.context import ContextBuilder
from membrane.inference.websearch import (
    SearchError,
    SearchResult,
    decide_search,
    fetch_page_content,
    format_page_content_block,
    format_results_block,
    search_web,
)
from membrane.learning.chat_log import ChatLogger
from membrane.memory.books import BookEntry, BooksStore, book_episode_summary
from membrane.memory.models import ChatSession, ChatTurn, SFTExample
from membrane.memory.store import MemoryStore

if TYPE_CHECKING:
    from membrane.config import FirecrawlConfig, PersonaConfig, Settings, WebSearchConfig
    from membrane.llm.ollama import OllamaClient


@dataclass
class SftExportStats:
    ui_sessions: int
    agent_sessions: int
    total_sessions: int
    chat_examples: int
    memory_examples: int
    book_examples: int
    web_examples: int
    total_examples: int
    include_chats: bool
    enrich_from_web: bool
    fetch_search_pages: bool


class TrainingExporter:
    def __init__(
        self,
        store: MemoryStore,
        context_builder: ContextBuilder,
        chats_dir: Path,
        export_dir: Path,
        books_path: Path | None = None,
        settings: Settings | None = None,
        fine_tune: FineTuneConfig | None = None,
        persona: PersonaConfig | None = None,
        search_client: OllamaClient | None = None,
    ) -> None:
        self.store = store
        self.context_builder = context_builder
        self.chat_logger = ChatLogger(chats_dir)
        self.export_dir = export_dir
        self.books = BooksStore(books_path) if books_path else None
        self.settings = settings
        self.fine_tune = fine_tune or FineTuneConfig()
        self.persona = persona
        self.search_client = search_client
        self.export_dir.mkdir(parents=True, exist_ok=True)

    @property
    def web_search_config(self) -> WebSearchConfig:
        from membrane.config import WebSearchConfig

        if self.persona is not None:
            return self.persona.web_search
        return WebSearchConfig()

    @property
    def firecrawl_config(self) -> FirecrawlConfig:
        from membrane.config import FirecrawlConfig

        if self.persona is not None:
            return self.persona.firecrawl
        return FirecrawlConfig()

    def collect_chat_sessions(self) -> tuple[list[ChatSession], dict[str, int]]:
        """Gather UI chats and agent transcripts (deduped)."""
        seen: set[str] = set()
        sessions: list[ChatSession] = []
        counts = {"ui": 0, "agent": 0}

        def add(session: ChatSession, source: str) -> None:
            key = str(session.metadata.get("session_id") or session.id)
            if key in seen:
                return
            seen.add(key)
            sessions.append(session)
            counts[source] += 1

        for path in self.chat_logger.list_sessions():
            session = ChatSession.model_validate_json(path.read_text(encoding="utf-8"))
            if session.metadata.get("include_in_training") is False:
                continue
            add(session, "ui")

        if self.settings is not None:
            from membrane.ingest.agents.io import load_parsed_turns, read_session_meta

            for provider in self.settings.list_agent_providers():
                parsed_dir = self.settings.resolved_agent_parsed_dir(provider)
                if not parsed_dir.exists():
                    continue
                for path in sorted(parsed_dir.glob("*.jsonl")):
                    if ".meta." in path.name:
                        continue
                    agent_turns = load_parsed_turns(path)
                    if not agent_turns:
                        continue
                    meta = read_session_meta(path)
                    chat_turns = [
                        ChatTurn(role=t.role, content=t.content)  # type: ignore[arg-type]
                        for t in agent_turns
                        if t.role in ("user", "assistant") and t.content.strip()
                    ]
                    if len(chat_turns) < 2:
                        continue
                    agent = provider or meta.get("agent") or agent_turns[0].agent or "agent"
                    add(
                        ChatSession(
                            id=f"{agent}-{path.stem}",
                            turns=chat_turns,
                            metadata={
                                "source": agent,
                                "session_id": path.stem,
                                "agent": agent,
                            },
                        ),
                        "agent",
                    )

        return sessions, counts

    def _turn_web_search_meta(self, turn: ChatTurn) -> dict | None:
        if not isinstance(turn.metadata, dict):
            return None
        web = turn.metadata.get("web_search")
        return web if isinstance(web, dict) else None

    def _results_from_meta(self, web_meta: dict) -> tuple[str, list[SearchResult]]:
        query = str(web_meta.get("query", "")).strip()
        raw_results = web_meta.get("results") or []
        results: list[SearchResult] = []
        if isinstance(raw_results, list):
            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                if url.startswith("http") and title:
                    results.append(
                        SearchResult(
                            title=title,
                            url=url,
                            snippet=str(item.get("snippet", "")).strip(),
                        )
                    )
        return query, results

    def _resolve_search_for_turn(
        self,
        prefix: list[ChatTurn],
        turn: ChatTurn,
    ) -> tuple[str, list[SearchResult]] | None:
        web_meta = self._turn_web_search_meta(turn)
        if web_meta:
            query, results = self._results_from_meta(web_meta)
            if query and results:
                return query, results

        if not self.fine_tune.enrich_from_web:
            return None

        draft = [ChatTurn(role=t.role, content=t.content) for t in prefix]  # type: ignore[arg-type]
        query: str | None = None
        if self.search_client is not None:
            query = decide_search(self.search_client, draft)
        if not query:
            return None
        try:
            results = search_web(query, self.web_search_config)
        except SearchError:
            return None
        if not results:
            return None
        return query, results

    def _web_enrichment_blocks(
        self,
        query: str,
        results: list[SearchResult],
    ) -> tuple[str, list[SFTExample]]:
        """Build injected context and optional standalone page training rows."""
        blocks = [format_results_block(query, results)]
        page_examples: list[SFTExample] = []

        if not self.fine_tune.fetch_search_pages:
            return "\n\n".join(blocks), page_examples

        for result in results[: self.fine_tune.max_pages_per_query]:
            page_text = fetch_page_content(result.url, firecrawl=self.firecrawl_config)
            if not page_text:
                continue
            blocks.append(format_page_content_block(result.title, result.url, page_text))
            system = self.context_builder.build_system_prompt(user_query=query)
            page_examples.append(
                SFTExample(
                    messages=[
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": f"What does the web say about: {query}?",
                        },
                        {
                            "role": "assistant",
                            "content": (
                                f"From {result.title} ({result.url}):\n\n{page_text[:3500]}"
                            ),
                        },
                    ],
                    memory_context=self.context_builder.build_memory_context_dict(query),
                    metadata={
                        "task": "personal_assistant",
                        "subtype": "web_page",
                        "query": query,
                        "url": result.url,
                        "title": result.title,
                    },
                )
            )

        return "\n\n".join(blocks), page_examples

    def chat_examples_from_session(self, session: ChatSession) -> tuple[list[SFTExample], list[SFTExample]]:
        """One SFT row per assistant turn; optional web page rows."""
        turns = [t for t in session.turns if t.role in ("user", "assistant") and t.content.strip()]
        chat_examples: list[SFTExample] = []
        web_examples: list[SFTExample] = []
        source = session.metadata.get("source", "ui")

        for index, turn in enumerate(turns):
            if turn.role != "assistant":
                continue
            prefix = turns[: index + 1]
            last_user = next((t.content for t in reversed(prefix) if t.role == "user"), None)
            if not last_user:
                continue

            stored_context = None
            if isinstance(turn.metadata, dict):
                stored_context = turn.metadata.get("memory_context")

            memory_context = (
                stored_context
                if isinstance(stored_context, dict)
                else self.context_builder.build_memory_context_dict(last_user)
            )
            system = self.context_builder.build_system_prompt(user_query=last_user)

            search = self._resolve_search_for_turn(prefix, turn)
            if search:
                query, results = search
                web_block, page_rows = self._web_enrichment_blocks(query, results)
                system = f"{system}\n\n{web_block}"
                web_examples.extend(page_rows)

            messages: list[dict[str, str]] = [{"role": "system", "content": system}]
            for t in prefix:
                messages.append({"role": t.role, "content": t.content})

            meta: dict = {
                "session_id": session.id,
                "turn_index": index,
                "source": source,
                "task": "personal_assistant",
                "subtype": "chat_turn",
            }
            if search:
                meta["web_query"] = search[0]

            chat_examples.append(
                SFTExample(
                    messages=messages,
                    memory_context=memory_context,
                    metadata=meta,
                )
            )

        return chat_examples, web_examples

    def build_sft_examples(self) -> tuple[list[SFTExample], SftExportStats]:
        chat_examples: list[SFTExample] = []
        web_examples: list[SFTExample] = []
        counts = {"ui": 0, "agent": 0}
        total_sessions = 0

        if self.fine_tune.include_chats:
            sessions, counts = self.collect_chat_sessions()
            total_sessions = len(sessions)
            for session in sessions:
                chat_rows, page_rows = self.chat_examples_from_session(session)
                chat_examples.extend(chat_rows)
                web_examples.extend(page_rows)

        memory_examples = self._memory_qa_examples()
        book_examples = self._books_qa_examples()
        all_examples = [*chat_examples, *web_examples, *memory_examples, *book_examples]
        stats = SftExportStats(
            ui_sessions=counts["ui"],
            agent_sessions=counts["agent"],
            total_sessions=total_sessions,
            chat_examples=len(chat_examples),
            memory_examples=len(memory_examples),
            book_examples=len(book_examples),
            web_examples=len(web_examples),
            total_examples=len(all_examples),
            include_chats=self.fine_tune.include_chats,
            enrich_from_web=self.fine_tune.enrich_from_web,
            fetch_search_pages=self.fine_tune.fetch_search_pages,
        )
        return all_examples, stats

    def _assistant_turn_count(self, session: ChatSession) -> int:
        return sum(
            1
            for turn in session.turns
            if turn.role == "assistant" and turn.content.strip()
        )

    def _stored_web_example_count(self, session: ChatSession) -> int:
        if not self.fine_tune.fetch_search_pages:
            return 0
        count = 0
        for turn in session.turns:
            if turn.role != "assistant":
                continue
            web_meta = self._turn_web_search_meta(turn)
            if not web_meta:
                continue
            _, results = self._results_from_meta(web_meta)
            if results:
                count += min(len(results), self.fine_tune.max_pages_per_query)
        return count

    def _book_example_count(self) -> int:
        if self.books is None:
            return 0
        entries = self.books.load()
        if not entries:
            return 0
        count = len(entries)
        count += sum(1 for book in entries if book.notes)
        count += 1
        return count

    def sft_preview(self) -> SftExportStats:
        """Fast counts for UI status — no live web search or page fetches."""
        chat_examples = 0
        web_examples = 0
        counts = {"ui": 0, "agent": 0}
        total_sessions = 0

        if self.fine_tune.include_chats:
            sessions, counts = self.collect_chat_sessions()
            total_sessions = len(sessions)
            for session in sessions:
                chat_examples += self._assistant_turn_count(session)
                web_examples += self._stored_web_example_count(session)

        memory_examples = len(self.store.load_profile())
        book_examples = self._book_example_count()
        total_examples = chat_examples + web_examples + memory_examples + book_examples
        return SftExportStats(
            ui_sessions=counts["ui"],
            agent_sessions=counts["agent"],
            total_sessions=total_sessions,
            chat_examples=chat_examples,
            memory_examples=memory_examples,
            book_examples=book_examples,
            web_examples=web_examples,
            total_examples=total_examples,
            include_chats=self.fine_tune.include_chats,
            enrich_from_web=self.fine_tune.enrich_from_web,
            fetch_search_pages=self.fine_tune.fetch_search_pages,
        )

    def export_sft(self, output_name: str = "pa_sft.jsonl") -> Path:
        out_path = self.export_dir / output_name
        examples, _stats = self.build_sft_examples()
        with out_path.open("w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex.model_dump(mode="json")) + "\n")
        return out_path

    def _memory_qa_examples(self) -> list[SFTExample]:
        """Generate simple recall examples from profile entries."""
        examples: list[SFTExample] = []
        for entry in self.store.load_profile():
            system = self.context_builder.build_system_prompt()
            user_q = f"What do you know about my {entry.key.replace('_', ' ')}?"
            assistant_a = entry.value
            examples.append(
                SFTExample(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_q},
                        {"role": "assistant", "content": assistant_a},
                    ],
                    memory_context=self.context_builder.build_memory_context_dict(user_q),
                    metadata={"task": "personal_assistant", "subtype": "profile_recall"},
                )
            )
        return examples

    def _books_qa_examples(self) -> list[SFTExample]:
        """Generate recall examples so the model knows which books the user read."""
        if self.books is None:
            return []
        entries = self.books.load()
        if not entries:
            return []

        system = self.context_builder.build_system_prompt()
        examples: list[SFTExample] = []

        def _example(user_q: str, assistant_a: str, subtype: str) -> SFTExample:
            return SFTExample(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_q},
                    {"role": "assistant", "content": assistant_a},
                ],
                memory_context=self.context_builder.build_memory_context_dict(user_q),
                metadata={"task": "personal_assistant", "subtype": subtype},
            )

        for book in entries:
            examples.append(
                _example(
                    f"Have I read '{book.title}'?",
                    f"Yes — {book_episode_summary(book)}",
                    "book_recall",
                )
            )
            if book.notes:
                by = f" by {book.author}" if book.author else ""
                examples.append(
                    _example(
                        f"What did I take away from '{book.title}'{by}?",
                        book.notes,
                        "book_takeaway",
                    )
                )

        examples.append(
            _example(
                "What books have I read?",
                "You've read:\n" + "\n".join(f"- {self._book_line(b)}" for b in entries),
                "book_list",
            )
        )
        return examples

    @staticmethod
    def _book_line(book: BookEntry) -> str:
        line = book.title
        if book.author:
            line += f" — {book.author}"
        if book.rating:
            line += f" ({book.rating}/5)"
        return line

    def export_dpo(self, output_name: str = "pa_dpo.jsonl") -> Path:
        out_path = self.export_dir / output_name
        dpo_source = self.export_dir.parent / "dpo"
        lines: list[str] = []
        if dpo_source.exists():
            for path in sorted(dpo_source.glob("*.jsonl")):
                lines.extend(path.read_text(encoding="utf-8").splitlines())
        out_path.write_text(
            "\n".join(line for line in lines if line.strip()) + ("\n" if lines else ""),
            encoding="utf-8",
        )
        return out_path

    def export_memory_snapshot(self, output_name: str = "memory_snapshot.json") -> Path:
        out_path = self.export_dir / output_name
        out_path.write_text(json.dumps(self.store.snapshot(), indent=2), encoding="utf-8")
        return out_path
