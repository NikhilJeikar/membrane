"""MCP servers and life-integration tools configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from membrane.integrations.credentials import tool_connection_status


class McpServerConfig(BaseModel):
    id: str
    name: str
    enabled: bool = False
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    built_in: bool = False


class ToolIntegrationConfig(BaseModel):
    id: str
    name: str
    enabled: bool = False
    category: str = "productivity"
    description: str = ""
    setup_hint: str = ""
    via: str = "oauth"


class FineTuneConfig(BaseModel):
    base_model: str = ""
    output_model: str = "membrane-pa:latest"
    hf_base_model: str = Field(
        default="",
        description="Optional Hugging Face model override when the Ollama tag is unmapped.",
    )
    include_chats: bool = Field(
        default=True,
        description="Include membrane and agent chat sessions in SFT export.",
    )
    enrich_from_web: bool = Field(
        default=False,
        description="During export, search the web when a turn needs external facts.",
    )
    fetch_search_pages: bool = Field(
        default=True,
        description="Fetch full page text for search result URLs and add to training rows.",
    )
    max_pages_per_query: int = Field(default=3, ge=1, le=5)
    epochs: int = Field(default=1, ge=1, le=10)
    learning_rate: float = Field(default=2e-4, gt=0)
    lora_rank: int = Field(default=16, ge=4, le=128)
    lora_alpha: int = Field(default=32, ge=8, le=256)
    batch_size: int = Field(default=2, ge=1, le=16)
    gradient_accumulation_steps: int = Field(default=4, ge=1, le=32)
    max_seq_length: int = Field(default=2048, ge=512, le=8192)
    set_as_chat_model: bool = Field(
        default=True,
        description="After training, set the output model as the persona chat model.",
    )
    last_export_at: str | None = None
    last_run_at: str | None = None
    status: str = "idle"
    status_message: str = ""
    progress_pct: int = Field(default=0, ge=0, le=100)
    train_step: int = Field(default=0, ge=0)
    train_total_steps: int = Field(default=0, ge=0)
    train_epoch: int = Field(default=0, ge=0)
    last_error: str | None = None


class IntegrationsConfig(BaseModel):
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    tools: list[ToolIntegrationConfig] = Field(default_factory=list)
    fine_tune: FineTuneConfig = Field(default_factory=FineTuneConfig)

    @classmethod
    def default(cls) -> IntegrationsConfig:
        return cls(
            mcp_servers=_DEFAULT_MCP_SERVERS,
            tools=_DEFAULT_TOOLS,
        )


_DEFAULT_MCP_SERVERS: list[McpServerConfig] = [
    McpServerConfig(
        id="cursor-ide-browser",
        name="Browser automation",
        description="Chrome DevTools automation for web tasks and testing.",
        built_in=True,
    ),
    McpServerConfig(
        id="filesystem",
        name="Filesystem",
        description="Read and write local files within allowed directories.",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/home"],
    ),
    McpServerConfig(
        id="github",
        name="GitHub",
        description="Issues, pull requests, and repository search via GitHub API.",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
    ),
    McpServerConfig(
        id="google-drive",
        name="Google Drive",
        description="Search and read Google Drive documents.",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-gdrive"],
    ),
    McpServerConfig(
        id="postgres",
        name="PostgreSQL",
        description="Query a PostgreSQL database with read-only SQL.",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres"],
        env={"DATABASE_URL": ""},
    ),
    McpServerConfig(
        id="slack",
        name="Slack",
        description="Channels, messages, and workspace search.",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env={"SLACK_BOT_TOKEN": ""},
    ),
]

_DEFAULT_TOOLS: list[ToolIntegrationConfig] = [
    ToolIntegrationConfig(
        id="google",
        name="Google",
        category="productivity",
        description="Gmail, Calendar, Drive, and Contacts.",
        setup_hint="Click Connect to enter credentials or sign in with Google.",
        via="oauth",
    ),
    ToolIntegrationConfig(
        id="github",
        name="GitHub",
        category="dev",
        description="Repos, issues, PRs, and notifications.",
        setup_hint="Click Connect to paste a PAT or sign in with GitHub.",
        via="oauth",
    ),
    ToolIntegrationConfig(
        id="linkedin",
        name="LinkedIn",
        category="social",
        description="Profile, connections, and messaging (where API allows).",
        setup_hint="Click Connect to enter app credentials or sign in.",
        via="oauth",
    ),
    ToolIntegrationConfig(
        id="instagram",
        name="Instagram",
        category="social",
        description="Media and insights via Meta Graph API.",
        setup_hint="Click Connect to paste your Meta/Instagram access token.",
        via="oauth",
    ),
    ToolIntegrationConfig(
        id="twitter",
        name="X (Twitter)",
        category="social",
        description="Timeline, bookmarks, and post drafts.",
        setup_hint="Click Connect to paste bearer token or API keys.",
        via="oauth",
    ),
    ToolIntegrationConfig(
        id="slack",
        name="Slack",
        category="productivity",
        description="Workspace messages and channels.",
        setup_hint="Click Connect to paste your Slack bot token.",
        via="oauth",
    ),
    ToolIntegrationConfig(
        id="notion",
        name="Notion",
        category="productivity",
        description="Pages, databases, and notes.",
        setup_hint="Click Connect to paste your Notion integration token.",
        via="oauth",
    ),
    ToolIntegrationConfig(
        id="web_search",
        name="Web search",
        category="built_in",
        description="DuckDuckGo search during chat (configured in config database).",
        setup_hint="Toggle under Tools → Model or enable web_search in config.",
        via="built_in",
    ),
    ToolIntegrationConfig(
        id="shell",
        name="Shell commands",
        category="built_in",
        description="Run Linux commands in a bubblewrap sandbox during chat (sudo blocked).",
        setup_hint="Requires bubblewrap (bwrap). Toggle under Tools → Model or enable shell in config.",
        via="built_in",
    ),
    ToolIntegrationConfig(
        id="whatsapp",
        name="WhatsApp",
        category="messaging",
        description="Chat export ingest via CLI.",
        setup_hint="membrane ingest whatsapp <export.txt>",
        via="cli",
    ),
    ToolIntegrationConfig(
        id="email",
        name="Email",
        category="productivity",
        description="Push email JSON to the local ingest server.",
        setup_hint="POST /v1/ingest/email on the ingest server.",
        via="ingest_server",
    ),
    ToolIntegrationConfig(
        id="calendar",
        name="Calendar",
        category="productivity",
        description="Push calendar events to the local ingest server.",
        setup_hint="POST /v1/ingest/calendar on the ingest server.",
        via="ingest_server",
    ),
]


def _merge_catalog(
    saved: list[McpServerConfig] | list[ToolIntegrationConfig],
    defaults: list[McpServerConfig] | list[ToolIntegrationConfig],
) -> list:
    by_id = {item.id: item for item in saved}
    merged = []
    for default in defaults:
        if default.id in by_id:
            merged.append(default.model_copy(update=by_id[default.id].model_dump()))
        else:
            merged.append(default)
    for item in saved:
        if item.id not in {d.id for d in defaults}:
            merged.append(item)
    return merged


def load_integrations() -> IntegrationsConfig:
    from membrane.config_store import NAMESPACE_INTEGRATIONS, ensure_config_db, load_config_raw

    defaults = IntegrationsConfig.default()
    ensure_config_db()
    raw = load_config_raw(NAMESPACE_INTEGRATIONS)
    if raw is None:
        return defaults
    mcp_saved = [McpServerConfig.model_validate(x) for x in raw.get("mcp_servers", [])]
    tools_saved = [ToolIntegrationConfig.model_validate(x) for x in raw.get("tools", [])]
    fine_tune_raw = raw.get("fine_tune") or {}
    fine_tune = FineTuneConfig.model_validate(fine_tune_raw) if fine_tune_raw else defaults.fine_tune
    return IntegrationsConfig(
        mcp_servers=_merge_catalog(mcp_saved, defaults.mcp_servers),
        tools=_merge_catalog(tools_saved, defaults.tools),
        fine_tune=fine_tune,
    )


def save_integrations(config: IntegrationsConfig) -> Path:
    from membrane.config_store import NAMESPACE_INTEGRATIONS, save_config_raw

    return save_config_raw(NAMESPACE_INTEGRATIONS, config.model_dump(mode="python"))


def integrations_status(config: IntegrationsConfig | None = None) -> dict:
    cfg = config or load_integrations()
    tools = []
    for tool in cfg.tools:
        tools.append(
            {
                **tool.model_dump(),
                "connected": tool_connection_status(tool.id),
            }
        )
    enabled_mcp = sum(1 for s in cfg.mcp_servers if s.enabled)
    enabled_tools = sum(1 for t in cfg.tools if t.enabled)
    connected_tools = sum(1 for t in tools if t["connected"])
    return {
        "mcp_servers": [s.model_dump() for s in cfg.mcp_servers],
        "tools": tools,
        "fine_tune": cfg.fine_tune.model_dump(),
        "summary": {
            "mcp_enabled": enabled_mcp,
            "mcp_total": len(cfg.mcp_servers),
            "tools_enabled": enabled_tools,
            "tools_connected": connected_tools,
            "tools_total": len(cfg.tools),
        },
    }
