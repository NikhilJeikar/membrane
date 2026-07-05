import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CheckCircle2,
  Bot,
  Cable,
  Download,
  ExternalLink,
  Loader2,
  Plug,
  Save,
  Sparkles,
  Trash2,
  Wrench,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import {
  ModelAdvancedPanel,
  PersonaBehaviorPanel,
  PersonaTabIcon,
  WebToolsPanel,
} from "../components/PersonaSettingsPanels";
import { Button } from "../components/ui/Button";
import { Card, SectionTitle } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Spinner } from "../components/ui/Spinner";
import { Switch } from "../components/ui/Switch";
import { Table, TBody, TD, TH, THead, TR } from "../components/ui/Table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/Tabs";
import { Tag } from "../components/ui/Tag";
import { useToast } from "../components/ui/Toast";
import {
  api,
  CredentialsCatalog,
  FineTuneConfig,
  IntegrationsConfig,
  McpServer,
  ToolCredentials,
  ToolIntegration,
  TrainingStatus,
  Persona,
} from "../api";

const CATEGORY_LABELS: Record<string, string> = {
  productivity: "Productivity",
  social: "Social",
  dev: "Developer",
  messaging: "Messaging",
  built_in: "Built-in",
};

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const FINE_TUNE_STEPS = [
  { id: "export", label: "Export data", statuses: ["queued", "exporting"] },
  { id: "train", label: "Train LoRA", statuses: ["training"] },
  { id: "register", label: "Register in Ollama", statuses: ["registering"] },
  { id: "done", label: "Complete", statuses: ["ready"] },
] as const;

const FINE_TUNE_ACTIVE = new Set(["queued", "exporting", "training", "registering"]);

function fineTuneStepPhase(fineTune: FineTuneConfig): number {
  const { status, progress_pct } = fineTune;
  if (status === "ready") return FINE_TUNE_STEPS.length;
  if (status === "failed") {
    if (progress_pct < 20) return 0;
    if (progress_pct < 85) return 1;
    return 2;
  }
  const idx = FINE_TUNE_STEPS.findIndex((step) =>
    (step.statuses as readonly string[]).includes(status)
  );
  return idx >= 0 ? idx : -2;
}

function FineTuneProgressPanel({
  fineTune,
  running,
}: {
  fineTune: FineTuneConfig;
  running: boolean;
}) {
  const active = running || FINE_TUNE_ACTIVE.has(fineTune.status);
  const visible = active || fineTune.status === "ready" || fineTune.status === "failed";
  if (!visible) return null;

  const phase = fineTuneStepPhase(fineTune);
  const pct = Math.max(0, Math.min(100, fineTune.progress_pct));

  return (
    <Card className="mb-4 border-accent/20 bg-accent/5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <SectionTitle className="mb-1">Fine-tune progress</SectionTitle>
          <p className="text-[13px] text-ink-secondary">
            {fineTune.status_message || "Waiting to start…"}
          </p>
        </div>
        {active && <Loader2 className="h-5 w-5 shrink-0 animate-spin text-accent" />}
        {fineTune.status === "ready" && !active && (
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />
        )}
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between text-xs text-ink-muted">
          <span className="capitalize">{fineTune.status.replace(/_/g, " ")}</span>
          <span className="tabular-nums font-medium text-ink-secondary">{pct}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              fineTune.status === "failed" ? "bg-red-500" : "bg-accent"
            }`}
            style={{ width: `${active || fineTune.status === "ready" ? Math.max(pct, active ? 8 : pct) : pct}%` }}
          />
        </div>
      </div>

      {fineTune.train_total_steps > 0 && (
        <p className="mt-2 text-xs tabular-nums text-ink-muted">
          Epoch {fineTune.train_epoch}/{fineTune.epochs || 1} · step{" "}
          {fineTune.train_step}/{fineTune.train_total_steps}
        </p>
      )}

      <ol className="mt-4 grid gap-2 sm:grid-cols-4">
        {FINE_TUNE_STEPS.map((step, index) => {
          const done = phase > index || fineTune.status === "ready";
          const current = phase === index && active;
          const failed = fineTune.status === "failed" && phase === index;
          return (
            <li
              key={step.id}
              className={`rounded-lg border px-3 py-2 text-xs ${
                failed
                  ? "border-red-500/30 bg-red-500/10 text-red-300"
                  : done
                    ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-300"
                    : current
                      ? "border-accent/40 bg-accent/10 text-ink-primary"
                      : "border-white/10 bg-white/[0.02] text-ink-muted"
              }`}
            >
              <div className="font-medium">{step.label}</div>
              {current && active && <div className="mt-0.5 text-[11px] opacity-80">In progress</div>}
              {done && !current && <div className="mt-0.5 text-[11px] opacity-80">Done</div>}
              {failed && <div className="mt-0.5 text-[11px] opacity-80">Failed</div>}
            </li>
          );
        })}
      </ol>

      {fineTune.last_error && (
        <p className="mt-3 rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {fineTune.last_error}
        </p>
      )}

      {fineTune.status === "ready" && fineTune.last_run_at && (
        <p className="mt-3 text-xs text-ink-muted">
          Finished {new Date(fineTune.last_run_at).toLocaleString()}
          {fineTune.output_model ? ` · model ${fineTune.output_model}` : ""}
        </p>
      )}
    </Card>
  );
}

export default function ToolsPage() {
  const [integrations, setIntegrations] = useState<IntegrationsConfig | null>(null);
  const [credentials, setCredentials] = useState<CredentialsCatalog | null>(null);
  const [training, setTraining] = useState<TrainingStatus | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaOk, setOllamaOk] = useState(false);
  const [chatModel, setChatModel] = useState("");
  const [extractorModel, setExtractorModel] = useState("");
  const [persona, setPersona] = useState<Persona | null>(null);
  const [fineTune, setFineTune] = useState<FineTuneConfig | null>(null);
  const [connectTool, setConnectTool] = useState<ToolIntegration | null>(null);
  const [credentialDraft, setCredentialDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [savingCredentials, setSavingCredentials] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [fineTuning, setFineTuning] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const toast = useToast();
  const notifiedStatusRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    const [integ, creds, train, models, persona] = await Promise.all([
      api.getIntegrations(),
      api.getIntegrationCredentials(),
      api.trainingStatus(),
      api.ollamaModels(),
      api.getPersona(),
    ]);
    setCredentials(creds);
    setTraining(train);
    setOllamaModels(models.models);
    setOllamaOk(models.ollama_ok);
    setChatModel(persona.llm.model);
    setExtractorModel(persona.llm.extractor_model);
    setPersona(persona);
    setIntegrations({
      ...integ,
      tools: integ.tools.map((tool) =>
        tool.id === "shell"
          ? { ...tool, enabled: Boolean(persona.shell?.enabled) }
          : tool.id === "web_search"
            ? { ...tool, enabled: Boolean(persona.web_search?.enabled) }
            : tool
      ),
    });
    setFineTune(train.fine_tune);
  }, []);

  useEffect(() => {
    load().catch(console.error);
  }, [load]);

  useEffect(() => {
    const running =
      training?.fine_tune_running ||
      FINE_TUNE_ACTIVE.has(training?.fine_tune.status ?? "");
    if (!running) return;

    const poll = () => {
      api
        .trainingStatus()
        .then((train) => {
          setTraining(train);
          setFineTune(train.fine_tune);
          if (train.fine_tune.status === "ready" && notifiedStatusRef.current !== "ready") {
            notifiedStatusRef.current = "ready";
            setChatModel(train.chat_model);
            toast("success", "Fine-tune complete", train.fine_tune.status_message);
          }
          if (train.fine_tune.status === "failed" && notifiedStatusRef.current !== "failed") {
            notifiedStatusRef.current = "failed";
            toast(
              "error",
              "Fine-tune failed",
              train.fine_tune.last_error ?? train.fine_tune.status_message
            );
          }
        })
        .catch(console.error);
    };

    poll();
    const timer = window.setInterval(poll, 1500);
    return () => window.clearInterval(timer);
  }, [training?.fine_tune_running, training?.fine_tune.status, toast]);

  useEffect(() => {
    const connected = searchParams.get("connected");
    if (!connected) return;
    toast("success", "Connected", `${connected} account linked successfully`);
    setSearchParams({}, { replace: true });
    load().catch(console.error);
  }, [searchParams, setSearchParams, toast, load]);

  if (!integrations || !credentials || !training || !fineTune || !persona) {
    return <Spinner label="Loading model, MCP, and tools…" />;
  }

  function personaPayload() {
    if (!persona) return {};
    return {
      llm: {
        model: chatModel,
        extractor_model: extractorModel,
        base_url: persona.llm.base_url,
        temperature: persona.llm.temperature,
        timeout_seconds: persona.llm.timeout_seconds,
        max_retries: persona.llm.max_retries,
        num_threads: persona.llm.num_threads,
        parallel_requests: persona.llm.parallel_requests,
        context_window: persona.llm.context_window,
        thinking_enabled: persona.llm.thinking_enabled,
      },
      performance: { workers: Number(persona.performance?.workers ?? 0) },
      memory: persona.memory,
      style: persona.style,
      boundaries: persona.boundaries,
      identity: persona.identity,
      self_names: persona.self_names,
      web_search: persona.web_search,
      firecrawl: persona.firecrawl,
      shell: persona.shell,
    };
  }

  async function savePersonaSettings() {
    setSaving(true);
    try {
      const updated = await api.putPersona(personaPayload());
      setPersona(updated);
      setChatModel(updated.llm.model);
      setExtractorModel(updated.llm.extractor_model);
      toast("success", "Persona settings saved", "Config database updated");
    } catch (e) {
      toast("error", "Failed to save persona settings", String(e));
    } finally {
      setSaving(false);
    }
  }

  const modelOptions = (current: string) => {
    const opts = ollamaModels.map((m) => ({ value: m, label: m }));
    if (current && !ollamaModels.includes(current)) {
      opts.unshift({ value: current, label: `${current} (configured)` });
    }
    return opts.length ? opts : [{ value: current, label: current || "No models" }];
  };

  function updateMcp(id: string, enabled: boolean) {
    setIntegrations((prev) =>
      prev
        ? {
            ...prev,
            mcp_servers: prev.mcp_servers.map((s) => (s.id === id ? { ...s, enabled } : s)),
          }
        : prev
    );
  }

  function updateTool(id: string, enabled: boolean) {
    setIntegrations((prev) =>
      prev
        ? {
            ...prev,
            tools: prev.tools.map((t) => (t.id === id ? { ...t, enabled } : t)),
          }
        : prev
    );
    if (id === "shell") {
      setPersona((prev) =>
        prev ? { ...prev, shell: { ...prev.shell, enabled } } : prev
      );
    } else if (id === "web_search") {
      setPersona((prev) =>
        prev ? { ...prev, web_search: { ...prev.web_search, enabled } } : prev
      );
    }
  }

  function updateMcpEnv(id: string, envKey: string, value: string) {
    setIntegrations((prev) =>
      prev
        ? {
            ...prev,
            mcp_servers: prev.mcp_servers.map((s) =>
              s.id === id ? { ...s, env: { ...s.env, [envKey]: value } } : s
            ),
          }
        : prev
    );
  }

  function updateMcpField(id: string, patch: Partial<McpServer>) {
    setIntegrations((prev) =>
      prev
        ? {
            ...prev,
            mcp_servers: prev.mcp_servers.map((s) => (s.id === id ? { ...s, ...patch } : s)),
          }
        : prev
    );
  }

  function openConnect(tool: ToolIntegration) {
    if (!credentials) return;
    const schema = credentials.tools[tool.id];
    const draft: Record<string, string> = {};
    if (schema) {
      for (const field of schema.fields) {
        if (!field.oauth_only) draft[field.key] = "";
      }
    }
    setCredentialDraft(draft);
    setConnectTool(tool);
  }

  async function saveCredentials() {
    if (!connectTool) return;
    setSavingCredentials(true);
    try {
      await api.putIntegrationCredentials(connectTool.id, credentialDraft);
      toast("success", "Credentials saved", "Stored in config database");
      await load();
    } catch (e) {
      toast("error", "Failed to save credentials", String(e));
    } finally {
      setSavingCredentials(false);
    }
  }

  async function clearCredentials() {
    if (!connectTool) return;
    setSavingCredentials(true);
    try {
      await api.deleteIntegrationCredentials(connectTool.id);
      setCredentialDraft({});
      toast("success", "Credentials cleared");
      await load();
    } catch (e) {
      toast("error", "Failed to clear credentials", String(e));
    } finally {
      setSavingCredentials(false);
    }
  }

  async function startOAuth(providerId: string) {
    if (!connectTool) return;
    setSavingCredentials(true);
    try {
      if (Object.keys(credentialDraft).length > 0) {
        await api.putIntegrationCredentials(connectTool.id, credentialDraft);
      }
      window.location.href = api.oauthAuthorizeUrl(providerId);
    } catch (e) {
      toast("error", "Could not start sign-in", String(e));
      setSavingCredentials(false);
    }
  }

  async function saveFineTuneOptions() {
    if (!fineTune) return;
    setSaving(true);
    try {
      await api.putIntegrations({ fine_tune: fineTune });
      await load();
      toast("success", "Training options saved");
    } catch (e) {
      toast("error", "Failed to save training options", String(e));
    } finally {
      setSaving(false);
    }
  }

  async function saveIntegrations() {
    if (!integrations || !fineTune) return;
    setSaving(true);
    try {
      const updated = await api.putIntegrations({
        mcp_servers: integrations.mcp_servers,
        tools: integrations.tools,
        fine_tune: fineTune,
      });
      setIntegrations(updated);
      if (persona) {
        const shellTool = integrations.tools.find((t) => t.id === "shell");
        const webTool = integrations.tools.find((t) => t.id === "web_search");
        const personaUpdated = await api.putPersona({
          shell: shellTool ? { enabled: shellTool.enabled } : undefined,
          web_search: webTool ? { enabled: webTool.enabled } : undefined,
        });
        setPersona(personaUpdated);
      }
      toast("success", "Integrations saved", "Config database updated");
    } catch (e) {
      toast("error", "Failed to save integrations", String(e));
    } finally {
      setSaving(false);
    }
  }

  async function saveModels() {
    await savePersonaSettings();
  }

  async function runExport(kind: "sft" | "dpo" | "all") {
    if (!fineTune) return;
    setExporting(kind);
    try {
      await api.putIntegrations({ fine_tune: fineTune });
      const result = await api.trainingExport(kind);
      setFineTune(result.fine_tune);
      toast("success", "Training data exported", Object.values(result.paths).join(", "));
      await load();
    } catch (e) {
      toast("error", "Export failed", String(e));
    } finally {
      setExporting(null);
    }
  }

  async function runFineTune() {
    if (!fineTune) return;
    setFineTuning(true);
    notifiedStatusRef.current = null;
    try {
      await api.putIntegrations({ fine_tune: fineTune });
      const result = await api.trainingFineTune({
        base_model: fineTune.base_model || chatModel,
        output_model: fineTune.output_model,
      });
      setFineTune(result.fine_tune);
      setTraining((prev) =>
        prev
          ? {
              ...prev,
              fine_tune: result.fine_tune,
              fine_tune_running: true,
            }
          : prev
      );
      toast("success", "Fine-tune started", result.message);
    } catch (e) {
      toast("error", "Fine-tune failed", String(e));
    } finally {
      setFineTuning(false);
    }
  }

  const fineTuneActive =
    training.fine_tune_running || FINE_TUNE_ACTIVE.has(fineTune.status);

  const summary = integrations.summary;

  return (
    <>
      <PageHeader
        title="Model, MCP & tools"
        description="Choose which Ollama models to run, enable MCP servers and life integrations, and export data for fine-tuning."
      />

      <div className="mb-6 flex flex-wrap gap-2">
        <Tag tone={ollamaOk ? "green" : "red"}>
          Ollama {ollamaOk ? "online" : "offline"}
        </Tag>
        <Tag tone="blue">
          {summary.mcp_enabled}/{summary.mcp_total} MCP enabled
        </Tag>
        <Tag tone="purple">
          {summary.tools_enabled}/{summary.tools_total} tools enabled
        </Tag>
        <Tag tone={summary.tools_connected > 0 ? "green" : "gray"}>
          {summary.tools_connected} connected
        </Tag>
        {training.needs_train > 0 && (
          <Tag tone="amber">{training.needs_train} samples in training backlog</Tag>
        )}
      </div>

      <Tabs defaultValue="model">
        <TabsList>
          <TabsTrigger value="model">
            <Bot className="mr-1.5 h-3.5 w-3.5" />
            Model
          </TabsTrigger>
          <TabsTrigger value="persona">
            <PersonaTabIcon />
            Persona
          </TabsTrigger>
          <TabsTrigger value="mcp">
            <Cable className="mr-1.5 h-3.5 w-3.5" />
            MCP
          </TabsTrigger>
          <TabsTrigger value="tools">
            <Plug className="mr-1.5 h-3.5 w-3.5" />
            Tools
          </TabsTrigger>
          <TabsTrigger value="training">
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            Fine-tuning
          </TabsTrigger>
        </TabsList>

        <TabsContent value="model">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card className="space-y-4">
              <SectionTitle>Ollama models</SectionTitle>
              <Select
                label="Chat model"
                helper="Used for chat, web search decisions, and interactive tasks."
                value={chatModel}
                options={modelOptions(chatModel)}
                onValueChange={setChatModel}
              />
              <Select
                label="Extractor model"
                helper="Used for offline memory extraction from ingested data."
                value={extractorModel}
                options={modelOptions(extractorModel)}
                onValueChange={setExtractorModel}
              />
              <Button
                icon={<Save className="h-4 w-4" />}
                onClick={saveModels}
                loading={saving}
              >
                Save model settings
              </Button>
            </Card>

            <Card>
              <SectionTitle className="mb-3">Installed models</SectionTitle>
              {ollamaModels.length === 0 ? (
                <p className="text-[13px] text-ink-muted">
                  {ollamaOk
                    ? "No models installed. Run ollama pull qwen2.5:3b"
                    : "Start Ollama with ollama serve, then pull models."}
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {ollamaModels.map((m) => (
                    <li
                      key={m}
                      className="flex items-center justify-between rounded-md border border-line px-3 py-2 text-[13px]"
                    >
                      <span className="font-mono">{m}</span>
                      <div className="flex gap-1">
                        {m === chatModel && <Tag tone="green">chat</Tag>}
                        {m === extractorModel && <Tag tone="blue">extract</Tag>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <ModelAdvancedPanel
              persona={persona}
              onChange={setPersona}
              onSave={savePersonaSettings}
              saving={saving}
            />

            <div className="space-y-4">
              <WebToolsPanel
                persona={persona}
                onChange={setPersona}
                onSave={savePersonaSettings}
                saving={saving}
                fetchSearchPages={fineTune.fetch_search_pages}
              />
              <Button icon={<Save className="h-4 w-4" />} onClick={savePersonaSettings} loading={saving}>
                Save web, shell & Firecrawl settings
              </Button>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="persona">
          <PersonaBehaviorPanel
            persona={persona}
            onChange={setPersona}
            onSave={savePersonaSettings}
            saving={saving}
          />
        </TabsContent>

        <TabsContent value="mcp">
          <Card className="mb-4 space-y-1">
            <p className="text-[13px] leading-5 text-ink-secondary">
              Model Context Protocol servers extend the assistant with tools like browsers,
              filesystems, and APIs. Enable servers and enter any required tokens below — saved
              to the config database (no shell env vars needed).
            </p>
          </Card>
          <div className="space-y-3">
            {integrations.mcp_servers.map((server) => (
              <McpCard
                key={server.id}
                server={server}
                onToggle={(enabled) => updateMcp(server.id, enabled)}
                onEnvChange={(key, value) => updateMcpEnv(server.id, key, value)}
                onFieldChange={(patch) => updateMcpField(server.id, patch)}
              />
            ))}
          </div>
          <div className="mt-5 flex gap-3">
            <Button
              icon={<Save className="h-4 w-4" />}
              onClick={saveIntegrations}
              loading={saving}
            >
              Save MCP settings
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="tools">
          <Card className="mb-4 space-y-1">
            <p className="text-[13px] leading-5 text-ink-secondary">
              Connect accounts directly in the UI — credentials are stored locally in
              config/membrane.db (gitignored). Use Connect to paste tokens or sign in with
              OAuth where supported.
            </p>
          </Card>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {integrations.tools.map((tool) => (
              <ToolCard
                key={tool.id}
                tool={tool}
                canConnect={Boolean(credentials.tools[tool.id])}
                onToggle={(enabled) => updateTool(tool.id, enabled)}
                onConnect={() => openConnect(tool)}
              />
            ))}
          </div>
          <div className="mt-5">
            <Button
              icon={<Save className="h-4 w-4" />}
              onClick={saveIntegrations}
              loading={saving}
            >
              Save tool settings
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="training">
          <FineTuneProgressPanel fineTune={fineTune} running={fineTuneActive} />

          <Card className="mb-4">
            <SectionTitle className="mb-2">Training data preview</SectionTitle>
            <p className="mb-3 text-[13px] leading-5 text-ink-secondary">
              Preview reflects your training options below. Chat rows use the system prompt per
              turn; web enrichment adds search snippets and fetched page content when enabled.
            </p>
            <div className="flex flex-wrap gap-2">
              {!training.sft_sources.include_chats && (
                <Tag tone="amber">Chats excluded</Tag>
              )}
              {training.sft_sources.include_chats && (
                <Tag tone="blue">{training.sft_sources.total_sessions} chat sessions</Tag>
              )}
              {training.sft_sources.include_chats && (
                <Tag tone="purple">{training.sft_sources.chat_examples} chat rows</Tag>
              )}
              {training.sft_sources.web_examples > 0 && (
                <Tag tone="blue">{training.sft_sources.web_examples} web page rows</Tag>
              )}
              <Tag tone="gray">
                {training.sft_sources.memory_examples + training.sft_sources.book_examples} memory/book rows
              </Tag>
              <Tag tone="green">{training.sft_sources.total_examples} total SFT rows</Tag>
            </div>
            {training.sft_sources.enrich_from_web && (
              <p className="mt-2 text-xs text-ink-muted">
                Web enrichment on — searches and fetches pages when export runs (requires network).
              </p>
            )}
            {(training.sft_sources.ui_sessions > 0 || training.sft_sources.agent_sessions > 0) &&
              training.sft_sources.include_chats && (
              <p className="mt-2 text-xs text-ink-muted">
                {training.sft_sources.ui_sessions} membrane chat session
                {training.sft_sources.ui_sessions !== 1 ? "s" : ""}
                {training.sft_sources.agent_sessions > 0 &&
                  ` · ${training.sft_sources.agent_sessions} agent transcript${training.sft_sources.agent_sessions !== 1 ? "s" : ""}`}
              </p>
            )}
          </Card>

          <Card className="mb-4 space-y-4">
            <SectionTitle>Training options</SectionTitle>
            <Switch
              label="Include chat sessions"
              helper="Membrane UI chats and agent transcripts (Cursor, Claude, OpenAI)."
              checked={fineTune.include_chats}
              onCheckedChange={(checked) =>
                setFineTune((prev) => (prev ? { ...prev, include_chats: checked } : prev))
              }
            />
            <Switch
              label="Enrich from web during export"
              helper="Search the web for turns that need fresh facts (uses Ollama + DuckDuckGo)."
              checked={fineTune.enrich_from_web}
              onCheckedChange={(checked) =>
                setFineTune((prev) => (prev ? { ...prev, enrich_from_web: checked } : prev))
              }
            />
            <Switch
              label="Fetch search result pages"
              helper="Download full page text from search URLs and add dedicated training rows."
              checked={fineTune.fetch_search_pages}
              disabled={!fineTune.enrich_from_web && !fineTune.include_chats}
              onCheckedChange={(checked) =>
                setFineTune((prev) => (prev ? { ...prev, fetch_search_pages: checked } : prev))
              }
            />
            <Input
              label="Max pages per search query"
              type="number"
              min={1}
              max={5}
              value={String(fineTune.max_pages_per_query)}
              onChange={(e) =>
                setFineTune((prev) =>
                  prev
                    ? {
                        ...prev,
                        max_pages_per_query: Math.min(
                          5,
                          Math.max(1, Number(e.target.value) || 1)
                        ),
                      }
                    : prev
                )
              }
            />
            <p className="text-xs text-ink-muted">
              Turns that already used web search in Chat always include their search snippets;
              page fetching applies to those URLs too when enabled.
            </p>
            <Button
              variant="secondary"
              icon={<Save className="h-4 w-4" />}
              onClick={saveFineTuneOptions}
              loading={saving}
            >
              Save training options
            </Button>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card className="space-y-4">
              <SectionTitle>Export training data</SectionTitle>
              <p className="text-[13px] leading-5 text-ink-secondary">
                Writes pa_sft.jsonl with one row per assistant reply (system prompt + conversation
                history). DPO pairs come from recorded corrections in data/training/dpo/.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  icon={<Download className="h-4 w-4" />}
                  loading={exporting === "sft"}
                  onClick={() => runExport("sft")}
                >
                  Export SFT
                </Button>
                <Button
                  variant="secondary"
                  icon={<Download className="h-4 w-4" />}
                  loading={exporting === "dpo"}
                  onClick={() => runExport("dpo")}
                >
                  Export DPO
                </Button>
                <Button
                  variant="secondary"
                  icon={<Download className="h-4 w-4" />}
                  loading={exporting === "all"}
                  onClick={() => runExport("all")}
                >
                  Export all
                </Button>
              </div>
              {training.nightly_enabled && (
                <p className="text-xs text-ink-muted">
                  Nightly export is enabled in Policies — schedule runs locally when configured.
                </p>
              )}
            </Card>

            <Card className="space-y-4">
              <SectionTitle>Run fine-tune</SectionTitle>
              {!training.training_available && (
                <p className="text-xs leading-5 text-amber-700">
                  Training packages not installed. Run{" "}
                  <code className="rounded bg-surface-muted px-1 py-0.5 font-mono text-[12px]">
                    pip install &apos;membrane[train]&apos;
                  </code>{" "}
                  on the server (CUDA GPU required).
                </p>
              )}
              <Select
                label="Base model"
                value={fineTune.base_model || chatModel}
                options={modelOptions(fineTune.base_model || chatModel)}
                onValueChange={(v) => setFineTune((prev) => (prev ? { ...prev, base_model: v } : prev))}
              />
              <Input
                label="Output model name"
                helper="Name for your fine-tuned Ollama model (e.g. membrane-pa:latest)."
                value={fineTune.output_model}
                onChange={(e) =>
                  setFineTune((prev) => (prev ? { ...prev, output_model: e.target.value } : prev))
                }
                inputClassName="font-mono text-[13px]"
              />
              <Input
                label="Hugging Face model (optional)"
                helper="Override when your Ollama tag is not auto-mapped."
                value={fineTune.hf_base_model}
                onChange={(e) =>
                  setFineTune((prev) => (prev ? { ...prev, hf_base_model: e.target.value } : prev))
                }
                inputClassName="font-mono text-[13px]"
              />
              <div className="grid gap-3 sm:grid-cols-2">
                <Input
                  label="Epochs"
                  type="number"
                  min={1}
                  max={10}
                  value={String(fineTune.epochs)}
                  onChange={(e) =>
                    setFineTune((prev) =>
                      prev ? { ...prev, epochs: Math.max(1, Number(e.target.value) || 1) } : prev
                    )
                  }
                />
                <Input
                  label="Batch size"
                  type="number"
                  min={1}
                  max={16}
                  value={String(fineTune.batch_size)}
                  onChange={(e) =>
                    setFineTune((prev) =>
                      prev ? { ...prev, batch_size: Math.max(1, Number(e.target.value) || 1) } : prev
                    )
                  }
                />
                <Input
                  label="LoRA rank"
                  type="number"
                  min={4}
                  max={128}
                  value={String(fineTune.lora_rank)}
                  onChange={(e) =>
                    setFineTune((prev) =>
                      prev ? { ...prev, lora_rank: Math.max(4, Number(e.target.value) || 16) } : prev
                    )
                  }
                />
                <Input
                  label="Max sequence length"
                  type="number"
                  min={512}
                  max={8192}
                  value={String(fineTune.max_seq_length)}
                  onChange={(e) =>
                    setFineTune((prev) =>
                      prev
                        ? { ...prev, max_seq_length: Math.max(512, Number(e.target.value) || 2048) }
                        : prev
                    )
                  }
                />
              </div>
              <Switch
                label="Set as chat model when done"
                checked={fineTune.set_as_chat_model}
                onCheckedChange={(checked) =>
                  setFineTune((prev) => (prev ? { ...prev, set_as_chat_model: checked } : prev))
                }
              />
              <Button
                icon={<Sparkles className="h-4 w-4" />}
                onClick={runFineTune}
                loading={fineTuning || fineTuneActive}
                disabled={!training.training_available || fineTuneActive}
              >
                {fineTuneActive ? "Fine-tuning…" : "Run fine-tune"}
              </Button>
              <p className="text-xs leading-5 text-ink-muted">
                Exports SFT data, runs LoRA training with Unsloth, registers the adapter in Ollama,
                and optionally sets it as your chat model. Requires a CUDA GPU.
              </p>
            </Card>
          </div>

          {training.exports.length > 0 && (
            <>
              <SectionTitle className="mb-3 mt-8">Recent exports</SectionTitle>
              <Card className="p-0">
                <Table>
                  <THead>
                    <TR>
                      <TH>File</TH>
                      <TH className="text-right">Size</TH>
                      <TH className="text-right">Modified</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {training.exports.map((exp) => (
                      <TR key={exp.name}>
                        <TD className="font-mono text-[13px]">{exp.name}</TD>
                        <TD className="text-right tabular-nums">{formatBytes(exp.size_bytes)}</TD>
                        <TD className="text-right text-ink-muted">
                          {new Date(exp.modified_at).toLocaleString()}
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </Card>
            </>
          )}
        </TabsContent>
      </Tabs>

      {connectTool && credentials.tools[connectTool.id] && (
        <ConnectDialog
          tool={connectTool}
          schema={credentials.tools[connectTool.id]}
          oauthProviders={credentials.oauth_providers.filter((p) => p.tool_id === connectTool.id)}
          draft={credentialDraft}
          saving={savingCredentials}
          onDraftChange={(key, value) =>
            setCredentialDraft((prev) => ({ ...prev, [key]: value }))
          }
          onSave={saveCredentials}
          onClear={clearCredentials}
          onOAuth={startOAuth}
          onClose={() => setConnectTool(null)}
        />
      )}
    </>
  );
}

function McpCard({
  server,
  onToggle,
  onEnvChange,
  onFieldChange,
}: {
  server: McpServer;
  onToggle: (enabled: boolean) => void;
  onEnvChange: (key: string, value: string) => void;
  onFieldChange: (patch: Partial<McpServer>) => void;
}) {
  const envKeys = Object.keys(server.env);
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-medium text-ink-primary">{server.name}</h3>
            {server.built_in && <Tag tone="purple">built-in</Tag>}
            <Tag tone="gray">{server.id}</Tag>
          </div>
          <p className="mt-1 text-[13px] leading-5 text-ink-secondary">{server.description}</p>
        </div>
        <Switch
          label="Enabled"
          checked={server.enabled}
          onCheckedChange={onToggle}
          className="shrink-0"
        />
      </div>
      {!server.built_in && (
        <div className="space-y-3 border-t border-line pt-3">
          <Input
            label="Command"
            value={server.command}
            onChange={(e) => onFieldChange({ command: e.target.value })}
            inputClassName="font-mono text-[13px]"
          />
          <Input
            label="Arguments"
            helper="Space-separated args passed to the command"
            value={server.args.join(" ")}
            onChange={(e) =>
              onFieldChange({
                args: e.target.value.trim() ? e.target.value.trim().split(/\s+/) : [],
              })
            }
            inputClassName="font-mono text-[13px]"
          />
        </div>
      )}
      {server.built_in && server.command && (
        <p className="font-mono text-xs text-ink-muted">
          {server.command} {server.args.join(" ")}
        </p>
      )}
      {envKeys.length > 0 && (
        <div className="space-y-3 border-t border-line pt-3">
          <SectionTitle>Server credentials</SectionTitle>
          {envKeys.map((key) => (
            <Input
              key={key}
              label={key}
              type="password"
              placeholder="Paste token or connection string"
              value={server.env[key] ?? ""}
              onChange={(e) => onEnvChange(key, e.target.value)}
              inputClassName="font-mono text-[13px]"
            />
          ))}
        </div>
      )}
    </Card>
  );
}

function ConnectDialog({
  tool,
  schema,
  oauthProviders,
  draft,
  saving,
  onDraftChange,
  onSave,
  onClear,
  onOAuth,
  onClose,
}: {
  tool: ToolIntegration;
  schema: ToolCredentials;
  oauthProviders: CredentialsCatalog["oauth_providers"];
  draft: Record<string, string>;
  saving: boolean;
  onDraftChange: (key: string, value: string) => void;
  onSave: () => void;
  onClear: () => void;
  onOAuth: (providerId: string) => void;
  onClose: () => void;
}) {
  const editableFields = schema.fields.filter((f) => !f.oauth_only);
  const oauthFields = schema.fields.filter((f) => f.oauth_only);
  const canOAuth = oauthProviders.some((p) =>
    p.requires.every((key) => draft[key]?.trim() || schema.values[key])
  );

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Connect ${tool.name}`}
      description="Credentials are stored locally on your machine in config/membrane.db."
      className="max-w-lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {schema.has_stored && (
            <Button
              variant="danger"
              icon={<Trash2 className="h-4 w-4" />}
              onClick={onClear}
              loading={saving}
            >
              Clear
            </Button>
          )}
          <Button icon={<Save className="h-4 w-4" />} onClick={onSave} loading={saving}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {editableFields.map((field) => (
          <Input
            key={field.key}
            label={field.label}
            helper={field.helper || undefined}
            placeholder={field.placeholder || (schema.values[field.key] ? "Saved (enter to replace)" : undefined)}
            type={field.secret ? "password" : "text"}
            value={draft[field.key] ?? ""}
            onChange={(e) => onDraftChange(field.key, e.target.value)}
            inputClassName={field.secret ? "font-mono text-[13px]" : undefined}
          />
        ))}

        {oauthFields.map((field) =>
          schema.values[field.key] ? (
            <div key={field.key} className="rounded-md border border-line px-3 py-2">
              <p className="text-xs text-ink-muted">{field.label}</p>
              <p className="font-mono text-[13px] text-emerald-300">{schema.values[field.key]}</p>
            </div>
          ) : null
        )}

        {oauthProviders.length > 0 && (
          <div className="space-y-2 border-t border-line pt-4">
            <SectionTitle>Sign in</SectionTitle>
            <p className="text-xs leading-5 text-ink-muted">
              Save client ID and secret first, then sign in. You'll be redirected back here when
              done. Add this redirect URI to your OAuth app:{" "}
              <code className="text-ink-secondary">
                {window.location.origin}/api/oauth/&lt;provider&gt;/callback
              </code>
            </p>
            {oauthProviders.map((provider) => (
              <Button
                key={provider.id}
                variant="secondary"
                icon={<ExternalLink className="h-4 w-4" />}
                disabled={!canOAuth}
                onClick={() => onOAuth(provider.id)}
              >
                Sign in with {provider.label}
              </Button>
            ))}
          </div>
        )}
      </div>
    </Dialog>
  );
}

function ToolCard({
  tool,
  canConnect,
  onToggle,
  onConnect,
}: {
  tool: ToolIntegration;
  canConnect: boolean;
  onToggle: (enabled: boolean) => void;
  onConnect: () => void;
}) {
  const category = CATEGORY_LABELS[tool.category] ?? tool.category;
  const viaLabel =
    tool.via === "oauth"
      ? "OAuth"
      : tool.via === "cli"
        ? "CLI"
        : tool.via === "ingest_server"
          ? "Ingest server"
          : "Built-in";

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Wrench className="h-4 w-4 shrink-0 text-ink-muted" />
            <h3 className="text-sm font-medium text-ink-primary">{tool.name}</h3>
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            <Tag tone="gray">{category}</Tag>
            <Tag tone="blue">{viaLabel}</Tag>
            {tool.connected ? (
              <Tag tone="green">connected</Tag>
            ) : (
              <Tag tone="amber">not connected</Tag>
            )}
          </div>
        </div>
        <Switch checked={tool.enabled} onCheckedChange={onToggle} aria-label={`Enable ${tool.name}`} />
      </div>
      <p className="text-[13px] leading-5 text-ink-secondary">{tool.description}</p>
      {tool.setup_hint && (
        <p className="text-xs leading-5 text-ink-muted">{tool.setup_hint}</p>
      )}
      {canConnect && (
        <Button variant="secondary" size="sm" className="self-start" onClick={onConnect}>
          Connect
        </Button>
      )}
    </Card>
  );
}
