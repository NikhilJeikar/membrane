"""Training and ingest policy configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


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
    # Local time of day (24h HH:MM) at which the training job should run.
    time: str = Field(default="02:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
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


AUTO_APPROVE_FIELDS = (
    "auto_approve_episodes",
    "auto_approve_profile",
    "auto_approve_preference",
)

SERVER_SOURCE_FIELDS = (
    "ingest",
    "extract",
    "train",
    "redact",
    *AUTO_APPROVE_FIELDS,
)

AGENT_SOURCE_FIELDS = (
    "ingest",
    "extract",
    "train",
    "redact",
    "user_only",
    *AUTO_APPROVE_FIELDS,
)

SOURCE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "email": SERVER_SOURCE_FIELDS,
    "calendar": SERVER_SOURCE_FIELDS,
    "search": SERVER_SOURCE_FIELDS,
    "cursor": AGENT_SOURCE_FIELDS,
    "claude": AGENT_SOURCE_FIELDS,
    "openai": AGENT_SOURCE_FIELDS,
    "whatsapp": (
        "ingest",
        "extract",
        "train",
        "redact",
        "self_only",
        *AUTO_APPROVE_FIELDS,
    ),
    "wiki": ("ingest", "extract", "train"),
}

SOURCE_DESCRIPTIONS: dict[str, str] = {
    "email": "Email ingested via the local server collector.",
    "calendar": "Calendar events from the local server.",
    "search": "Search history from the local server.",
    "cursor": "Cursor agent session transcripts.",
    "claude": "Claude agent session transcripts.",
    "openai": "OpenAI/Codex agent session transcripts.",
    "whatsapp": "WhatsApp chat exports.",
    "wiki": "Wikipedia corpus for summarization datasets (no PII redaction).",
}


def load_training_policy() -> TrainingPolicy:
    from membrane.config_store import NAMESPACE_TRAINING_POLICY, ensure_config_db, load_config_raw

    ensure_config_db()
    raw = load_config_raw(NAMESPACE_TRAINING_POLICY)
    if raw is None:
        return TrainingPolicy.default()
    sources_raw = raw.get("sources") or {}
    sources = {name: SourcePolicy.model_validate(cfg) for name, cfg in sources_raw.items()}
    nightly = NightlyPolicy.model_validate(raw.get("nightly") or {})
    return TrainingPolicy(phase=raw.get("phase", "review"), nightly=nightly, sources=sources)


def save_training_policy(policy: TrainingPolicy) -> Path:
    from membrane.config_store import NAMESPACE_TRAINING_POLICY, save_config_raw

    payload = {
        "phase": policy.phase,
        "nightly": policy.nightly.model_dump(),
        "sources": {name: cfg.model_dump() for name, cfg in policy.sources.items()},
    }
    return save_config_raw(NAMESPACE_TRAINING_POLICY, payload)
