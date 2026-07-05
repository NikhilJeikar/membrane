"""Tests for SQLAlchemy config storage."""

from __future__ import annotations

from membrane.config import PersonaConfig, Settings, load_persona, save_persona
from membrane.config_policy import TrainingPolicy, load_training_policy, save_training_policy
from membrane.config_store import (
    NAMESPACE_PERSONA,
    ensure_config_db,
    load_config_raw,
    reset_config_store,
    save_config_raw,
    seed_default_config,
)


def _settings(tmp_path, monkeypatch) -> Settings:
    settings = Settings(root=tmp_path)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("membrane.config.get_settings", lambda: settings)
    monkeypatch.setattr("membrane.config_store.get_settings", lambda: settings)
    reset_config_store()
    return settings


def test_config_store_roundtrip(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    save_config_raw(NAMESPACE_PERSONA, {"llm": {"model": "qwen2.5:3b"}})
    raw = load_config_raw(NAMESPACE_PERSONA)
    assert raw == {"llm": {"model": "qwen2.5:3b"}}


def test_seed_default_config(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    ensure_config_db()
    persona = load_config_raw(NAMESPACE_PERSONA)
    assert persona is not None
    assert "llm" in persona


def test_save_persona_writes_db(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    persona = PersonaConfig()
    persona.llm.model = "saved-in-db"
    db_path = save_persona(persona)

    assert db_path.name == "membrane.db"
    assert db_path.exists()

    reloaded = load_persona()
    assert reloaded.llm.model == "saved-in-db"


def test_load_persona_accepts_large_context_window(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    save_config_raw(NAMESPACE_PERSONA, {"llm": {"context_window": 819_200}})
    persona = load_persona()
    assert persona.llm.context_window == 819_200


def test_training_policy_roundtrip(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    policy = TrainingPolicy.default()
    policy.phase = "policy"
    save_training_policy(policy)
    loaded = load_training_policy()
    assert loaded.phase == "policy"


def test_seed_default_config_idempotent(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    save_config_raw(NAMESPACE_PERSONA, {"llm": {"model": "custom"}})
    seed_default_config()
    raw = load_config_raw(NAMESPACE_PERSONA)
    assert raw["llm"]["model"] == "custom"
