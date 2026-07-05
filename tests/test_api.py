"""Tests for control UI API."""

import pytest
from fastapi.testclient import TestClient

from membrane.api.app import create_app
from membrane.config import Settings
from membrane.config_store import reset_config_store


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    settings = Settings(root=tmp_path)
    settings.memory_dir.mkdir(parents=True, exist_ok=True)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    reset_config_store()
    monkeypatch.setattr("membrane.api.app.get_settings", lambda: settings)
    monkeypatch.setattr("membrane.config.get_settings", lambda: settings)
    monkeypatch.setattr("membrane.config_store.get_settings", lambda: settings)
    return TestClient(create_app())


def test_api_status(api_client):
    res = api_client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "pending_proposals" in data
    assert "ollama_ok" in data


def test_api_policy_roundtrip(api_client):
    res = api_client.get("/api/policy")
    assert res.status_code == 200
    policy = res.json()
    policy["phase"] = "review"
    res2 = api_client.put("/api/policy", json=policy)
    assert res2.status_code == 200


def test_api_policy_nightly_schedule(api_client):
    policy = api_client.get("/api/policy").json()
    assert policy["nightly"]["time"] == "02:00"

    policy["nightly"] = {"enabled": True, "time": "23:30", "since_hours": 48}
    res = api_client.put("/api/policy", json=policy)
    assert res.status_code == 200

    saved = api_client.get("/api/policy").json()
    assert saved["nightly"] == {"enabled": True, "time": "23:30", "since_hours": 48}

    policy["nightly"]["time"] = "25:00"
    res = api_client.put("/api/policy", json=policy)
    assert res.status_code == 422


def test_api_proposed_list(api_client):
    res = api_client.get("/api/memory/proposed?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data


def test_api_profile_crud(api_client):
    res = api_client.post(
        "/api/memory/profile",
        json={"key": "location", "value": "Bangalore", "confidence": 0.9},
    )
    assert res.status_code == 200
    entry = res.json()
    assert entry["key"] == "location"
    assert entry["value"] == "Bangalore"
    assert entry["source"] == "manual"

    snap = api_client.get("/api/memory/snapshot").json()
    assert len(snap["profile"]) == 1

    res2 = api_client.post(
        "/api/memory/profile",
        json={"key": "location", "value": "Mumbai", "confidence": 0.95},
    )
    assert res2.status_code == 200
    assert res2.json()["value"] == "Mumbai"

    res3 = api_client.delete("/api/memory/profile/location")
    assert res3.status_code == 200
    assert api_client.get("/api/memory/snapshot").json()["profile"] == []


def test_api_preference_crud(api_client):
    res = api_client.post(
        "/api/memory/preferences",
        json={"key": "tone", "value": "concise", "strength": 0.8},
    )
    assert res.status_code == 200
    entry = res.json()
    assert entry["key"] == "tone"
    assert entry["source"] == "manual"

    snap = api_client.get("/api/memory/snapshot").json()
    assert len(snap["preferences"]) == 1

    res2 = api_client.delete("/api/memory/preferences/tone")
    assert res2.status_code == 200
    assert api_client.get("/api/memory/snapshot").json()["preferences"] == []


def test_api_profile_delete_missing(api_client):
    res = api_client.delete("/api/memory/profile/missing")
    assert res.status_code == 404


def test_spa_fallback_serves_index(tmp_path):
    ui_dist = tmp_path / "ui"
    ui_dist.mkdir()
    (ui_dist / "index.html").write_text("<html>membrane</html>", encoding="utf-8")
    assets = ui_dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")

    client = TestClient(create_app(ui_dist))
    assert client.get("/ingest").status_code == 200
    assert "membrane" in client.get("/ingest").text
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/api/status").status_code == 200


def test_api_ingest_stats_includes_queue(api_client):
    res = api_client.get("/api/ingest/stats")
    assert res.status_code == 200
    data = res.json()
    assert "sources" in data
    assert "totals" in data
    assert "needs_parse" in data["totals"]
    assert "needs_extract" in data["totals"]
    assert "needs_train" in data["totals"]


def test_api_persona_roundtrip(api_client):
    res = api_client.get("/api/persona")
    assert res.status_code == 200
    persona = res.json()
    assert "llm" in persona

    persona["llm"]["model"] = "llama3:8b"
    persona["llm"]["extractor_model"] = "llama3:8b"
    res2 = api_client.put("/api/persona", json={"llm": persona["llm"]})
    assert res2.status_code == 200
    assert res2.json()["llm"]["model"] == "llama3:8b"


def test_api_books_crud_syncs_episodes(api_client):
    res = api_client.post(
        "/api/books",
        json={"title": "Deep Work", "author": "Cal Newport", "rating": 5, "notes": "Focus wins."},
    )
    assert res.status_code == 200
    book = res.json()
    assert book["title"] == "Deep Work"
    assert book["episode_id"]

    episodes = api_client.get("/api/memory/snapshot").json()["episodes"]
    assert len(episodes) == 1
    assert "Deep Work" in episodes[0]["summary"]
    assert "Cal Newport" in episodes[0]["summary"]

    res2 = api_client.put(
        f"/api/books/{book['id']}",
        json={"title": "Deep Work", "author": "Cal Newport", "rating": 4, "notes": "Still great."},
    )
    assert res2.status_code == 200
    assert res2.json()["rating"] == 4
    episodes = api_client.get("/api/memory/snapshot").json()["episodes"]
    assert len(episodes) == 1
    assert "4/5" in episodes[0]["summary"]

    listing = api_client.get("/api/books").json()
    assert len(listing["items"]) == 1

    res3 = api_client.delete(f"/api/books/{book['id']}")
    assert res3.status_code == 200
    assert api_client.get("/api/books").json()["items"] == []
    assert api_client.get("/api/memory/snapshot").json()["episodes"] == []


def test_api_books_validation(api_client):
    assert api_client.post("/api/books", json={"title": "  "}).status_code == 400
    assert api_client.post("/api/books", json={"title": "X", "rating": 9}).status_code == 400
    assert api_client.delete("/api/books/missing").status_code == 404


def test_api_persona_server_update(api_client):
    res = api_client.put(
        "/api/persona",
        json={"server": {"host": "0.0.0.0", "port": 9000, "token": "secret123"}},
    )
    assert res.status_code == 200
    server = res.json()["server"]
    assert server["host"] == "0.0.0.0"
    assert server["port"] == 9000
    assert server["token"] == "secret123"

    status = api_client.get("/api/server/status").json()
    assert status["host"] == "0.0.0.0"
    assert status["port"] == 9000
    assert status["token"] == "secret123"


def test_api_persona_server_update_rejects_invalid(api_client):
    res = api_client.put("/api/persona", json={"server": {"port": 99_999_999}})
    assert res.status_code == 400

    res2 = api_client.put("/api/persona", json={"server": {"parse_interval_seconds": 5}})
    assert res2.status_code == 400


def test_api_persona_web_search_toggle(api_client):
    persona = api_client.get("/api/persona").json()
    assert persona["web_search"]["enabled"] is False

    res = api_client.put("/api/persona", json={"web_search": {"enabled": True, "max_results": 3}})
    assert res.status_code == 200
    assert res.json()["web_search"]["enabled"] is True
    assert res.json()["web_search"]["max_results"] == 3

    invalid = api_client.put("/api/persona", json={"web_search": {"max_results": 50}})
    assert invalid.status_code == 400


def test_api_persona_extended_fields(api_client):
    res = api_client.put(
        "/api/persona",
        json={
            "memory": {"use_episodes": False, "max_episodes_in_context": 3},
            "style": {"format": "prose", "empathy_level": 0.8},
            "identity": {"name": "Test assistant", "timezone": "UTC"},
            "self_names": ["Nikhil", "You"],
            "web_search": {"timeout_seconds": 15},
            "llm": {"parallel_requests": 1, "context_window": 16384},
            "performance": {"workers": 2},
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["memory"]["use_episodes"] is False
    assert body["style"]["format"] == "prose"
    assert body["identity"]["name"] == "Test assistant"
    assert body["llm"]["parallel_requests"] == 1
    assert body["performance"]["workers"] == 2


def test_api_persona_firecrawl_toggle(api_client):
    res = api_client.put(
        "/api/persona",
        json={
            "firecrawl": {
                "enabled": True,
                "base_url": "http://127.0.0.1:3002",
                "scrape_in_chat": True,
                "max_pages_in_chat": 1,
            }
        },
    )
    assert res.status_code == 200
    firecrawl = res.json()["firecrawl"]
    assert firecrawl["enabled"] is True
    assert firecrawl["base_url"] == "http://127.0.0.1:3002"
    assert firecrawl["scrape_in_chat"] is True
    assert firecrawl["max_pages_in_chat"] == 1


def test_api_persona_shell_toggle(api_client):
    persona = api_client.get("/api/persona").json()
    assert persona["shell"]["enabled"] is False

    res = api_client.put(
        "/api/persona",
        json={"shell": {"enabled": True, "max_commands_per_turn": 3}},
    )
    assert res.status_code == 200
    shell = res.json()["shell"]
    assert shell["enabled"] is True
    assert shell["max_commands_per_turn"] == 3

    invalid = api_client.put("/api/persona", json={"shell": {"max_commands_per_turn": 50}})
    assert invalid.status_code == 400


def test_api_chat_web_search_injects_results(api_client, monkeypatch):
    import json as jsonlib

    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return True

        def chat_stream(self, messages):
            systems = [m["content"] for m in messages if m["role"] == "system"]
            assert any("[WEB SEARCH RESULTS]" in s for s in systems)
            yield "Fresh answer"

    from membrane.inference.websearch import SearchResult

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())
    monkeypatch.setattr("membrane.api.app.decide_search", lambda _c, _t: "latest python release")
    monkeypatch.setattr(
        "membrane.api.app.search_web",
        lambda _q, _cfg: [SearchResult(title="Python", url="https://python.org", snippet="3.14")],
    )

    api_client.put("/api/persona", json={"web_search": {"enabled": True}})
    session_id = api_client.post("/api/chat/sessions").json()["id"]
    msg = api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "what's the latest python release?"},
    )
    assert msg.status_code == 200
    lines = [jsonlib.loads(line) for line in msg.text.splitlines() if line.strip()]
    search_events = [line["web_search"] for line in lines if "web_search" in line]
    assert search_events[0] == {"status": "searching", "query": "latest python release"}
    assert search_events[1]["status"] == "done"
    assert search_events[1]["results"] == [{"title": "Python", "url": "https://python.org"}]
    assert lines[-1]["reply"] == "Fresh answer"
    assistant = [t for t in lines[-1]["session"]["turns"] if t["role"] == "assistant"][-1]
    assert assistant["metadata"]["web_search"]["query"] == "latest python release"
    assert assistant["metadata"]["web_search"]["results"][0]["title"] == "Python"
    assert "memory_context" in assistant["metadata"]


def test_api_chat_web_search_scrapes_pages_with_firecrawl(api_client, monkeypatch):
    import json as jsonlib

    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return True

        def chat_stream(self, messages):
            systems = [m["content"] for m in messages if m["role"] == "system"]
            assert any("[WEB PAGE CONTENT]" in s for s in systems)
            yield "Answer with page content"

    from membrane.inference.websearch import SearchResult

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())
    monkeypatch.setattr("membrane.api.app.decide_search", lambda _c, _t: "python docs")
    monkeypatch.setattr(
        "membrane.api.app.search_web",
        lambda _q, _cfg: [SearchResult(title="Docs", url="https://docs.python.org", snippet="")],
    )
    monkeypatch.setattr(
        "membrane.api.app.enrich_search_with_pages",
        lambda results, cfg: "[WEB PAGE CONTENT]\nSource: Docs\nURL: https://docs.python.org\n\nPage body",
    )

    api_client.put(
        "/api/persona",
        json={
            "web_search": {"enabled": True},
            "firecrawl": {"enabled": True, "scrape_in_chat": True, "max_pages_in_chat": 1},
        },
    )
    session_id = api_client.post("/api/chat/sessions").json()["id"]
    msg = api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "summarize python docs"},
    )
    assert msg.status_code == 200
    lines = [jsonlib.loads(line) for line in msg.text.splitlines() if line.strip()]
    assert lines[-1]["reply"] == "Answer with page content"


def test_api_chat_stream_includes_context(api_client, monkeypatch):
    import json as jsonlib

    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return True

        def chat_stream(self, _messages):
            yield "Hi"

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())
    monkeypatch.setattr("membrane.api.app.decide_search", lambda _c, _t: None)

    api_client.post("/api/memory/profile", json={"key": "city", "value": "Bangalore"})
    session_id = api_client.post("/api/chat/sessions").json()["id"]
    msg = api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "where do I live?"},
    )
    lines = [jsonlib.loads(line) for line in msg.text.splitlines() if line.strip()]
    assert "context" in lines[0]
    assert lines[0]["context"]["profile"][0]["value"] == "Bangalore"
    assistant = [t for t in lines[-1]["session"]["turns"] if t["role"] == "assistant"][-1]
    assert assistant["metadata"]["memory_context"]["profile"][0]["key"] == "city"


def test_api_chat_web_search_disabled_skips_search(api_client, monkeypatch):
    import json as jsonlib

    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return True

        def chat_stream(self, messages):
            assert not any("[WEB SEARCH RESULTS]" in m["content"] for m in messages)
            yield "Local answer"

    def _no_decide(*_args):
        raise AssertionError("decide_search must not be called when disabled")

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())
    monkeypatch.setattr("membrane.api.app.decide_search", _no_decide)

    session_id = api_client.post("/api/chat/sessions").json()["id"]
    msg = api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "hello"},
    )
    lines = [jsonlib.loads(line) for line in msg.text.splitlines() if line.strip()]
    assert not any("web_search" in line for line in lines)
    assert lines[-1]["reply"] == "Local answer"


def test_api_policy_capabilities(api_client):
    res = api_client.get("/api/policy/capabilities")
    assert res.status_code == 200
    data = res.json()
    assert "self_only" in data["sources"]["whatsapp"]
    assert "user_only" not in data["sources"]["whatsapp"]
    assert "user_only" in data["sources"]["cursor"]


def test_api_chat_session_roundtrip(api_client, monkeypatch):
    import json as jsonlib

    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return True

        def chat_stream(self, messages):
            assert messages[0]["role"] == "system"
            assert messages[-1]["role"] == "user"
            yield "Hello "
            yield "from membrane"

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())

    create = api_client.post("/api/chat/sessions")
    assert create.status_code == 200
    session_id = create.json()["id"]

    get_one = api_client.get(f"/api/chat/sessions/{session_id}")
    assert get_one.status_code == 200

    list_res = api_client.get("/api/chat/sessions")
    assert any(item["id"] == session_id for item in list_res.json()["items"])

    msg = api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "Hi there"},
    )
    assert msg.status_code == 200
    lines = [jsonlib.loads(line) for line in msg.text.splitlines() if line.strip()]
    deltas = [line["delta"] for line in lines if "delta" in line]
    assert deltas == ["Hello ", "from membrane"]
    final = lines[-1]
    assert final["done"] is True
    assert final["reply"] == "Hello from membrane"
    assert len(final["session"]["turns"]) == 2


def test_api_chat_patch_and_context_usage(api_client, monkeypatch):
    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return True

        def chat_stream(self, _messages):
            yield "ok"

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())

    session_id = api_client.post("/api/chat/sessions").json()["id"]
    api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "Hello"},
    )

    usage = api_client.get(f"/api/chat/sessions/{session_id}/context-usage")
    assert usage.status_code == 200
    data = usage.json()
    assert data["estimated_tokens"] > 0

    prior_id = api_client.post("/api/chat/sessions").json()["id"]
    api_client.post(
        f"/api/chat/sessions/{prior_id}/message",
        json={"content": "We planned a Goa trip for March"},
    )
    api_client.post(
        f"/api/chat/sessions/{prior_id}/message",
        json={"content": "What dates work for Goa?"},
    )

    new_id = api_client.post("/api/chat/sessions").json()["id"]
    usage_with_prior = api_client.get(
        f"/api/chat/sessions/{new_id}/context-usage?draft=What%20did%20we%20plan%20for%20Goa?"
    )
    assert usage_with_prior.status_code == 200

    patch = api_client.patch(
        f"/api/chat/sessions/{prior_id}",
        json={"include_in_training": False},
    )
    assert patch.status_code == 200
    assert patch.json()["metadata"]["include_in_training"] is False

    listed = api_client.get("/api/chat/sessions").json()["items"]
    row = next(i for i in listed if i["id"] == prior_id)
    assert row["include_in_training"] is False


def test_api_chat_session_delete(api_client):
    session_id = api_client.post("/api/chat/sessions").json()["id"]

    res = api_client.delete(f"/api/chat/sessions/{session_id}")
    assert res.status_code == 200
    assert res.json() == {"deleted": session_id}

    assert api_client.get(f"/api/chat/sessions/{session_id}").status_code == 404
    list_res = api_client.get("/api/chat/sessions")
    assert not any(item["id"] == session_id for item in list_res.json()["items"])

    missing = api_client.delete(f"/api/chat/sessions/{session_id}")
    assert missing.status_code == 404


def test_api_chat_stream_error_records_nothing(api_client, monkeypatch):
    import json as jsonlib

    from membrane.llm.ollama import OllamaError

    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return True

        def chat_stream(self, _messages):
            yield "partial"
            raise OllamaError("connection dropped")

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())

    create = api_client.post("/api/chat/sessions")
    session_id = create.json()["id"]
    msg = api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "Hi"},
    )
    lines = [jsonlib.loads(line) for line in msg.text.splitlines() if line.strip()]
    assert lines[-1] == {"error": "connection dropped"}
    session = api_client.get(f"/api/chat/sessions/{session_id}").json()
    assert session["turns"] == []


def test_api_chat_missing_model(api_client, monkeypatch):
    class FakeClient:
        def health_check(self):
            return True

        def has_model(self, _model=None):
            return False

    monkeypatch.setattr("membrane.api.app.OllamaClient", lambda _cfg: FakeClient())

    create = api_client.post("/api/chat/sessions")
    session_id = create.json()["id"]
    res = api_client.post(
        f"/api/chat/sessions/{session_id}/message",
        json={"content": "Hi"},
    )
    assert res.status_code == 400
    assert "not installed" in res.json()["detail"]
    session = api_client.get(f"/api/chat/sessions/{session_id}").json()
    assert session["turns"] == []


def test_api_integrations_roundtrip(api_client):
    res = api_client.get("/api/integrations")
    assert res.status_code == 200
    data = res.json()
    assert "mcp_servers" in data
    assert "tools" in data
    assert "summary" in data
    assert len(data["mcp_servers"]) >= 1
    assert len(data["tools"]) >= 1

    first_mcp = data["mcp_servers"][0]
    first_mcp["enabled"] = not first_mcp["enabled"]
    res2 = api_client.put("/api/integrations", json={"mcp_servers": data["mcp_servers"]})
    assert res2.status_code == 200
    saved = res2.json()
    assert saved["mcp_servers"][0]["enabled"] == first_mcp["enabled"]


def test_api_training_status(api_client):
    res = api_client.get("/api/training/status")
    assert res.status_code == 200
    data = res.json()
    assert "needs_train" in data
    assert "exports" in data
    assert "fine_tune" in data
    assert "training_available" in data
    assert "fine_tune_running" in data


def test_api_training_export(api_client):
    res = api_client.post("/api/training/export", json={"kind": "sft"})
    assert res.status_code == 200
    data = res.json()
    assert "sft" in data["paths"]
    assert data["fine_tune"]["last_export_at"] is not None


def test_api_training_fine_tune_requires_deps(api_client, monkeypatch):
    monkeypatch.setattr(
        "membrane.api.app.training_deps_available",
        lambda: False,
    )
    res = api_client.post(
        "/api/training/fine-tune",
        json={"base_model": "qwen2.5:3b", "output_model": "membrane-pa:latest"},
    )
    assert res.status_code == 501


def test_api_training_fine_tune_starts_job(api_client, monkeypatch):
    from membrane.config_integrations import FineTuneConfig

    fake_ft = FineTuneConfig(
        base_model="qwen2.5:3b",
        output_model="membrane-pa:latest",
        status="queued",
    )
    monkeypatch.setattr("membrane.api.app.training_deps_available", lambda: True)
    monkeypatch.setattr("membrane.api.app.is_fine_tune_running", lambda: False)
    monkeypatch.setattr(
        "membrane.api.app.start_fine_tune_job",
        lambda factory: fake_ft,
    )

    res = api_client.post(
        "/api/training/fine-tune",
        json={"base_model": "qwen2.5:3b", "output_model": "membrane-pa:latest"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "queued"
    assert "fine_tune" in data


def test_api_integration_credentials(api_client):
    res = api_client.get("/api/integrations/credentials")
    assert res.status_code == 200
    data = res.json()
    assert "tools" in data
    assert "oauth_providers" in data
    assert "github" in data["tools"]

    res2 = api_client.put(
        "/api/integrations/credentials/github",
        json={"values": {"access_token": "ghp_test1234567890"}},
    )
    assert res2.status_code == 200
    assert res2.json()["connected"] is True

    res3 = api_client.delete("/api/integrations/credentials/github")
    assert res3.status_code == 200
