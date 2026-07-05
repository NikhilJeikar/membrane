"""Tests for SFT export from chat sessions."""

import json

from membrane.config import PersonaConfig, Settings
from membrane.inference.context import ContextBuilder
from membrane.learning.export import TrainingExporter
from membrane.memory.models import ChatSession, ChatTurn
from membrane.memory.store import MemoryStore


def _write_session(chats_dir, session: ChatSession) -> None:
    path = chats_dir / f"{session.id}.json"
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")


def test_export_sft_one_row_per_assistant_turn(tmp_path):
    memory = MemoryStore(tmp_path / "memory")
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    session = ChatSession(
        id="s1",
        turns=[
            ChatTurn(role="user", content="Hi"),
            ChatTurn(role="assistant", content="Hello!"),
            ChatTurn(role="user", content="What's my focus?"),
            ChatTurn(
                role="assistant",
                content="Deep work blocks.",
                metadata={"memory_context": {"profile": [], "preferences": [], "episodes": []}},
            ),
        ],
    )
    _write_session(chats_dir, session)

    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=chats_dir,
        export_dir=tmp_path / "export",
    )
    out = exporter.export_sft()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    chat_rows = [r for r in rows if r["metadata"].get("subtype") == "chat_turn"]
    assert len(chat_rows) == 2
    assert chat_rows[0]["messages"][0]["role"] == "system"
    assert chat_rows[0]["messages"][-1]["content"] == "Hello!"
    assert chat_rows[1]["messages"][-1]["content"] == "Deep work blocks."
    assert chat_rows[1]["memory_context"] == {"profile": [], "preferences": [], "episodes": []}


def test_export_sft_includes_agent_sessions(tmp_path):
    memory = MemoryStore(tmp_path / "memory")
    settings = Settings(root=tmp_path)
    parsed = settings.agent_parsed_dir("cursor")
    parsed.mkdir(parents=True)
    (parsed / "sess1.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "role": "user",
                        "content": "Fix the bug",
                        "session_id": "sess1",
                        "source_file": "x.jsonl",
                        "turn_index": 0,
                        "agent": "cursor",
                    }
                ),
                json.dumps(
                    {
                        "role": "assistant",
                        "content": "Applied the patch.",
                        "session_id": "sess1",
                        "source_file": "x.jsonl",
                        "turn_index": 1,
                        "agent": "cursor",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=tmp_path / "chats",
        export_dir=tmp_path / "export",
        settings=settings,
    )
    stats = exporter.sft_preview()
    assert stats.agent_sessions == 1
    assert stats.chat_examples == 1

    out = exporter.export_sft()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    agent_rows = [r for r in rows if r["metadata"].get("source") == "cursor"]
    assert len(agent_rows) == 1
    assert agent_rows[0]["messages"][0]["role"] == "system"


def test_export_sft_dedupes_synced_agent_chats(tmp_path):
    memory = MemoryStore(tmp_path / "memory")
    settings = Settings(root=tmp_path)
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()

    parsed = settings.agent_parsed_dir("cursor")
    parsed.mkdir(parents=True)
    (parsed / "sess1.jsonl").write_text(
        json.dumps(
            {
                "role": "user",
                "content": "Hello",
                "session_id": "sess1",
                "source_file": "x.jsonl",
                "turn_index": 0,
                "agent": "cursor",
            }
        )
        + "\n"
        + json.dumps(
            {
                "role": "assistant",
                "content": "Hi there",
                "session_id": "sess1",
                "source_file": "x.jsonl",
                "turn_index": 1,
                "agent": "cursor",
            }
        ),
        encoding="utf-8",
    )

    _write_session(
        chats_dir,
        ChatSession(
            id="cursor-sess1",
            turns=[
                ChatTurn(role="user", content="Hello"),
                ChatTurn(role="assistant", content="Hi there"),
            ],
            metadata={"source": "cursor", "session_id": "sess1"},
        ),
    )

    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=chats_dir,
        export_dir=tmp_path / "export",
        settings=settings,
    )
    stats = exporter.sft_preview()
    assert stats.total_sessions == 1
    assert stats.chat_examples == 1


def test_export_sft_exclude_chats(tmp_path):
    memory = MemoryStore(tmp_path / "memory")
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    _write_session(
        chats_dir,
        ChatSession(
            id="s1",
            turns=[
                ChatTurn(role="user", content="Hi"),
                ChatTurn(role="assistant", content="Hello!"),
            ],
        ),
    )

    from membrane.config_integrations import FineTuneConfig

    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=chats_dir,
        export_dir=tmp_path / "export",
        fine_tune=FineTuneConfig(include_chats=False),
    )
    stats = exporter.sft_preview()
    assert stats.chat_examples == 0
    assert stats.include_chats is False


def test_export_sft_web_search_pages(tmp_path, monkeypatch):
    memory = MemoryStore(tmp_path / "memory")
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    session = ChatSession(
        id="s1",
        turns=[
            ChatTurn(role="user", content="What's new in Python?"),
            ChatTurn(
                role="assistant",
                content="Python 3.13 added improvements.",
                metadata={
                    "web_search": {
                        "query": "python 3.13 release",
                        "results": [
                            {
                                "title": "Python 3.13",
                                "url": "https://example.com/python",
                                "snippet": "Released.",
                            }
                        ],
                    }
                },
            ),
        ],
    )
    _write_session(chats_dir, session)

    monkeypatch.setattr(
        "membrane.learning.export.fetch_page_content",
        lambda url, **kwargs: "Detailed release notes from the page.",
    )

    from membrane.config_integrations import FineTuneConfig

    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=chats_dir,
        export_dir=tmp_path / "export",
        fine_tune=FineTuneConfig(include_chats=True, fetch_search_pages=True),
    )
    stats = exporter.sft_preview()
    assert stats.chat_examples == 1
    assert stats.web_examples == 1

    out = exporter.export_sft()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    chat_row = next(r for r in rows if r["metadata"].get("subtype") == "chat_turn")
    assert "[WEB SEARCH RESULTS]" in chat_row["messages"][0]["content"]
    assert "[WEB PAGE CONTENT]" in chat_row["messages"][0]["content"]
    web_row = next(r for r in rows if r["metadata"].get("subtype") == "web_page")
    assert "Detailed release notes" in web_row["messages"][2]["content"]


def test_export_sft_respects_per_chat_opt_out(tmp_path):
    memory = MemoryStore(tmp_path / "memory")
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    _write_session(
        chats_dir,
        ChatSession(
            id="included",
            turns=[
                ChatTurn(role="user", content="Hi"),
                ChatTurn(role="assistant", content="Hello!"),
            ],
        ),
    )
    _write_session(
        chats_dir,
        ChatSession(
            id="excluded",
            metadata={"include_in_training": False},
            turns=[
                ChatTurn(role="user", content="Secret"),
                ChatTurn(role="assistant", content="Private."),
            ],
        ),
    )

    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=chats_dir,
        export_dir=tmp_path / "export",
    )
    stats = exporter.sft_preview()
    assert stats.total_sessions == 1
    assert stats.chat_examples == 1


def test_sft_preview_skips_live_web_enrichment(tmp_path, monkeypatch):
    memory = MemoryStore(tmp_path / "memory")
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir()
    _write_session(
        chats_dir,
        ChatSession(
            id="s1",
            turns=[
                ChatTurn(role="user", content="What is new in Python 3.13?"),
                ChatTurn(role="assistant", content="Python 3.13 added improved typing."),
            ],
        ),
    )

    def _should_not_run(*_args, **_kwargs):
        raise AssertionError("decide_search must not run during sft_preview")

    monkeypatch.setattr("membrane.learning.export.decide_search", _should_not_run)
    monkeypatch.setattr(
        "membrane.learning.export.fetch_page_content",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("fetch_page_content must not run during sft_preview")
        ),
    )

    from membrane.config_integrations import FineTuneConfig

    exporter = TrainingExporter(
        store=memory,
        context_builder=ContextBuilder(memory, PersonaConfig()),
        chats_dir=chats_dir,
        export_dir=tmp_path / "export",
        fine_tune=FineTuneConfig(
            include_chats=True,
            enrich_from_web=True,
            fetch_search_pages=True,
        ),
    )
    stats = exporter.sft_preview()
    assert stats.chat_examples == 1
    assert stats.web_examples == 0
