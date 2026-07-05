"""CLI commands for config database read/write (mirrors UI settings)."""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer
from rich.console import Console

from membrane.config import PersonaConfig, load_persona, save_persona
from membrane.config_integrations import IntegrationsConfig, load_integrations, save_integrations
from membrane.config_paths import get_nested, parse_config_value, set_nested
from membrane.config_policy import TrainingPolicy, load_training_policy, save_training_policy
from membrane.integrations.credentials import load_credentials_raw, upsert_tool_credentials

console = Console()
config_app = typer.Typer(no_args_is_help=True, help="View and edit config stored in the database.")
persona_app = typer.Typer(no_args_is_help=True, help="Persona settings (LLM, web search, Firecrawl, style).")
policy_app = typer.Typer(no_args_is_help=True, help="Training and ingest policy.")
integrations_app = typer.Typer(no_args_is_help=True, help="MCP servers, tools, and fine-tune options.")
credentials_app = typer.Typer(no_args_is_help=True, help="Integration credentials (secrets).")

config_app.add_typer(persona_app, name="persona")
config_app.add_typer(policy_app, name="policy")
config_app.add_typer(integrations_app, name="integrations")
config_app.add_typer(credentials_app, name="credentials")

_SECRET_KEYS = {"token", "api_key", "secret", "password", "access_token", "refresh_token", "bot_token"}


def _mask_secrets(data: Any, parent_key: str = "") -> Any:
    if isinstance(data, dict):
        return {k: _mask_secrets(v, k) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask_secrets(item, parent_key) for item in data]
    if isinstance(data, str) and data:
        key = parent_key.lower()
        if any(part in key for part in _SECRET_KEYS):
            return "***" if len(data) <= 8 else f"{data[:4]}…{data[-2:]}"
    return data


def _print_json(data: Any) -> None:
    console.print_json(json.dumps(data, indent=2, default=str))


def _apply_persona_patch(persona: PersonaConfig, path: str, value: Any) -> PersonaConfig:
    payload = persona.model_dump(mode="python")
    set_nested(payload, path, value)
    return PersonaConfig.model_validate(payload)


def _apply_policy_patch(policy: TrainingPolicy, path: str, value: Any) -> TrainingPolicy:
    payload = policy.model_dump(mode="python")
    set_nested(payload, path, value)
    return TrainingPolicy.model_validate(payload)


def _apply_integrations_patch(config: IntegrationsConfig, path: str, value: Any) -> IntegrationsConfig:
    payload = config.model_dump(mode="python")
    set_nested(payload, path, value)
    return IntegrationsConfig.model_validate(payload)


@config_app.callback(invoke_without_command=True)
def config_show_all() -> None:
    """Show all config namespaces (credentials masked)."""
    console.print("[bold]persona[/bold]")
    _print_json(load_persona().model_dump(mode="python"))
    console.print("\n[bold]policy[/bold]")
    _print_json(load_training_policy().model_dump(mode="python"))
    console.print("\n[bold]integrations[/bold]")
    _print_json(load_integrations().model_dump(mode="python"))
    console.print("\n[bold]credentials[/bold]")
    _print_json(_mask_secrets({"tools": load_credentials_raw()}))


@persona_app.command("show")
def persona_show(
    path: Annotated[str | None, typer.Argument(help="Optional dot path, e.g. firecrawl.enabled")] = None,
) -> None:
    """Show persona config or a single field."""
    data = load_persona().model_dump(mode="python")
    if path:
        _print_json(get_nested(data, path))
    else:
        _print_json(data)


@persona_app.command("set")
def persona_set(
    path: Annotated[str, typer.Argument(help="Dot path, e.g. firecrawl.enabled")],
    value: Annotated[str, typer.Argument(help="Value (true/false/number/JSON string)")],
) -> None:
    """Update one persona field."""
    parsed = parse_config_value(value)
    persona = _apply_persona_patch(load_persona(), path, parsed)
    save_persona(persona)
    console.print(f"[green]Updated[/green] persona.{path} = {parsed!r}")


@policy_app.command("show")
def policy_show(
    path: Annotated[str | None, typer.Argument(help="Optional dot path, e.g. sources.whatsapp.train")] = None,
) -> None:
    """Show training policy or a single field."""
    data = load_training_policy().model_dump(mode="python")
    if path:
        _print_json(get_nested(data, path))
    else:
        _print_json(data)


@policy_app.command("set")
def policy_set(
    path: Annotated[str, typer.Argument(help="Dot path, e.g. sources.whatsapp.train")],
    value: Annotated[str, typer.Argument(help="Value")],
) -> None:
    """Update one training policy field."""
    parsed = parse_config_value(value)
    policy = _apply_policy_patch(load_training_policy(), path, parsed)
    save_training_policy(policy)
    console.print(f"[green]Updated[/green] policy.{path} = {parsed!r}")


@integrations_app.command("show")
def integrations_show(
    path: Annotated[str | None, typer.Argument(help="Optional dot path, e.g. fine_tune.include_chats")] = None,
) -> None:
    """Show integrations config or a single field."""
    data = load_integrations().model_dump(mode="python")
    if path:
        _print_json(get_nested(data, path))
    else:
        _print_json(data)


@integrations_app.command("set")
def integrations_set(
    path: Annotated[str, typer.Argument(help="Dot path, e.g. fine_tune.fetch_search_pages")],
    value: Annotated[str, typer.Argument(help="Value")],
) -> None:
    """Update one integrations field."""
    parsed = parse_config_value(value)
    config = _apply_integrations_patch(load_integrations(), path, parsed)
    save_integrations(config)
    console.print(f"[green]Updated[/green] integrations.{path} = {parsed!r}")


@credentials_app.command("show")
def credentials_show(
    tool_id: Annotated[str | None, typer.Argument(help="Tool id, e.g. github")] = None,
) -> None:
    """Show stored credentials (masked)."""
    creds = load_credentials_raw()
    if tool_id:
        _print_json(_mask_secrets(creds.get(tool_id, {})))
    else:
        _print_json(_mask_secrets(creds))


@credentials_app.command("set")
def credentials_set(
    tool_id: Annotated[str, typer.Argument(help="Tool id, e.g. github")],
    key: Annotated[str, typer.Argument(help="Credential key, e.g. access_token")],
    value: Annotated[str, typer.Argument(help="Secret value")],
) -> None:
    """Set one credential field for a tool."""
    upsert_tool_credentials(tool_id, {key: value})
    console.print(f"[green]Updated[/green] credentials.{tool_id}.{key}")
