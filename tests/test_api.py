"""Tests for control UI API."""

from fastapi.testclient import TestClient

from shadow_pa.api.app import create_app


def test_api_status():
    client = TestClient(create_app())
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "pending_proposals" in data
    assert "ollama_ok" in data


def test_api_policy_roundtrip():
    client = TestClient(create_app())
    res = client.get("/api/policy")
    assert res.status_code == 200
    policy = res.json()
    policy["phase"] = "review"
    res2 = client.put("/api/policy", json=policy)
    assert res2.status_code == 200


def test_api_proposed_list():
    client = TestClient(create_app())
    res = client.get("/api/memory/proposed?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "items" in data
