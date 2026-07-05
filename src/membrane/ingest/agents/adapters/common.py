"""Shared text extraction helpers for agent adapters."""

from __future__ import annotations

import re

from membrane.utils.redact import redact_text

USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL | re.IGNORECASE)
TIMESTAMP_RE = re.compile(r"<timestamp>.*?</timestamp>\s*", re.DOTALL | re.IGNORECASE)
HOME_PATH_RE = re.compile(r"/home/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._~/-]*)*")
PROJECTS_PATH_RE = re.compile(r"~/Projects/[A-Za-z0-9._/-]+")
CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")


def strip_cursor_user_message(text: str) -> str:
    match = USER_QUERY_RE.search(text)
    if match:
        text = match.group(1).strip()
    return TIMESTAMP_RE.sub("", text).strip()


def extract_structured_content_parts(
    content_parts: list[dict],
    *,
    skip_tool_heavy: bool,
    min_assistant_chars: int,
) -> tuple[str, bool]:
    texts: list[str] = []
    has_tools = False
    for part in content_parts:
        part_type = part.get("type", "")
        if part_type == "tool_use":
            has_tools = True
            continue
        if part_type == "text":
            text = part.get("text", "").strip()
            if text:
                texts.append(text)
    combined = "\n\n".join(texts)
    combined = CODE_FENCE_RE.sub("[code omitted]", combined)
    if skip_tool_heavy and has_tools and len(combined) < min_assistant_chars:
        return "", has_tools
    return combined.strip(), has_tools


def extract_openai_content(content: object) -> tuple[str, bool]:
    if isinstance(content, str):
        return content.strip(), False
    if not isinstance(content, list):
        return "", False
    texts: list[str] = []
    has_tools = False
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type", "")
        if part_type in ("tool_use", "tool_call", "function_call"):
            has_tools = True
            continue
        if part_type == "text":
            text = part.get("text", "").strip()
            if text:
                texts.append(text)
        elif "text" in part and isinstance(part["text"], str):
            texts.append(part["text"].strip())
    combined = "\n\n".join(texts)
    combined = CODE_FENCE_RE.sub("[code omitted]", combined)
    return combined.strip(), has_tools


def sanitize_agent_text(text: str, *, redact: bool) -> str:
    text = HOME_PATH_RE.sub("[PATH]", text)
    text = PROJECTS_PATH_RE.sub("[PATH]", text)
    if redact:
        text = redact_text(text)
    return text.strip()


def workspace_hint_from_path(path: Path) -> str | None:
    parts = path.parts
    for part in parts:
        if part.startswith("home-nikhil-Projects-"):
            return part.replace("home-nikhil-Projects-", "")
        if part.startswith("home-nikhil-"):
            return part.replace("home-nikhil-", "")
        if part.startswith("-home-"):
            return part.lstrip("-").replace("-", "/")
    return None
