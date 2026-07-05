"""SQLAlchemy-backed configuration storage (SQLite by default, URL swappable)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from membrane.config import get_settings

NAMESPACE_PERSONA = "persona"
NAMESPACE_TRAINING_POLICY = "training_policy"
NAMESPACE_INTEGRATIONS = "integrations"
NAMESPACE_CREDENTIALS = "credentials"

_ENGINE = None


class Base(DeclarativeBase):
    pass


class ConfigEntry(Base):
    __tablename__ = "config_entries"

    namespace: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def reset_config_store() -> None:
    """Drop cached engine (for tests)."""
    global _ENGINE
    _ENGINE = None


def get_engine():
    global _ENGINE
    settings = get_settings()
    url = settings.database_url_resolved
    if _ENGINE is None or str(_ENGINE.url) != url:
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _ENGINE = create_engine(url, connect_args=connect_args)
    return _ENGINE


def config_db_path() -> Path:
    settings = get_settings()
    url = settings.database_url_resolved
    if url.startswith("sqlite:///"):
        raw = url.removeprefix("sqlite:///")
        return Path(raw)
    return settings.config_dir / "membrane.db"


def _ensure_tables() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)


def seed_default_config() -> None:
    """Write built-in defaults for any missing config namespace."""
    if load_config_raw(NAMESPACE_PERSONA) is None:
        from membrane.config import PersonaConfig

        save_config_raw(NAMESPACE_PERSONA, PersonaConfig().model_dump(mode="python"))
    if load_config_raw(NAMESPACE_TRAINING_POLICY) is None:
        from membrane.config_policy import TrainingPolicy

        policy = TrainingPolicy.default()
        save_config_raw(
            NAMESPACE_TRAINING_POLICY,
            {
                "phase": policy.phase,
                "nightly": policy.nightly.model_dump(),
                "sources": {name: cfg.model_dump() for name, cfg in policy.sources.items()},
            },
        )
    if load_config_raw(NAMESPACE_INTEGRATIONS) is None:
        from membrane.config_integrations import IntegrationsConfig

        save_config_raw(
            NAMESPACE_INTEGRATIONS,
            IntegrationsConfig.default().model_dump(mode="python"),
        )
    if load_config_raw(NAMESPACE_CREDENTIALS) is None:
        save_config_raw(NAMESPACE_CREDENTIALS, {"tools": {}})


def ensure_config_db() -> Path:
    """Create tables and seed defaults when namespaces are missing."""
    _ensure_tables()
    seed_default_config()
    return config_db_path()


def load_config_raw(namespace: str) -> dict[str, Any] | None:
    _ensure_tables()
    with Session(get_engine()) as session:
        row = session.get(ConfigEntry, namespace)
        if row is None:
            return None
        data = json.loads(row.data)
        return data if isinstance(data, dict) else {}


def save_config_raw(namespace: str, payload: dict[str, Any]) -> Path:
    _ensure_tables()
    encoded = json.dumps(payload, ensure_ascii=False)
    now = datetime.now(tz=UTC)
    with Session(get_engine()) as session:
        row = session.get(ConfigEntry, namespace)
        if row is None:
            session.add(ConfigEntry(namespace=namespace, data=encoded, updated_at=now))
        else:
            row.data = encoded
            row.updated_at = now
        session.commit()
    return config_db_path()
