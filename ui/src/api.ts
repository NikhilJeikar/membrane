const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const body = JSON.parse(text) as { detail?: string };
      throw new Error(body.detail || text || res.statusText);
    } catch (err) {
      if (err instanceof Error && err.message !== text) {
        throw err;
      }
      throw new Error(text || res.statusText);
    }
  }
  return res.json() as Promise<T>;
}

export type Status = {
  ollama_ok: boolean;
  model_ready: boolean;
  ollama_model: string;
  extractor_model: string;
  pending_proposals: number;
  approved_archive: number;
  profile_count: number;
  preference_count: number;
  episode_count: number;
  tracked_entries: number;
  agent_sessions: number;
  stale_extract_agents: number;
  needs_parse: number;
  needs_extract: number;
  needs_train: number;
  chats: number;
  phase: string;
};

export type SourceQueueStats = {
  raw: number;
  parsed: number;
  needs_parse: number;
  needs_extract: number;
  needs_train: number;
  train_enabled: boolean;
};

export type IngestStats = {
  sources: Record<string, SourceQueueStats>;
  totals: {
    needs_parse: number;
    needs_extract: number;
    needs_train: number;
  };
};

export type PersonaLLM = {
  provider: string;
  base_url: string;
  model: string;
  extractor_model: string;
  temperature: number;
  timeout_seconds: number;
  max_retries: number;
  num_threads: number;
  parallel_requests: number;
  context_window: number;
};

export type PersonaServer = {
  host: string;
  port: number;
  token: string;
  parse_interval_seconds: number;
  auto_extract: boolean;
};

export type PersonaWebSearch = {
  enabled: boolean;
  max_results: number;
  timeout_seconds: number;
};

export type PersonaFirecrawl = {
  enabled: boolean;
  base_url: string;
  api_key: string;
  timeout_seconds: number;
  max_chars: number;
  scrape_in_chat: boolean;
  max_pages_in_chat: number;
};

export type PersonaShell = {
  enabled: boolean;
  timeout_seconds: number;
  max_output_chars: number;
  max_commands_per_turn: number;
  workspace_dir: string;
  allow_network: boolean;
};

export type Persona = {
  identity: Record<string, string>;
  style: Record<string, unknown>;
  memory: Record<string, unknown>;
  boundaries: Record<string, unknown>;
  llm: PersonaLLM;
  performance: Record<string, unknown>;
  server: PersonaServer;
  web_search: PersonaWebSearch;
  firecrawl: PersonaFirecrawl;
  shell: PersonaShell;
  self_names: string[];
};

export type ServerStatus = {
  host: string;
  port: number;
  parse_interval_seconds: number;
  auto_extract: boolean;
  token: string;
  sources: Record<string, { raw: number; parsed: number }>;
};

export type Proposal = {
  id: string;
  category: string;
  status: string;
  source: string;
  reason: string;
  created_at: string;
  summary: string;
  detail: Record<string, unknown>;
  existing_note: string | null;
};

export type SourcePolicy = {
  ingest: boolean;
  extract: boolean;
  train: boolean;
  auto_approve_episodes: boolean;
  auto_approve_profile: boolean;
  auto_approve_preference: boolean;
  redact: boolean;
  self_only: boolean;
  user_only: boolean;
};

export type ProfileEntry = {
  id: string;
  key: string;
  value: string;
  confidence: number;
  source: string;
  updated_at: string;
  evidence: string[];
};

export type PreferenceEntry = {
  id: string;
  key: string;
  value: string;
  strength: number;
  source: string;
  updated_at: string;
  evidence: string[];
};

export type MemorySnapshot = {
  profile: ProfileEntry[];
  preferences: PreferenceEntry[];
  episodes: Array<{ id: string; summary: string; tags: string[] }>;
};

export type ProfileUpsert = {
  key: string;
  value: string;
  confidence?: number;
};

export type PreferenceUpsert = {
  key: string;
  value: string;
  strength?: number;
};

export type TrainingPolicy = {
  phase: string;
  nightly: { enabled: boolean; time: string; since_hours: number };
  sources: Record<string, SourcePolicy>;
};

export type PolicyCapabilities = {
  sources: Record<string, string[]>;
  descriptions: Record<string, string>;
};

export type CredentialField = {
  key: string;
  label: string;
  secret: boolean;
  placeholder: string;
  helper: string;
  oauth_only: boolean;
};

export type ToolCredentials = {
  fields: CredentialField[];
  values: Record<string, string>;
  connected: boolean;
  has_stored: boolean;
};

export type CredentialsCatalog = {
  tools: Record<string, ToolCredentials>;
  oauth_providers: { id: string; tool_id: string; label: string; requires: string[] }[];
};

export type McpServer = {
  id: string;
  name: string;
  enabled: boolean;
  command: string;
  args: string[];
  env: Record<string, string>;
  description: string;
  built_in: boolean;
};

export type ToolIntegration = {
  id: string;
  name: string;
  enabled: boolean;
  connected: boolean;
  category: string;
  description: string;
  setup_hint: string;
  via: string;
};

export type FineTuneConfig = {
  base_model: string;
  output_model: string;
  hf_base_model: string;
  include_chats: boolean;
  enrich_from_web: boolean;
  fetch_search_pages: boolean;
  max_pages_per_query: number;
  epochs: number;
  learning_rate: number;
  lora_rank: number;
  lora_alpha: number;
  batch_size: number;
  gradient_accumulation_steps: number;
  max_seq_length: number;
  set_as_chat_model: boolean;
  last_export_at: string | null;
  last_run_at: string | null;
  status: string;
  status_message: string;
  progress_pct: number;
  train_step: number;
  train_total_steps: number;
  train_epoch: number;
  last_error: string | null;
};

export type IntegrationsConfig = {
  mcp_servers: McpServer[];
  tools: ToolIntegration[];
  fine_tune: FineTuneConfig;
  summary: {
    mcp_enabled: number;
    mcp_total: number;
    tools_enabled: number;
    tools_connected: number;
    tools_total: number;
  };
};

export type TrainingExport = {
  name: string;
  size_bytes: number;
  modified_at: string;
};

export type TrainingStatus = {
  needs_train: number;
  chat_model: string;
  extractor_model: string;
  fine_tune: FineTuneConfig;
  fine_tune_running: boolean;
  training_available: boolean;
  training_requirements: string;
  exports: TrainingExport[];
  nightly_enabled: boolean;
  sft_sources: SftSourceStats;
};

export type SftSourceStats = {
  ui_sessions: number;
  agent_sessions: number;
  total_sessions: number;
  chat_examples: number;
  memory_examples: number;
  book_examples: number;
  web_examples: number;
  total_examples: number;
  include_chats: boolean;
  enrich_from_web: boolean;
  fetch_search_pages: boolean;
};

export type BookEntry = {
  id: string;
  title: string;
  author: string;
  rating: number | null;
  notes: string;
  read_year: number | null;
  added_at: string;
  episode_id: string | null;
};

export type BookUpsert = {
  title: string;
  author?: string;
  rating?: number | null;
  notes?: string;
  read_year?: number | null;
};

export type ChatTurn = {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string | null;
  metadata?: TurnReferences;
};

export type MemoryContextEntry = {
  key?: string;
  value?: string;
  summary?: string;
  tags?: string[];
  date?: string | null;
};

export type MemoryContext = {
  profile: MemoryContextEntry[];
  preferences: MemoryContextEntry[];
  episodes: MemoryContextEntry[];
};

export type ShellCommandResult = {
  command: string;
  exit_code?: number | null;
  blocked?: boolean;
  timed_out?: boolean;
  stdout?: string;
  stderr?: string;
};

export type TurnReferences = {
  memory_context?: MemoryContext;
  web_search?: {
    query: string;
    results: { title: string; url: string }[];
  };
  shell?: {
    commands: ShellCommandResult[];
  };
};

export type ChatSession = {
  id: string;
  turns: ChatTurn[];
  metadata: Record<string, unknown>;
};

export type ChatSessionSummary = {
  id: string;
  turns: number;
  preview: string;
  updated_at: string | null;
  include_in_training: boolean;
};

export type ContextUsage = {
  estimated_tokens: number;
  system_base_tokens: number;
  memory_tokens: number;
  system_tokens: number;
  tools_tokens: number;
  tools_breakdown: Record<string, number>;
  conversation_tokens: number;
  draft_tokens: number;
  context_limit: number;
  remaining_tokens: number;
  usage_percent: number;
  include_in_training?: boolean;
  session_turns?: number;
};

export type WebSearchEvent = {
  status: "searching" | "done";
  query: string;
  results?: { title: string; url: string }[];
};

export type ShellEvent = {
  status: "running" | "done";
  command?: string;
  commands?: ShellCommandResult[];
};

type ChatStreamLine =
  | { delta: string }
  | { error: string }
  | { context: MemoryContext }
  | { context_usage: ContextUsage }
  | { web_search: WebSearchEvent }
  | { shell: ShellEvent }
  | { done: true; reply: string; session: ChatSession };

async function streamChatMessage(
  id: string,
  content: string,
  onDelta: (delta: string) => void,
  onSearch?: (event: WebSearchEvent) => void,
  onContext?: (context: MemoryContext) => void,
  onContextUsage?: (usage: ContextUsage) => void,
  onShell?: (event: ShellEvent) => void
): Promise<{ session: ChatSession; reply: string }> {
  const res = await fetch(`${BASE}/api/chat/sessions/${id}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    try {
      const body = JSON.parse(text) as { detail?: string };
      throw new Error(body.detail || text || res.statusText);
    } catch (err) {
      if (err instanceof Error && err.message !== text) throw err;
      throw new Error(text || res.statusText);
    }
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: { session: ChatSession; reply: string } | null = null;

  const handleLine = (line: string) => {
    if (!line.trim()) return;
    const data = JSON.parse(line) as ChatStreamLine;
    if ("error" in data) throw new Error(data.error);
    if ("web_search" in data) {
      onSearch?.(data.web_search);
    } else if ("shell" in data) {
      onShell?.(data.shell);
    } else if ("context" in data) {
      onContext?.(data.context);
    } else if ("context_usage" in data) {
      onContextUsage?.(data.context_usage);
    } else if ("done" in data) {
      final = { session: data.session, reply: data.reply };
    } else {
      onDelta(data.delta);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) handleLine(line);
  }
  handleLine(buffer);

  if (!final) throw new Error("Chat stream ended unexpectedly");
  return final;
}

export const api = {
  status: () => request<Status>("/api/status"),
  memorySnapshot: () => request<MemorySnapshot>("/api/memory/snapshot"),
  upsertProfile: (body: ProfileUpsert) =>
    request<ProfileEntry>("/api/memory/profile", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteProfile: (key: string) =>
    request<{ deleted: string }>(`/api/memory/profile/${encodeURIComponent(key)}`, {
      method: "DELETE",
    }),
  upsertPreference: (body: PreferenceUpsert) =>
    request<PreferenceEntry>("/api/memory/preferences", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deletePreference: (key: string) =>
    request<{ deleted: string }>(`/api/memory/preferences/${encodeURIComponent(key)}`, {
      method: "DELETE",
    }),
  proposed: (category?: string) =>
    request<{ total: number; items: Proposal[] }>(
      `/api/memory/proposed${category ? `?category=${category}` : ""}`
    ),
  approve: (id: string) =>
    request<Proposal>(`/api/memory/proposed/${id}/approve`, { method: "POST" }),
  reject: (id: string) =>
    request<Proposal>(`/api/memory/proposed/${id}/reject`, { method: "POST" }),
  approveAll: () =>
    request<{ count: number }>("/api/memory/proposed/approve-all", { method: "POST" }),
  ingestStats: () => request<IngestStats>("/api/ingest/stats"),
  getPersona: () => request<Persona>("/api/persona"),
  putPersona: (body: {
    llm?: Partial<PersonaLLM>;
    performance?: { workers?: number };
    memory?: Record<string, unknown>;
    style?: Record<string, unknown>;
    boundaries?: Record<string, unknown>;
    identity?: Record<string, string>;
    self_names?: string[];
    server?: Partial<PersonaServer>;
    web_search?: Partial<PersonaWebSearch>;
    firecrawl?: Partial<PersonaFirecrawl>;
    shell?: Partial<PersonaShell>;
  }) =>
    request<Persona>("/api/persona", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  ollamaModels: () => request<{ models: string[]; ollama_ok: boolean }>("/api/ollama/models"),
  parseIngest: (source = "all") =>
    request<Record<string, { processed: number; skipped: number }>>("/api/ingest/parse", {
      method: "POST",
      body: JSON.stringify({ source, force: false }),
    }),
  serverStatus: () => request<ServerStatus>("/api/server/status"),
  getPolicy: () => request<TrainingPolicy>("/api/policy"),
  getPolicyCapabilities: () => request<PolicyCapabilities>("/api/policy/capabilities"),
  putPolicy: (policy: TrainingPolicy) =>
    request<TrainingPolicy>("/api/policy", {
      method: "PUT",
      body: JSON.stringify(policy),
    }),
  listBooks: () => request<{ items: BookEntry[] }>("/api/books"),
  addBook: (body: BookUpsert) =>
    request<BookEntry>("/api/books", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateBook: (id: string, body: BookUpsert) =>
    request<BookEntry>(`/api/books/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteBook: (id: string) =>
    request<{ deleted: string }>(`/api/books/${id}`, { method: "DELETE" }),
  listChatSessions: () => request<{ items: ChatSessionSummary[] }>("/api/chat/sessions"),
  createChatSession: () =>
    request<ChatSession>("/api/chat/sessions", { method: "POST" }),
  getChatSession: (id: string) => request<ChatSession>(`/api/chat/sessions/${id}`),
  getChatContextUsage: (id: string, draft = "") =>
    request<ContextUsage>(
      `/api/chat/sessions/${encodeURIComponent(id)}/context-usage?draft=${encodeURIComponent(draft)}`
    ),
  patchChatSession: (id: string, body: { include_in_training?: boolean }) =>
    request<ChatSession>(`/api/chat/sessions/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteChatSession: (id: string) =>
    request<{ deleted: string }>(`/api/chat/sessions/${id}`, { method: "DELETE" }),
  sendChatMessage: streamChatMessage,
  getIntegrations: () => request<IntegrationsConfig>("/api/integrations"),
  getIntegrationCredentials: () => request<CredentialsCatalog>("/api/integrations/credentials"),
  putIntegrationCredentials: (toolId: string, values: Record<string, string>) =>
    request<ToolCredentials>(`/api/integrations/credentials/${encodeURIComponent(toolId)}`, {
      method: "PUT",
      body: JSON.stringify({ values }),
    }),
  deleteIntegrationCredentials: (toolId: string) =>
    request<{ deleted: string }>(`/api/integrations/credentials/${encodeURIComponent(toolId)}`, {
      method: "DELETE",
    }),
  oauthAuthorizeUrl: (provider: string) => `/api/oauth/${encodeURIComponent(provider)}/authorize`,
  putIntegrations: (body: {
    mcp_servers?: McpServer[];
    tools?: ToolIntegration[];
    fine_tune?: FineTuneConfig;
  }) =>
    request<IntegrationsConfig>("/api/integrations", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  trainingStatus: () => request<TrainingStatus>("/api/training/status"),
  trainingExport: (kind: "sft" | "dpo" | "all" = "sft") =>
    request<{ paths: Record<string, string>; fine_tune: FineTuneConfig }>("/api/training/export", {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),
  trainingFineTune: (body: { base_model?: string; output_model?: string }) =>
    request<{
      status: string;
      message: string;
      fine_tune: FineTuneConfig;
    }>("/api/training/fine-tune", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
