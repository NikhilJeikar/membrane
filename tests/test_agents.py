"""Tests for multi-agent transcript ingest."""

import json
from pathlib import Path

from membrane.ingest.agents.registry import detect_provider, get_adapter, list_providers
from membrane.ingest.agents.ingest import ingest_agent_path


SAMPLE_CURSOR = "\n".join(
    [
        json.dumps(
            {
                "role": "user",
                "message": {"content": [{"type": "text", "text": "<user_query>Hello</user_query>"}]},
            }
        ),
        json.dumps(
            {
                "role": "assistant",
                "message": {"content": [{"type": "text", "text": "Hi there, how can I help you today?"}]},
            }
        ),
    ]
)

SAMPLE_CLAUDE = "\n".join(
    [
        json.dumps(
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "Build a memory system"}]},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Here is a plan for structured memory with review workflow."}]},
            }
        ),
    ]
)

SAMPLE_OPENAI = "\n".join(
    [
        json.dumps({"role": "user", "content": "Summarize this document please"}),
        json.dumps({"role": "assistant", "content": "This document covers local-first personal assistant design."}),
    ]
)


def test_list_providers():
    assert "cursor" in list_providers()
    assert "claude" in list_providers()
    assert "openai" in list_providers()


def test_detect_cursor_format(tmp_path: Path):
    path = tmp_path / "sess.jsonl"
    path.write_text(SAMPLE_CURSOR, encoding="utf-8")
    assert detect_provider(path) == "cursor"


def test_detect_claude_format(tmp_path: Path):
    path = tmp_path / "sess.jsonl"
    path.write_text(SAMPLE_CLAUDE, encoding="utf-8")
    assert detect_provider(path) == "claude"


def test_detect_openai_format(tmp_path: Path):
    path = tmp_path / "sess.jsonl"
    path.write_text(SAMPLE_OPENAI, encoding="utf-8")
    assert detect_provider(path) == "openai"


def test_parse_claude_transcript(tmp_path: Path):
    path = tmp_path / "abc.jsonl"
    path.write_text(SAMPLE_CLAUDE, encoding="utf-8")
    session = get_adapter("claude").parse(path, redact=False)
    assert session.agent == "claude"
    assert len(session.turns) == 2
    assert "memory" in session.turns[0].content.lower()


def test_ingest_agent_auto_routes_by_provider(tmp_path: Path):
    from membrane.config import Settings

    settings = Settings(root=tmp_path)
    root = tmp_path / "transcripts"
    root.mkdir()
    (root / "cursor.jsonl").write_text(SAMPLE_CURSOR, encoding="utf-8")
    (root / "claude.jsonl").write_text(SAMPLE_CLAUDE, encoding="utf-8")

    stats = ingest_agent_path(root, provider="auto", settings=settings, redact=False)
    assert stats.processed == 2
    assert (settings.agent_parsed_dir("cursor") / "cursor.jsonl").exists()
    assert (settings.agent_parsed_dir("claude") / "claude.jsonl").exists()
