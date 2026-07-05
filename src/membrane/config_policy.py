"""Training and ingest policy configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from membrane.config import get_settings


class SourcePolicy(BaseModel):
    ingest: bool = True
    extract: bool = True
    train: bool = False
    auto_approve_episodes: bool = False
    auto_approve_profile: bool = False
    auto_approve_preference: bool = False
    redact: bool = True
    self_only: bool = False
    user_only: bool = False


class NightlyPolicy(BaseModel):
    enabled: bool = False
    since_hours: int = Field(default=24, ge=1, le=168)


class TrainingPolicy(BaseModel):
    phase: str = "review"
    nightly: NightlyPolicy = Field(default_factory=NightlyPolicy)
    sources: dict[str, SourcePolicy] = Field(default_factory=dict)

    @classmethod
    def default(cls) -> TrainingPolicy:
        return cls(
            phase="review",
            sources={
                "email": SourcePolicy(train=True),
                "calendar": SourcePolicy(train=True),
                "search": SourcePolicy(train=True),
                "cursor": SourcePolicy(train=False, user_only=True),
                "claude": SourcePolicy(train=False, user_only=True),
                "openai": SourcePolicy(train=False, user_only=True),
                "whatsapp": SourcePolicy(train=True, self_only=True),
                "wiki": SourcePolicy(extract=False, train=False),
            },
        )


def policy_path() -> Path:
    settings = get_settings()
    path = settings.config_dir / "training_policy.yaml"
    example = settings.config_dir / "training_policy.example.yaml"
    if not path.exists() and example.exists():
        path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def load_training_policy() -> TrainingPolicy:
    path = policy_path()
    if not path.exists():
        return TrainingPolicy.default()
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources_raw = raw.get("sources") or {}
    sources = {name: SourcePolicy.model_validate(cfg) for name, cfg in sources_raw.items()}
    nightly = NightlyPolicy.model_validate(raw.get("nightly") or {})
    return TrainingPolicy(phase=raw.get("phase", "review"), nightly=nightly, sources=sources)


def save_training_policy(policy: TrainingPolicy) -> Path:
    path = policy_path()
    payload = {
        "phase": policy.phase,
        "nightly": policy.nightly.model_dump(),
        "sources": {name: cfg.model_dump() for name, cfg in policy.sources.items()},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False), encoding="utf-8")
    return path
