"""Tests for conversation context building."""

from membrane.config import PersonaConfig, StyleConfig, WebSearchConfig
from membrane.inference.context import ContextBuilder
from membrane.memory.models import ChatTurn
from membrane.memory.store import MemoryStore


def test_build_conversation_messages_includes_history(tmp_path):
    store = MemoryStore(tmp_path)
    builder = ContextBuilder(store, PersonaConfig())
    turns = [
        ChatTurn(role="user", content="First question"),
        ChatTurn(role="assistant", content="First answer"),
        ChatTurn(role="user", content="Follow up"),
    ]
    messages = builder.build_conversation_messages(turns)
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "Follow up"
    assert len(messages) == 4


def test_system_prompt_links_chat_user_to_profile(tmp_path):
    persona = PersonaConfig(
        self_names=["Nikhil", "You"],
        identity={"name": "Nikhil's assistant", "timezone": "Asia/Kolkata"},
    )
    builder = ContextBuilder(MemoryStore(tmp_path), persona)
    prompt = builder.build_system_prompt()

    assert "The person chatting with you is Nikhil" in prompt
    assert "also: You" in prompt
    assert "Every message labeled 'user'" in prompt
    assert "describe this same person" in prompt
    assert "[ASSISTANT IDENTITY]" in prompt
    assert "Nikhil's assistant" in prompt


def test_system_prompt_memory_growth(tmp_path):
    builder = ContextBuilder(MemoryStore(tmp_path), PersonaConfig())
    prompt = builder.build_system_prompt()
    assert "[MEMORY GROWTH]" in prompt
    assert "broaden what you know" in prompt
    assert "stronger, more personalized" in prompt


def test_system_prompt_independent_opinions(tmp_path):
    enabled = ContextBuilder(
        MemoryStore(tmp_path),
        PersonaConfig(style=StyleConfig(independent_opinions=True)),
    )
    prompt = enabled.build_system_prompt()
    assert "share your honest view" in prompt
    assert "respectfully disagree" in prompt

    disabled = ContextBuilder(
        MemoryStore(tmp_path),
        PersonaConfig(style=StyleConfig(independent_opinions=False)),
    )
    assert "avoid unnecessary disagreement" in disabled.build_system_prompt()


def test_estimate_context_usage_counts_tokens(tmp_path):
    store = MemoryStore(tmp_path)
    builder = ContextBuilder(store, PersonaConfig())
    turns = [
        ChatTurn(role="user", content="Hello " * 20),
        ChatTurn(role="assistant", content="Hi " * 20),
    ]
    usage = builder.estimate_context_usage(turns)
    assert usage["estimated_tokens"] > 0
    assert usage["context_limit"] == 8192
    assert usage["remaining_tokens"] <= usage["context_limit"]
    assert 0 <= usage["usage_percent"] <= 100
    assert usage["system_tokens"] == usage["system_base_tokens"] + usage["memory_tokens"]
    assert usage["tools_tokens"] == 0
    assert usage["tools_breakdown"] == {}


def test_estimate_context_usage_includes_tools_breakdown(tmp_path):
    store = MemoryStore(tmp_path)
    persona = PersonaConfig(web_search=WebSearchConfig(enabled=True))
    builder = ContextBuilder(store, persona)
    turns = [
        ChatTurn(role="user", content="What is the news?"),
        ChatTurn(
            role="assistant",
            content="Here is what I found.",
            metadata={
                "web_search": {
                    "query": "news today",
                    "results": [],
                    "content_chars": 800,
                    "tool_tokens": {"web_search": 200, "firecrawl": 400},
                }
            },
        ),
    ]
    usage = builder.estimate_context_usage(turns, draft_user="Follow up question")
    assert usage["tools_tokens"] == 600
    assert usage["tools_breakdown"] == {"web_search": 200, "firecrawl": 400}
    assert usage["estimated_tokens"] >= usage["tools_tokens"]


def test_estimate_context_usage_includes_reasoning_tokens(tmp_path):
    store = MemoryStore(tmp_path)
    builder = ContextBuilder(store, PersonaConfig())
    turns = [
        ChatTurn(role="user", content="Solve this"),
        ChatTurn(
            role="assistant",
            content="The answer is 4.",
            metadata={"thinking": "x" * 400},
        ),
    ]
    usage = builder.estimate_context_usage(turns)
    assert usage["reasoning_tokens"] == 100
    assert usage["estimated_tokens"] >= usage["reasoning_tokens"]


def test_estimate_context_usage_accepts_explicit_tools(tmp_path):
    store = MemoryStore(tmp_path)
    builder = ContextBuilder(store, PersonaConfig())
    usage = builder.estimate_context_usage(
        [],
        draft_user="Hello",
        tools_breakdown={"web_search": 150, "firecrawl": 50},
    )
    assert usage["tools_tokens"] == 200
    assert usage["tools_breakdown"] == {"web_search": 150, "firecrawl": 50}
