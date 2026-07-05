"""Tests for config dot-path helpers and CLI config commands."""

from __future__ import annotations

from typer.testing import CliRunner

from membrane.config import PersonaConfig, Settings, load_persona, save_persona
from membrane.config_paths import get_nested, parse_config_value, set_nested
from membrane.config_store import reset_config_store
from membrane.cli_config import config_app


def test_parse_config_value_types():
    assert parse_config_value("true") is True
    assert parse_config_value("42") == 42
    assert parse_config_value("3.14") == 3.14
    assert parse_config_value('["a","b"]') == ["a", "b"]
    assert parse_config_value("hello") == "hello"


def test_set_and_get_nested():
    data = {"firecrawl": {"enabled": False}}
    set_nested(data, "firecrawl.enabled", True)
    assert get_nested(data, "firecrawl.enabled") is True


def test_cli_persona_set(tmp_path, monkeypatch):
    settings = Settings(root=tmp_path)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    reset_config_store()
    monkeypatch.setattr("membrane.config.get_settings", lambda: settings)
    monkeypatch.setattr("membrane.config_store.get_settings", lambda: settings)
    monkeypatch.setattr("membrane.cli_config.load_persona", load_persona)
    monkeypatch.setattr("membrane.cli_config.save_persona", save_persona)

    save_persona(PersonaConfig())
    runner = CliRunner()
    result = runner.invoke(config_app, ["persona", "set", "firecrawl.enabled", "true"])
    assert result.exit_code == 0, result.output
    assert load_persona().firecrawl.enabled is True
