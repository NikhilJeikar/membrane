"""Bubblewrap-based sandbox for shell commands."""

from __future__ import annotations

import shutil
from pathlib import Path

from membrane.config import ShellConfig, get_settings

_BWRAP_BIN = "bwrap"
_SHELL_BIN = "/usr/bin/bash"


def bubblewrap_path() -> Path | None:
    found = shutil.which(_BWRAP_BIN)
    return Path(found) if found else None


def resolve_shell_workspace(config: ShellConfig) -> Path:
    custom = (config.workspace_dir or "").strip()
    if custom:
        path = Path(custom).expanduser()
        if not path.is_absolute():
            path = get_settings().root / path
    else:
        path = get_settings().shell_workspace_dir
    path.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve()
    tmp_root = Path("/tmp").resolve()
    if resolved == tmp_root or tmp_root in resolved.parents:
        raise ValueError(
            "Shell workspace cannot live under /tmp; use data/shell_workspace or another path."
        )
    return resolved


def build_sandbox_argv(command: str, config: ShellConfig, workspace: Path) -> list[str]:
    bwrap = bubblewrap_path()
    if bwrap is None:
        raise FileNotFoundError(
            "bubblewrap (bwrap) is not installed. Install it to use shell commands."
        )

    argv = [
        str(bwrap),
        "--ro-bind",
        "/",
        "/",
        "--bind",
        str(workspace),
        str(workspace),
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        str(workspace),
        "--die-with-parent",
        "--new-session",
    ]
    if not config.allow_network:
        argv.append("--unshare-net")
    argv.extend(
        [
            "--setenv",
            "HOME",
            str(workspace),
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--setenv",
            "TERM",
            "dumb",
            _SHELL_BIN,
            "-lc",
            command,
        ]
    )
    return argv


def sandbox_summary(workspace: Path, config: ShellConfig) -> str:
    network = "enabled" if config.allow_network else "disabled"
    return (
        f"Sandbox workspace: {workspace}. "
        f"The rest of the filesystem is read-only, sudo is blocked, and network is {network}."
    )
