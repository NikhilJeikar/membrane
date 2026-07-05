"""Ingest result counters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class IngestStats:
    processed: int = 0
    skipped: int = 0
    outputs: list[Path] = field(default_factory=list)


@dataclass
class ExtractStats:
    processed_files: int = 0
    skipped_files: int = 0
    proposals: int = 0
    failed_chunks: int = 0
