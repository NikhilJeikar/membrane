"""Project paths and persona configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[2]


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
    context_window: int = Field(
        default=8192,
        ge=1024,
        le=2_097_152,
        description="Approximate model context size in tokens (for usage meter)",
    )
    thinking_enabled: bool = Field(
        default=False,
        description="Request chain-of-thought from Ollama thinking models (DeepSeek R1, Qwen3, …)",
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
    independent_opinions: bool = Field(
        default=True,
        description="Share honest views even when they differ from the user's",
    )


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


class WebSearchConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="Allow chat to search the web (queries leave your machine)",
    )
    max_results: int = Field(default=5, ge=1, le=10)
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class FirecrawlConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="Use a local Firecrawl instance (Podman/Docker) to scrape pages",
    )
    base_url: str = Field(
        default="http://localhost:3002",
        description="Firecrawl API base URL (self-hosted, no account required)",
    )
    api_key: str = Field(
        default="",
        description="Optional API key when USE_DB_AUTHENTICATION is enabled on Firecrawl",
    )
    timeout_seconds: float = Field(default=30.0, ge=5.0, le=120.0)
    max_chars: int = Field(default=8000, ge=1000, le=50000)
    scrape_in_chat: bool = Field(
        default=False,
        description="After web search, scrape top result pages into chat context",
    )
    max_pages_in_chat: int = Field(default=2, ge=0, le=5)


class ShellConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="Allow chat to run shell commands in a bubblewrap sandbox (sudo blocked)",
    )
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    max_output_chars: int = Field(default=8000, ge=500, le=50000)
    max_commands_per_turn: int = Field(default=5, ge=1, le=10)
    workspace_dir: str = Field(
        default="",
        description="Writable sandbox directory (default: data/shell_workspace)",
    )
    allow_network: bool = Field(
        default=False,
        description="Allow outbound network access from sandboxed commands",
    )


class PersonaConfig(BaseModel):
    identity: dict[str, str] = Field(default_factory=dict)
    style: StyleConfig = Field(default_factory=StyleConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    boundaries: BoundariesConfig = Field(default_factory=BoundariesConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    firecrawl: FirecrawlConfig = Field(default_factory=FirecrawlConfig)
    shell: ShellConfig = Field(default_factory=ShellConfig)
    self_names: list[str] = Field(default_factory=lambda: ["Nikhil"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MEMBRANE_", extra="ignore")

    root: Path = Field(default_factory=project_root)
    database_url: str = Field(
        default="",
        description="SQLAlchemy database URL (default: sqlite in config/membrane.db)",
    )

    @property
    def database_url_resolved(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        db_path = (self.config_dir / "membrane.db").resolve()
        return f"sqlite:///{db_path}"

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
    def agents_dir(self) -> Path:
        return self.data_dir / "agents"

    def agent_raw_dir(self, provider: str) -> Path:
        return self.agents_dir / provider / "raw"

    def agent_parsed_dir(self, provider: str) -> Path:
        return self.agents_dir / provider / "parsed"

    def legacy_agent_parsed_dir(self, provider: str) -> Path:
        """Pre-agents layout: data/{provider}/parsed (cursor only today)."""
        return self.data_dir / provider / "parsed"

    def resolved_agent_parsed_dir(self, provider: str) -> Path:
        legacy = self.legacy_agent_parsed_dir(provider)
        if provider == "cursor" and legacy.exists():
            return legacy
        return self.agent_parsed_dir(provider)

    def resolved_agent_raw_dir(self, provider: str) -> Path:
        legacy = self.data_dir / provider / "raw"
        if provider == "cursor" and legacy.exists():
            return legacy
        return self.agent_raw_dir(provider)

    def list_agent_providers(self) -> list[str]:
        providers: set[str] = set()
        if self.agents_dir.exists():
            for path in self.agents_dir.iterdir():
                if path.is_dir():
                    providers.add(path.name)
        legacy_cursor = self.data_dir / "cursor"
        if legacy_cursor.is_dir():
            providers.add("cursor")
        return sorted(providers)

    @property
    def cursor_raw_dir(self) -> Path:
        return self.resolved_agent_raw_dir("cursor")

    @property
    def cursor_parsed_dir(self) -> Path:
        return self.resolved_agent_parsed_dir("cursor")

    @property
    def wiki_corpus_dir(self) -> Path:
        return self.data_dir / "corpus" / "wiki"

    @property
    def books_path(self) -> Path:
        return self.data_dir / "books" / "books.json"

    @property
    def chats_dir(self) -> Path:
        return self.data_dir / "chats"

    @property
    def shell_workspace_dir(self) -> Path:
        return self.data_dir / "shell_workspace"

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
    def config_db_path(self) -> Path:
        from membrane.config_store import config_db_path

        return config_db_path()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_persona() -> PersonaConfig:
    from membrane.config_store import NAMESPACE_PERSONA, ensure_config_db, load_config_raw

    ensure_config_db()
    raw = load_config_raw(NAMESPACE_PERSONA)
    if raw is None:
        return PersonaConfig()
    return PersonaConfig.model_validate(raw)


def save_persona(persona: PersonaConfig) -> Path:
    from membrane.config_store import NAMESPACE_PERSONA, save_config_raw

    return save_config_raw(NAMESPACE_PERSONA, persona.model_dump(mode="python"))


def ensure_data_layout(root: Path | None = None) -> None:
    settings = Settings(root=root or project_root())
    from membrane.config_store import ensure_config_db

    ensure_config_db()
    dirs = [
        settings.config_dir,
        settings.memory_dir,
        settings.memory_dir / "examples",
        settings.memory_dir / "proposed",
        settings.memory_dir / "approved",
        settings.whatsapp_raw_dir,
        settings.whatsapp_parsed_dir,
        settings.agents_dir,
        settings.agent_raw_dir("cursor"),
        settings.agent_parsed_dir("cursor"),
        settings.wiki_corpus_dir,
        settings.wiki_corpus_dir / "raw",
        settings.wiki_corpus_dir / "datasets",
        settings.chats_dir,
        settings.shell_workspace_dir,
        settings.books_path.parent,
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
