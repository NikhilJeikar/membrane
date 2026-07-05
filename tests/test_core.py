"""Tests for shadow-pa."""

import json
from pathlib import Path

from shadow_pa.config import ensure_data_layout
from shadow_pa.ingest.cursor import format_cursor_chunk_for_extraction, parse_cursor_transcript
from shadow_pa.ingest.whatsapp import parse_whatsapp_export
from shadow_pa.ingest.wikipedia import WikipediaArticle, build_summarization_corpus
from shadow_pa.memory.models import MemoryCategory, MemoryProposal, ProfileEntry
from shadow_pa.memory.store import MemoryStore
from shadow_pa.utils.redact import redact_text


SAMPLE_EXPORT = """[05/07/2026, 10:32:15] Nikhil: Can we move gym to Tue/Thu?
[05/07/2026, 10:33:01] Friend: Sure, works for me
[05/07/2026, 10:34:00] Nikhil: Thanks!
"""

SAMPLE_CURSOR = "\n".join(
    [
        json.dumps(
            {
                "role": "user",
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": "<timestamp>Sunday</timestamp>\n<user_query>\nBuild a PA with memory\n</user_query>",
                        }
                    ]
                },
            }
        ),
        json.dumps(
            {
                "role": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Here is a plan for your personal assistant with memory."},
                        {"type": "tool_use", "name": "Grep", "input": {}},
                    ]
                },
            }
        ),
    ]
)


def test_parse_whatsapp_export():
    messages = parse_whatsapp_export(SAMPLE_EXPORT, self_names=["Nikhil"], redact=False)
    assert len(messages) == 3
    assert messages[0].is_self is True
    assert messages[1].is_self is False
    assert "gym" in messages[0].text


def test_parse_cursor_transcript(tmp_path: Path):
    path = tmp_path / "abc123.jsonl"
    path.write_text(SAMPLE_CURSOR, encoding="utf-8")
    session = parse_cursor_transcript(path, redact=False)
    assert session.session_id == "abc123"
    assert len(session.turns) == 2
    assert session.turns[0].role == "user"
    assert "PA with memory" in session.turns[0].content
    assert session.turns[1].role == "assistant"
    chunk_text = format_cursor_chunk_for_extraction(session.turns)
    assert "SELF" in chunk_text


def test_redact_phone():
    text = redact_text("Call me at +91 9876543210 please")
    assert "[PHONE]" in text
    assert "9876543210" not in text


def test_memory_store_propose_approve(tmp_path: Path):
    store = MemoryStore(tmp_path)
    profile = ProfileEntry(key="gym_schedule", value="Tue/Thu")
    proposal = MemoryProposal(
        category=MemoryCategory.PROFILE,
        profile=profile,
        reason="test",
    )
    store.propose(proposal)
    pending = store.list_proposed()
    assert len(pending) == 1
    store.approve(pending[0].id)
    profiles = store.load_profile()
    assert len(profiles) == 1
    assert profiles[0].key == "gym_schedule"


def test_ensure_data_layout(tmp_path: Path):
    ensure_data_layout(tmp_path)
    assert (tmp_path / "data" / "whatsapp" / "raw").is_dir()
    assert (tmp_path / "data" / "cursor" / "parsed").is_dir()
    assert (tmp_path / "data" / "corpus" / "wiki" / "raw").is_dir()


def test_build_summarization_corpus():
    article = WikipediaArticle(title="Test", text="Paragraph one.\n\nParagraph two is longer.", lang="en")
    examples = build_summarization_corpus([article], include_lead_summary=True)
    assert len(examples) == 1
    assert examples[0].metadata["task"] == "summarization"
    assert examples[0].metadata["labeled"] is True


def test_offline_extract_cursor(tmp_path: Path):
    from shadow_pa.shadow.offline import offline_extract_cursor_file

    parsed = tmp_path / "sess1.jsonl"
    parsed.write_text(
        json.dumps(
            {
                "role": "user",
                "content": "I want distillation and summarization with python on Fedora",
                "session_id": "sess1",
                "source_file": "sess1.jsonl",
                "turn_index": 0,
                "has_tool_calls": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    meta = tmp_path / "sess1.meta.json"
    meta.write_text(json.dumps({"workspace_hint": "shadow-pa"}), encoding="utf-8")
    proposals = offline_extract_cursor_file(parsed, tmp_path)
    assert any(p.profile and p.profile.key == "cursor_project" for p in proposals)
    assert any(p.category.value == "episode" for p in proposals)
