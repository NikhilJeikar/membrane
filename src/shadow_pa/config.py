"""Project paths and persona configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class LLMConfig(BaseModel):
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    extractor_model: str = "qwen2.5:7b"
    temperature: float = 0.3
    timeout_seconds: float = Field(
        default=600.0,
        ge=30.0,
        description="Read timeout per Ollama request (CPU inference can be slow)",
    )
    max_retries: int = Field(default=2, ge=0, le=5)
    num_threads: int = Field(
        default=0,
        ge=0,
        description="CPU threads per Ollama request (0 = use all cores)",
    )
    parallel_requests: int = Field(
        default=0,
        ge=0,
        description="Concurrent Ollama requests (0 or 1 recommended on CPU-only)",
    )


class PerformanceConfig(BaseModel):
    workers: int = Field(
        default=0,
        ge=0,
        description="Parallel workers for ingest/extract (0 = CPU cores - 1)",
    )


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    token: str = ""
    parse_interval_seconds: int = Field(
        default=300,
        ge=30,
        description="How often the server parses raw → parsed (seconds)",
    )
    auto_extract: bool = Field(
        default=False,
        description="After parse, run offline extractor and create proposals",
    )


class StyleConfig(BaseModel):
    format: str = "bullets"
    max_length: str = "short"
    empathy_level: float = Field(default=0.6, ge=0.0, le=1.0)
    proactivity: float = Field(default=0.4, ge=0.0, le=1.0)


class MemoryConfig(BaseModel):
    use_profile: bool = True
    use_preferences: bool = True
    use_episodes: bool = True
    max_episodes_in_context: int = 5
    confirm_before_save: bool = True


class BoundariesConfig(BaseModel):
    never_claim_to_have_done: list[str] = Field(
        default_factory=lambda: ["booked", "sent email", "called", "paid"]
    )
    ask_when_unsure: bool = True


class PersonaConfig(BaseModel):
    identity: dict[str, str] = Field(default_factory=dict)
    style: StyleConfig = Field(default_factory=StyleConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    boundaries: BoundariesConfig = Field(default_factory=BoundariesConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    self_names: list[str] = Field(default_factory=lambda: ["Nikhil"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHADOW_PA_", extra="ignore")

    root: Path = Field(default_factory=project_root)

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def whatsapp_raw_dir(self) -> Path:
        return self.data_dir / "whatsapp" / "raw"

    @property
    def whatsapp_parsed_dir(self) -> Path:
        return self.data_dir / "whatsapp" / "parsed"

    @property
    def cursor_raw_dir(self) -> Path:
        return self.data_dir / "cursor" / "raw"

    @property
    def cursor_parsed_dir(self) -> Path:
        return self.data_dir / "cursor" / "parsed"

    @property
    def wiki_corpus_dir(self) -> Path:
        return self.data_dir / "corpus" / "wiki"

    @property
    def chats_dir(self) -> Path:
        return self.data_dir / "chats"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def training_dir(self) -> Path:
        return self.data_dir / "training"

    @property
    def manifest_path(self) -> Path:
        return self.data_dir / "ingest_manifest.json"

    @property
    def server_dir(self) -> Path:
        return self.data_dir / "server"

    @property
    def server_token_path(self) -> Path:
        return self.server_dir / "token"

    def server_raw_dir(self, source: str) -> Path:
        return self.data_dir / source / "raw"

    def server_parsed_dir(self, source: str) -> Path:
        return self.data_dir / source / "parsed"

    @property
    def persona_path(self) -> Path:
        return self.config_dir / "persona.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_persona(path: Path | None = None) -> PersonaConfig:
    settings = get_settings()
    persona_path = path or settings.persona_path
    if not persona_path.exists():
        example = settings.config_dir / "persona.example.yaml"
        if example.exists():
            persona_path = example
        else:
            return PersonaConfig()
    raw: dict[str, Any] = yaml.safe_load(persona_path.read_text(encoding="utf-8")) or {}
    return PersonaConfig.model_validate(raw)


def ensure_data_layout(root: Path | None = None) -> None:
    settings = Settings(root=root or project_root())
    dirs = [
        settings.config_dir,
        settings.memory_dir,
        settings.memory_dir / "examples",
        settings.memory_dir / "proposed",
        settings.memory_dir / "approved",
        settings.whatsapp_raw_dir,
        settings.whatsapp_parsed_dir,
        settings.cursor_raw_dir,
        settings.cursor_parsed_dir,
        settings.wiki_corpus_dir,
        settings.wiki_corpus_dir / "raw",
        settings.wiki_corpus_dir / "datasets",
        settings.chats_dir,
        settings.datasets_dir / "summarization",
        settings.datasets_dir / "coding",
        settings.datasets_dir / "personal_assistant",
        settings.training_dir / "sft",
        settings.training_dir / "dpo",
        settings.training_dir / "export",
        settings.server_dir,
    ]
    for source in ("email", "calendar", "search"):
        dirs.extend([settings.server_raw_dir(source), settings.server_parsed_dir(source)])
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
