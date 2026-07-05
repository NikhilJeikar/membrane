"""Tests for optional shell command execution in chat."""

import json
from pathlib import Path

import pytest

from membrane.config import ShellConfig
from membrane.inference.shell import (
    format_shell_results_block,
    is_command_allowed,
    iter_shell_loop,
    run_shell_command,
    run_shell_loop,
)
from membrane.inference.shell_sandbox import (
    build_sandbox_argv,
    bubblewrap_path,
    resolve_shell_workspace,
)
from membrane.memory.models import ChatTurn


def test_is_command_allowed_blocks_sudo_variants():
    assert is_command_allowed("ls -la") is True
    assert is_command_allowed("echo hello") is True
    assert is_command_allowed("sudo apt update") is False
    assert is_command_allowed("cd /tmp && sudo rm file") is False
    assert is_command_allowed("pkexec foo") is False
    assert is_command_allowed("doas command") is False
    assert is_command_allowed("su - root") is False
    assert is_command_allowed("su root -c 'id'") is False


def _test_workspace(name: str) -> Path:
    path = Path(__file__).resolve().parents[1] / "data" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.mark.skipif(bubblewrap_path() is None, reason="bubblewrap not installed")
def test_run_shell_command_executes_simple_command():
    workspace = _test_workspace("test_shell_workspace")
    config = ShellConfig()
    result = run_shell_command("echo membrane-shell-test", config, workspace=workspace)
    assert result.blocked is False
    assert result.exit_code == 0
    assert "membrane-shell-test" in result.stdout


def test_run_shell_command_blocks_sudo():
    result = run_shell_command("sudo id", ShellConfig())
    assert result.blocked is True
    assert "Blocked" in result.stderr


@pytest.mark.skipif(bubblewrap_path() is None, reason="bubblewrap not installed")
def test_run_shell_command_blocks_writes_outside_workspace():
    workspace = _test_workspace("test_shell_workspace")
    config = ShellConfig()
    result = run_shell_command(
        "touch blocked.txt",
        config,
        workspace=workspace,
    )
    assert result.exit_code == 0
    assert (workspace / "blocked.txt").exists()


def test_run_shell_command_requires_bubblewrap(monkeypatch):
    monkeypatch.setattr("membrane.inference.shell.bubblewrap_path", lambda: None)
    result = run_shell_command("echo hello", ShellConfig())
    assert result.blocked is True
    assert "bubblewrap" in result.stderr.lower()


@pytest.mark.skipif(bubblewrap_path() is None, reason="bubblewrap not installed")
def test_build_sandbox_argv_blocks_network_by_default(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    argv = build_sandbox_argv("echo hi", ShellConfig(), workspace)
    assert "--unshare-net" in argv
    assert str(workspace) in argv


@pytest.mark.skipif(bubblewrap_path() is None, reason="bubblewrap not installed")
def test_build_sandbox_argv_allows_network_when_enabled(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    argv = build_sandbox_argv("echo hi", ShellConfig(allow_network=True), workspace)
    assert "--unshare-net" not in argv


def test_resolve_shell_workspace_rejects_tmp_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMBRANE_ROOT", str(tmp_path))
    from membrane.config import Settings

    monkeypatch.setattr(
        "membrane.inference.shell_sandbox.get_settings",
        lambda: Settings(root=tmp_path),
    )
    with pytest.raises(ValueError, match="/tmp"):
        resolve_shell_workspace(ShellConfig(workspace_dir="/tmp/shell_ws"))


def test_resolve_shell_workspace_uses_custom_dir(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    from membrane.config import Settings

    monkeypatch.setattr(
        "membrane.inference.shell_sandbox.get_settings",
        lambda: Settings(root=root),
    )
    path = resolve_shell_workspace(ShellConfig(workspace_dir="data/custom_sandbox_test"))
    assert path == (root / "data" / "custom_sandbox_test").resolve()
    assert path.exists()


@pytest.mark.skipif(bubblewrap_path() is None, reason="bubblewrap not installed")
def test_format_shell_results_block_includes_output():
    workspace = _test_workspace("test_shell_workspace")
    config = ShellConfig()
    block = format_shell_results_block(
        [run_shell_command("echo hello", config, workspace=workspace)],
        config,
    )
    assert "[SHELL COMMAND OUTPUT]" in block
    assert "Sandbox workspace" in block
    assert "echo hello" in block
    assert "hello" in block


def test_run_shell_loop_stops_when_model_declines(monkeypatch):
    class FakeClient:
        def chat(self, _messages, **_kwargs):
            return json.dumps({"run": False, "command": ""})

    results = run_shell_loop(FakeClient(), [ChatTurn(role="user", content="Hi")], ShellConfig())
    assert results == []


@pytest.mark.skipif(bubblewrap_path() is None, reason="bubblewrap not installed")
def test_run_shell_loop_runs_model_command(monkeypatch):
    workspace = _test_workspace("test_shell_workspace")
    calls = {"count": 0}

    class FakeClient:
        def chat(self, _messages, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return json.dumps({"run": True, "command": "echo loop-test"})
            return json.dumps({"run": False, "command": ""})

    monkeypatch.setattr(
        "membrane.inference.shell.resolve_shell_workspace",
        lambda _config: workspace,
    )
    results = run_shell_loop(
        FakeClient(),
        [ChatTurn(role="user", content="What kernel am I running?")],
        ShellConfig(max_commands_per_turn=3),
    )
    assert len(results) == 1
    assert results[0].exit_code == 0
    assert "loop-test" in results[0].stdout


@pytest.mark.skipif(bubblewrap_path() is None, reason="bubblewrap not installed")
def test_iter_shell_loop_yields_start_and_complete(monkeypatch):
    workspace = _test_workspace("test_shell_workspace")
    calls = {"count": 0}

    class FakeClient:
        def chat(self, _messages, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return json.dumps({"run": True, "command": "echo stream-test"})
            return json.dumps({"run": False, "command": ""})

    monkeypatch.setattr(
        "membrane.inference.shell.resolve_shell_workspace",
        lambda _config: workspace,
    )
    events = list(
        iter_shell_loop(
            FakeClient(),
            [ChatTurn(role="user", content="Check hostname")],
            ShellConfig(max_commands_per_turn=3),
        )
    )
    assert [phase for phase, _command, _snapshot in events] == ["start", "complete"]
    assert events[0][1] == "echo stream-test"
    assert events[0][2] == []
    assert len(events[1][2]) == 1
    assert "stream-test" in events[1][2][0].stdout
