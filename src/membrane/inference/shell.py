"""Optional sandboxed shell command execution for chat (no sudo)."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from membrane.config import ShellConfig
from membrane.inference.shell_sandbox import (
    build_sandbox_argv,
    bubblewrap_path,
    resolve_shell_workspace,
    sandbox_summary,
)
from membrane.llm.ollama import OllamaClient, OllamaError
from membrane.memory.models import ChatTurn

_FORBIDDEN_COMMAND_RE = re.compile(
    r"(?:^|[\s;|&`$()<>])"
    r"(?:sudo|pkexec|doas)\b"
    r"|(?:^|[\s;|&`$()<>])su\s+(?:-|root|\w)"
    r"|(?:^|[\s;|&`$()<>])su\s*$",
    re.IGNORECASE,
)

_DECISION_SYSTEM = """You decide whether to run a shell command in Membrane's sandbox to help answer the user's latest message.

Commands run in an isolated workspace with a read-only view of the rest of the system.
Only the sandbox workspace is writable. Network access is usually disabled.
Run commands when they would materially help: inspect files, check system state, run scripts, etc.
Do NOT run commands for greetings, opinions, or questions answerable from conversation and memory alone.
Privileged commands are forbidden — never use sudo, su, pkexec, or doas.

Respond with JSON only:
{{"run": true, "command": "<single shell command>"}}
or
{{"run": false, "command": ""}}"""


@dataclass(frozen=True)
class ShellResult:
    command: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    blocked: bool = False
    timed_out: bool = False


class ShellError(RuntimeError):
    pass


def is_command_allowed(command: str) -> bool:
    text = command.strip()
    if not text:
        return False
    return _FORBIDDEN_COMMAND_RE.search(text) is None


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def run_shell_command(
    command: str,
    config: ShellConfig,
    *,
    workspace: Path | None = None,
) -> ShellResult:
    if not is_command_allowed(command):
        return ShellResult(
            command=command,
            blocked=True,
            stderr="Blocked: sudo and other privileged commands are not allowed.",
        )

    if bubblewrap_path() is None:
        return ShellResult(
            command=command,
            blocked=True,
            stderr="Blocked: bubblewrap (bwrap) is required for sandboxed shell commands.",
        )

    work_dir = workspace or resolve_shell_workspace(config)
    try:
        proc = subprocess.run(
            build_sandbox_argv(command, config, work_dir),
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return ShellResult(
            command=command,
            timed_out=True,
            stderr=f"Command timed out after {config.timeout_seconds:g}s.",
        )
    except OSError as exc:
        return ShellResult(command=command, exit_code=1, stderr=str(exc))

    stdout = _truncate(proc.stdout or "", config.max_output_chars)
    stderr = _truncate(proc.stderr or "", config.max_output_chars)
    return ShellResult(
        command=command,
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _format_prior_results(results: list[ShellResult]) -> str:
    if not results:
        return ""
    parts = ["Prior shell commands in this turn:"]
    for index, result in enumerate(results, 1):
        parts.append(f"{index}. $ {result.command}")
        if result.blocked:
            parts.append(f"   blocked: {result.stderr}")
        elif result.timed_out:
            parts.append(f"   timed out: {result.stderr}")
        else:
            parts.append(f"   exit code: {result.exit_code}")
            if result.stdout:
                parts.append(f"   stdout:\n{result.stdout}")
            if result.stderr:
                parts.append(f"   stderr:\n{result.stderr}")
    return "\n".join(parts)


def decide_shell_command(
    client: OllamaClient,
    turns: list[ChatTurn],
    prior_results: list[ShellResult],
) -> str | None:
    recent = [t for t in turns if t.role in ("user", "assistant")][-6:]
    convo = "\n".join(f"{t.role}: {t.content}" for t in recent)
    prior = _format_prior_results(prior_results)
    user_parts = [f"Conversation:\n{convo}"]
    if prior:
        user_parts.append(prior)
    user_parts.append("Should you run another shell command?")
    messages = [
        {"role": "system", "content": _DECISION_SYSTEM},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    try:
        raw = client.chat(messages, json_mode=True, temperature=0.0)
        data = json.loads(raw)
    except (OllamaError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("run"):
        return None
    command = str(data.get("command", "")).strip()
    return command or None


def shell_result_to_dict(result: ShellResult) -> dict:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "blocked": result.blocked,
        "timed_out": result.timed_out,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def iter_shell_loop(
    client: OllamaClient,
    turns: list[ChatTurn],
    config: ShellConfig,
):
    """Yield (phase, command, results) where phase is start or complete."""
    results: list[ShellResult] = []
    for _ in range(config.max_commands_per_turn):
        command = decide_shell_command(client, turns, results)
        if not command:
            break
        yield "start", command, list(results)
        result = run_shell_command(command, config)
        results.append(result)
        yield "complete", command, list(results)


def run_shell_loop(
    client: OllamaClient,
    turns: list[ChatTurn],
    config: ShellConfig,
) -> list[ShellResult]:
    results: list[ShellResult] = []
    for phase, _command, snapshot in iter_shell_loop(client, turns, config):
        if phase == "complete":
            results = snapshot
    return results


def format_shell_results_block(results: list[ShellResult], config: ShellConfig) -> str:
    workspace = resolve_shell_workspace(config)
    parts = [
        "[SHELL COMMAND OUTPUT]",
        sandbox_summary(workspace, config),
        "Use this output to answer the user. Mention when you relied on command results.",
        "",
    ]
    for index, result in enumerate(results, 1):
        parts.append(f"{index}. $ {result.command}")
        if result.blocked:
            parts.append(f"   blocked: {result.stderr}")
        elif result.timed_out:
            parts.append(f"   timed out: {result.stderr}")
        else:
            parts.append(f"   exit code: {result.exit_code}")
            if result.stdout:
                parts.append("   stdout:")
                parts.append(result.stdout)
            if result.stderr:
                parts.append("   stderr:")
                parts.append(result.stderr)
        parts.append("")
    return "\n".join(parts).rstrip()


def shell_results_to_metadata(results: list[ShellResult], content: str) -> dict:
    return {
        "commands": [shell_result_to_dict(result) for result in results],
        "content_chars": len(content),
        "tool_tokens": {"shell": len(content) // 4} if content else {},
    }
