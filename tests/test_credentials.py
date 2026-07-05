"""Tests for integration credentials."""

import pytest

from membrane.integrations.credentials import (
    clear_tool_credentials,
    credentials_catalog,
    tool_connection_status,
    upsert_tool_credentials,
)


@pytest.fixture
def creds_env(tmp_path, monkeypatch):
    settings_root = tmp_path
    monkeypatch.setattr(
        "membrane.integrations.credentials.get_settings",
        lambda: type("S", (), {"config_dir": settings_root / "config"})(),
    )
    (settings_root / "config").mkdir(parents=True)
    return settings_root


def test_credentials_save_and_connect(creds_env):
    upsert_tool_credentials("github", {"access_token": "ghp_testtoken123456"})
    assert tool_connection_status("github") is True
    catalog = credentials_catalog()
    assert catalog["tools"]["github"]["connected"] is True
    assert catalog["tools"]["github"]["values"]["access_token"].endswith("3456")


def test_credentials_mask_short_values(creds_env):
    upsert_tool_credentials("notion", {"integration_token": "sec"})
    catalog = credentials_catalog()
    assert catalog["tools"]["notion"]["values"]["integration_token"] == "••••"


def test_credentials_clear(creds_env):
    upsert_tool_credentials("slack", {"bot_token": "xoxb-test-token"})
    clear_tool_credentials("slack")
    assert tool_connection_status("slack") is False


def test_shell_connection_status_reflects_persona(creds_env, monkeypatch):
    from membrane.config import PersonaConfig, save_persona

    monkeypatch.setattr("membrane.config.get_settings", lambda: type("S", (), {"config_dir": creds_env / "config"})())
    monkeypatch.setattr("membrane.config_store.get_settings", lambda: type("S", (), {"config_dir": creds_env / "config", "database_url_resolved": f"sqlite:///{creds_env / 'config' / 'membrane.db'}"})())
    monkeypatch.setattr("membrane.integrations.credentials.get_settings", lambda: type("S", (), {"config_dir": creds_env / "config"})())

    persona = PersonaConfig()
    persona.shell.enabled = True
    save_persona(persona)

    assert tool_connection_status("shell") is True


def test_unknown_tool_rejected(creds_env):
    with pytest.raises(ValueError, match="unknown tool"):
        upsert_tool_credentials("unknown", {"token": "x"})
