"""Tests for Ollama client helpers."""

from membrane.config import LLMConfig
from membrane.llm.ollama import OllamaClient, OllamaModelNotFoundError


def test_has_model_matches_tag_variants(monkeypatch):
    client = OllamaClient(LLMConfig(model="qwen2.5:7b"))

    monkeypatch.setattr(client, "list_models", lambda: ["qwen2.5:3b", "llama3:8b"])
    assert client.has_model("qwen2.5:7b") is False
    assert client.has_model("qwen2.5:3b") is True
    assert client.has_model("llama3") is True
    assert client.has_model("llama3:8b") is True


def test_raise_for_response_maps_missing_model():
    import httpx

    client = OllamaClient(LLMConfig())
    response = httpx.Response(404, json={"error": "model 'foo' not found"})
    try:
        client._raise_for_response(response, "foo")
        raise AssertionError("expected OllamaModelNotFoundError")
    except OllamaModelNotFoundError as exc:
        assert "ollama pull foo" in str(exc)


def test_chat_stream_yields_chunks(monkeypatch):
    import json

    import httpx

    ndjson = "\n".join(
        [
            json.dumps({"message": {"content": "Hel"}, "done": False}),
            json.dumps({"message": {"content": "lo"}, "done": True}),
        ]
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=ndjson))
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda timeout=None: real_client(transport=transport, timeout=timeout),
    )

    client = OllamaClient(LLMConfig())
    chunks = list(client.chat_stream([{"role": "user", "content": "hi"}]))
    assert chunks == ["Hel", "lo"]
