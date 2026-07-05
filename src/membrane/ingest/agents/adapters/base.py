"""Agent transcript adapter protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from membrane.ingest.agents.models import AgentSession


class AgentAdapter(ABC):
    name: str
    label: str

    @abstractmethod
    def can_parse(self, sample_rows: list[dict[str, Any]]) -> bool:
        """Return True if sample JSONL rows match this adapter."""

    @abstractmethod
    def discover(self, root: Path) -> list[Path]:
        """Find transcript files for this agent under root."""

    @abstractmethod
    def parse(
        self,
        path: Path,
        *,
        include_assistant: bool = True,
        min_assistant_chars: int = 40,
        max_assistant_chars: int = 4000,
        skip_tool_heavy: bool = True,
        redact: bool = True,
    ) -> AgentSession:
        """Parse a transcript file into a normalized session."""
