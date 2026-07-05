import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bot,
  Brain,
  Check,
  ChevronDown,
  Copy,
  Globe,
  GraduationCap,
  Loader2,
  MessageSquare,
  Plus,
  SendHorizontal,
  Sparkles,
  Terminal,
  Trash2,
  UserRound,
} from "lucide-react";
import { api, ChatSession, ChatSessionSummary, ChatTurn, ContextUsage, MemoryContext, Proposal, ShellEvent, TurnReferences, WebSearchEvent } from "../api";
import { MarkdownContent } from "../components/MarkdownContent";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { ScrollArea } from "../components/ui/ScrollArea";
import { Switch } from "../components/ui/Switch";
import { useToast } from "../components/ui/Toast";
import { cn } from "../lib/utils";

const SUGGESTIONS = [
  "Summarize what you know about me",
  "What preferences should I add?",
  "Help me plan my week",
];

function sessionIncludeInTraining(session: ChatSession | null): boolean {
  return session?.metadata?.include_in_training !== false;
}

function roleLabel(role: "user" | "assistant") {
  return role === "user" ? "You" : "Assistant";
}

function isChatRoleTurn(turn: ChatTurn): turn is ChatTurn & { role: "user" | "assistant" } {
  return turn.role === "user" || turn.role === "assistant";
}

function formatChatForCopy(turns: ChatTurn[]): string {
  return turns
    .filter(isChatRoleTurn)
    .map((t) => `${roleLabel(t.role)}:\n${t.content}`)
    .join("\n\n");
}

function formatTokens(n: number) {
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k`;
  return n.toLocaleString();
}

function ContextUsageRing({ usage }: { usage: ContextUsage | null }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const percent = usage?.usage_percent ?? 0;
  const radius = 8.5;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (Math.min(percent, 100) / 100) * circumference;
  const ringClass =
    percent >= 90 ? "stroke-red-400" : percent >= 70 ? "stroke-amber-400" : "stroke-accent";

  return (
    <div ref={rootRef} className="relative mb-0.5 shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={usage ? `Context ${percent}% used. Show breakdown.` : "Context usage loading"}
        aria-expanded={open}
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-full transition",
          "text-ink-muted hover:bg-white/5 hover:text-ink-secondary",
          open && "bg-white/5 text-ink-primary"
        )}
      >
        <svg
          width="22"
          height="22"
          viewBox="0 0 22 22"
          className="overflow-visible"
          aria-hidden
        >
          <circle
            cx="11"
            cy="11"
            r={radius}
            fill="none"
            className="stroke-white/15"
            strokeWidth="2.25"
          />
          <circle
            cx="11"
            cy="11"
            r={radius}
            fill="none"
            className={cn(ringClass, "transition-[stroke-dashoffset] duration-300")}
            strokeWidth="2.25"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={usage ? dashOffset : circumference}
            transform="rotate(-90 11 11)"
          />
        </svg>
      </button>

      {open && usage && (
        <div
          role="dialog"
          aria-label="Context usage breakdown"
          className="absolute bottom-full right-0 z-50 mb-2 w-[17.5rem] rounded-xl border border-line-strong bg-surface-card p-3 shadow-overlay animate-fadeIn"
        >
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-ink-primary">Context usage</p>
            <span className="tabular-nums text-xs text-ink-muted">{percent}%</span>
          </div>

          <div className="mb-3 flex items-baseline justify-between gap-2">
            <span className="text-lg font-semibold tabular-nums text-ink-primary">
              {formatTokens(usage.estimated_tokens)}
            </span>
            <span className="text-xs tabular-nums text-ink-muted">
              / {formatTokens(usage.context_limit)} tokens
            </span>
          </div>

          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-white/10">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                percent >= 90 ? "bg-red-400" : percent >= 70 ? "bg-amber-400" : "bg-accent"
              )}
              style={{ width: `${Math.max(percent, 2)}%` }}
            />
          </div>

          <div className="space-y-2 border-t border-line pt-3">
            <BreakdownRow
              label="System"
              tokens={usage.system_base_tokens ?? usage.system_tokens}
              total={usage.estimated_tokens}
              tone="accent"
            />
            {(usage.memory_tokens ?? 0) > 0 && (
              <BreakdownRow
                label="Memory"
                tokens={usage.memory_tokens}
                total={usage.estimated_tokens}
                tone="accent"
              />
            )}
            {(usage.tools_tokens ?? 0) > 0 && (
              <>
                <BreakdownRow
                  label="Tools"
                  tokens={usage.tools_tokens}
                  total={usage.estimated_tokens}
                  tone="violet"
                />
                {usage.tools_breakdown?.web_search ? (
                  <BreakdownRow
                    label="Web search"
                    tokens={usage.tools_breakdown.web_search}
                    total={usage.estimated_tokens}
                    tone="violet"
                    nested
                  />
                ) : null}
                {usage.tools_breakdown?.firecrawl ? (
                  <BreakdownRow
                    label="Page scrape"
                    tokens={usage.tools_breakdown.firecrawl}
                    total={usage.estimated_tokens}
                    tone="violet"
                    nested
                  />
                ) : null}
                {usage.tools_breakdown?.shell ? (
                  <BreakdownRow
                    label="Shell"
                    tokens={usage.tools_breakdown.shell}
                    total={usage.estimated_tokens}
                    tone="violet"
                    nested
                  />
                ) : null}
              </>
            )}
            <BreakdownRow
              label="This conversation"
              tokens={usage.conversation_tokens}
              total={usage.estimated_tokens}
              tone="blue"
            />
            {(usage.reasoning_tokens ?? 0) > 0 && (
              <BreakdownRow
                label="Reasoning"
                tokens={usage.reasoning_tokens ?? 0}
                total={usage.estimated_tokens}
                tone="violet"
              />
            )}
            {usage.draft_tokens > 0 && (
              <BreakdownRow
                label="Draft message"
                tokens={usage.draft_tokens}
                total={usage.estimated_tokens}
                tone="blue"
              />
            )}
            <BreakdownRow
              label="Remaining"
              tokens={usage.remaining_tokens}
              total={usage.context_limit}
              tone="gray"
              muted
            />
          </div>

          <p className="mt-3 text-[11px] leading-4 text-ink-muted">
            Estimates use ~4 chars/token.
          </p>
        </div>
      )}
    </div>
  );
}

function BreakdownRow({
  label,
  tokens,
  total,
  tone,
  muted,
  nested,
}: {
  label: string;
  tokens: number;
  total: number;
  tone: "accent" | "blue" | "gray" | "violet";
  muted?: boolean;
  nested?: boolean;
}) {
  const pct = total > 0 ? Math.round((tokens / total) * 100) : 0;
  const barClass =
    tone === "accent"
      ? "bg-accent"
      : tone === "blue"
        ? "bg-sky-400"
        : tone === "violet"
          ? "bg-violet-400"
          : "bg-white/20";
  return (
    <div className={cn(muted && "opacity-80", nested && "pl-3")}>
      <div className="mb-1 flex items-center justify-between gap-2 text-[11px]">
        <span className="text-ink-secondary">{label}</span>
        <span className="tabular-nums text-ink-muted">
          ~{formatTokens(tokens)}
          {!muted && total > 0 ? ` · ${pct}%` : ""}
        </span>
      </div>
      {!muted && (
        <div className="h-1 overflow-hidden rounded-full bg-white/10">
          <div className={cn("h-full rounded-full", barClass)} style={{ width: `${Math.max(pct, 2)}%` }} />
        </div>
      )}
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1.5 py-1" aria-label="Assistant is thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-ink-muted animate-pulseDot"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function ThinkingBlock({
  thinking,
  streaming = false,
}: {
  thinking?: string;
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(streaming);

  useEffect(() => {
    if (streaming) setOpen(true);
  }, [streaming]);

  if (!thinking) return null;

  return (
    <div className="rounded-lg border border-violet-500/20 bg-violet-950/20">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs text-ink-secondary transition hover:bg-white/5"
      >
        <span className="inline-flex items-center gap-1.5 font-medium uppercase tracking-wide text-violet-300/90">
          {streaming ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Brain className="h-3.5 w-3.5" />
          )}
          Reasoning
          {streaming && <span className="normal-case tracking-normal text-ink-muted">· live</span>}
        </span>
        <ChevronDown className={cn("h-3.5 w-3.5 shrink-0 transition", open && "rotate-180")} />
      </button>
      {open && (
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-violet-500/15 px-3 py-2.5 font-mono text-[12px] leading-5 text-ink-secondary">
          {thinking}
        </pre>
      )}
    </div>
  );
}

function memoryItemCount(ctx?: MemoryContext): number {
  if (!ctx) return 0;
  return (
    (ctx.profile?.length ?? 0) +
    (ctx.preferences?.length ?? 0) +
    (ctx.episodes?.length ?? 0)
  );
}

function hasReferences(
  refs?: TurnReferences | null,
  search?: WebSearchEvent | null,
  shell?: ShellEvent | null
): boolean {
  if (memoryItemCount(refs?.memory_context) > 0) return true;
  if (refs?.web_search?.query) return true;
  if (refs?.shell?.commands?.length) return true;
  if (search?.status === "searching") return true;
  if (search?.query) return true;
  if (shell?.status === "running") return true;
  if (shell?.command) return true;
  if ((shell?.commands?.length ?? 0) > 0) return true;
  return false;
}

function ReferencesPanel({
  refs,
  search,
  shell,
}: {
  refs?: TurnReferences | null;
  search?: WebSearchEvent | null;
  shell?: ShellEvent | null;
}) {
  const [open, setOpen] = useState(false);
  const memory = refs?.memory_context;
  const web =
    refs?.web_search ??
    (search?.status === "done" ? { query: search.query, results: search.results ?? [] } : null);
  const shellCommands =
    refs?.shell?.commands ??
    shell?.commands ??
    [];
  const searching = search?.status === "searching";
  const shellRunning = shell?.status === "running";
  const currentShellCommand = shellRunning ? shell?.command : undefined;
  const memoryCount = memoryItemCount(memory);
  const webCount = web?.results?.length ?? 0;
  const shellCount = shellCommands.length;
  const showCurrentShell =
    shellRunning &&
    currentShellCommand &&
    !shellCommands.some((result) => result.command === currentShellCommand);

  useEffect(() => {
    if (shellRunning && (currentShellCommand || shellCount > 0)) {
      setOpen(true);
    }
  }, [shellRunning, currentShellCommand, shellCount]);

  if (!hasReferences(refs, search, shell)) return null;

  const labelParts: string[] = [];
  if (memoryCount > 0) {
    labelParts.push(`${memoryCount} memor${memoryCount === 1 ? "y" : "ies"}`);
  }
  if (searching) {
    labelParts.push(`searching “${search.query}”`);
  } else if (web?.query) {
    labelParts.push(
      webCount > 0
        ? `${webCount} web source${webCount === 1 ? "" : "s"}`
        : "web search (no results)"
    );
  }
  if (shellRunning) {
    if (currentShellCommand) {
      labelParts.push(`running $ ${currentShellCommand}`);
    } else if (shellCount > 0) {
      labelParts.push(`running shell commands (${shellCount} done)`);
    } else {
      labelParts.push("deciding shell commands");
    }
  } else if (shellCount > 0) {
    labelParts.push(`${shellCount} shell command${shellCount === 1 ? "" : "s"}`);
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-md border border-white/10 px-2 py-1 text-xs text-ink-muted transition hover:border-white/20 hover:bg-surface-hover hover:text-ink-secondary"
      >
        {searching ? (
          <Globe className="h-3.5 w-3.5 animate-pulse text-accent" />
        ) : shellRunning ? (
          <Terminal className="h-3.5 w-3.5 animate-pulse text-accent" />
        ) : memoryCount > 0 && (webCount > 0 || shellCount > 0) ? (
          <Brain className="h-3.5 w-3.5" />
        ) : webCount > 0 ? (
          <Globe className="h-3.5 w-3.5" />
        ) : shellCount > 0 ? (
          <Terminal className="h-3.5 w-3.5" />
        ) : (
          <Brain className="h-3.5 w-3.5" />
        )}
        <span>{labelParts.join(" · ")}</span>
        {!searching && (
          <ChevronDown className={cn("h-3 w-3 transition", open && "rotate-180")} />
        )}
      </button>

      {open && !searching && (
        <div className="space-y-3 rounded-lg border border-white/10 bg-surface-elevated/60 p-3 text-xs">
          {memoryCount > 0 && (
            <div className="space-y-2">
              <p className="font-medium uppercase tracking-wide text-ink-muted">Memory used</p>
              {memory?.profile?.length ? (
                <div>
                  <p className="mb-1 text-ink-secondary">Profile</p>
                  <ul className="space-y-1 text-ink-primary">
                    {memory.profile.map((entry) => (
                      <li key={`p-${entry.key}`}>
                        <span className="text-ink-muted">{entry.key}:</span> {entry.value}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {memory?.preferences?.length ? (
                <div>
                  <p className="mb-1 text-ink-secondary">Preferences</p>
                  <ul className="space-y-1 text-ink-primary">
                    {memory.preferences.map((entry) => (
                      <li key={`pref-${entry.key}`}>
                        <span className="text-ink-muted">{entry.key}:</span> {entry.value}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {memory?.episodes?.length ? (
                <div>
                  <p className="mb-1 text-ink-secondary">Episodes</p>
                  <ul className="space-y-1 text-ink-primary">
                    {memory.episodes.map((entry, i) => (
                      <li key={`ep-${i}`}>{entry.summary}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}

          {web?.query && (
            <div className="space-y-2">
              <p className="font-medium uppercase tracking-wide text-ink-muted">Web search</p>
              <p className="text-ink-secondary">
                Query: <span className="text-ink-primary">“{web.query}”</span>
              </p>
              {webCount > 0 ? (
                <ul className="space-y-1.5">
                  {web.results?.map((result) => (
                    <li key={result.url}>
                      <a
                        href={result.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent hover:underline"
                      >
                        {result.title || result.url}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-ink-muted">No results returned.</p>
              )}
            </div>
          )}

          {(shellCount > 0 || showCurrentShell) && (
            <div className="space-y-2">
              <p className="font-medium uppercase tracking-wide text-ink-muted">Shell commands</p>
              <ul className="space-y-2 text-ink-primary">
                {shellCommands.map((result, i) => (
                  <li key={`shell-${i}`}>
                    <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[11px]">
                      $ {result.command}
                    </code>
                    {result.blocked ? (
                      <p className="mt-1 text-ink-muted">{result.stderr || "Blocked"}</p>
                    ) : result.timed_out ? (
                      <p className="mt-1 text-ink-muted">{result.stderr || "Timed out"}</p>
                    ) : (
                      <div className="mt-1 space-y-1 text-ink-secondary">
                        {result.exit_code != null && (
                          <p className="text-ink-muted">exit {result.exit_code}</p>
                        )}
                        {result.stdout ? (
                          <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-black/20 p-2 font-mono text-[11px]">
                            {result.stdout}
                          </pre>
                        ) : null}
                        {result.stderr ? (
                          <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-black/20 p-2 font-mono text-[11px] text-amber-200/90">
                            {result.stderr}
                          </pre>
                        ) : null}
                      </div>
                    )}
                  </li>
                ))}
                {showCurrentShell && (
                  <li>
                    <code className="inline-flex items-center gap-1.5 rounded bg-black/30 px-1.5 py-0.5 font-mono text-[11px] text-accent">
                      <Loader2 className="h-3 w-3 animate-spin" />$ {currentShellCommand}
                    </code>
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MessageRow({
  role,
  content,
  thinking,
  isThinking = false,
  references,
  search,
  shell,
  thinkingStreaming = false,
}: {
  role: "user" | "assistant";
  content?: string;
  thinking?: string;
  isThinking?: boolean;
  references?: TurnReferences | null;
  search?: WebSearchEvent | null;
  shell?: ShellEvent | null;
  thinkingStreaming?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const isUser = role === "user";

  async function copyMessage() {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(`${roleLabel(role)}:\n${content}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div
      className={cn(
        "group w-full border-b border-white/5",
        isUser ? "bg-surface-elevated/40" : "bg-transparent"
      )}
    >
      <div className="mx-auto flex w-full max-w-3xl gap-4 px-4 py-6 md:px-6">
        <div
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            isUser
              ? "bg-white text-black"
              : "border border-white/10 bg-surface-elevated text-accent"
          )}
        >
          {isUser ? <UserRound className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
        </div>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              {roleLabel(role)}
            </p>
            {content && !isThinking && (
              <button
                type="button"
                onClick={copyMessage}
                aria-label="Copy message"
                title="Copy message"
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-muted transition hover:bg-white/10 hover:text-ink-primary",
                  "opacity-0 group-hover:opacity-100 focus:opacity-100"
                )}
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            )}
          </div>
          {!isUser && <ReferencesPanel refs={references} search={search} shell={shell} />}
          {!isUser && (thinking || thinkingStreaming) && (
            <ThinkingBlock thinking={thinking} streaming={thinkingStreaming} />
          )}
          {isThinking ? (
            <ThinkingDots />
          ) : content ? (
            <MarkdownContent content={content} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [streamText, setStreamText] = useState<string | null>(null);
  const [streamThinking, setStreamThinking] = useState<string | null>(null);
  const [ollamaOk, setOllamaOk] = useState(true);
  const [modelReady, setModelReady] = useState(true);
  const [model, setModel] = useState("");
  const [webSearch, setWebSearch] = useState(false);
  const [shellEnabled, setShellEnabled] = useState(false);
  const [searchEvent, setSearchEvent] = useState<WebSearchEvent | null>(null);
  const [shellEvent, setShellEvent] = useState<ShellEvent | null>(null);
  const [contextEvent, setContextEvent] = useState<MemoryContext | null>(null);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const canSend = Boolean(activeId && input.trim() && !sending && ollamaOk && modelReady);

  const loadSessions = useCallback(async () => {
    const [list, status] = await Promise.all([api.listChatSessions(), api.status()]);
    setSessions(list.items);
    setOllamaOk(status.ollama_ok);
    setModelReady(status.model_ready);
    setModel(status.ollama_model);
    return list.items;
  }, []);

  useEffect(() => {
    api
      .getPersona()
      .then((p) => {
        setWebSearch(Boolean(p.web_search?.enabled));
        setShellEnabled(Boolean(p.shell?.enabled));
      })
      .catch(console.error);
  }, []);

  async function toggleWebSearch() {
    const next = !webSearch;
    setWebSearch(next);
    try {
      await api.putPersona({ web_search: { enabled: next } });
    } catch (e) {
      setWebSearch(!next);
      toast("error", String(e));
    }
  }

  async function toggleShell() {
    const next = !shellEnabled;
    setShellEnabled(next);
    try {
      await api.putPersona({ shell: { enabled: next } });
    } catch (e) {
      setShellEnabled(!next);
      toast("error", String(e));
    }
  }

  const loadSession = useCallback(async (id: string) => {
    const data = await api.getChatSession(id);
    setSession(data);
    setActiveId(id);
  }, []);

  useEffect(() => {
    if (!activeId) {
      setContextUsage(null);
      return;
    }
    const handle = setTimeout(() => {
      api
        .getChatContextUsage(activeId, input)
        .then(setContextUsage)
        .catch(() => setContextUsage(null));
    }, input ? 200 : 0);
    return () => clearTimeout(handle);
  }, [activeId, session?.turns.length, input]);

  async function toggleIncludeInTraining(checked: boolean) {
    if (!activeId) return;
    try {
      const updated = await api.patchChatSession(activeId, { include_in_training: checked });
      setSession(updated);
      await loadSessions();
      toast("success", checked ? "Chat included in fine-tuning" : "Chat excluded from fine-tuning");
    } catch (e) {
      toast("error", String(e));
    }
  }

  useEffect(() => {
    loadSessions()
      .then(async (items) => {
        if (items.length > 0) {
          await loadSession(items[0].id);
          return;
        }
        const created = await api.createChatSession();
        setSession(created);
        setActiveId(created.id);
        setSessions([{ id: created.id, turns: 0, preview: "", updated_at: null, include_in_training: true }]);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [loadSessions, loadSession]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.turns.length, sending, streamText, streamThinking]);

  useEffect(() => {
    if (!sending) inputRef.current?.focus();
  }, [sending, activeId]);

  function resizeInput() {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  useEffect(() => {
    resizeInput();
  }, [input]);

  async function startNewChat() {
    try {
      const created = await api.createChatSession();
      await loadSessions();
      setSession(created);
      setActiveId(created.id);
      setInput("");
      inputRef.current?.focus();
    } catch (e) {
      toast("error", String(e));
    }
  }

  async function copyChat() {
    if (!session?.turns.length) return;
    try {
      await navigator.clipboard.writeText(formatChatForCopy(session.turns));
      toast("success", "Chat copied to clipboard");
    } catch {
      toast("error", "Failed to copy chat");
    }
  }

  async function confirmDeleteChat() {
    if (!deleteTarget) return;
    const id = deleteTarget;
    setDeleting(true);
    try {
      await api.deleteChatSession(id);
      setDeleteTarget(null);
      const remaining = await loadSessions();
      if (activeId !== id) return;
      if (remaining.length > 0) {
        await loadSession(remaining[0].id);
      } else {
        const created = await api.createChatSession();
        setSession(created);
        setActiveId(created.id);
        setSessions([{ id: created.id, turns: 0, preview: "", updated_at: null, include_in_training: true }]);
      }
      toast("success", "Chat deleted");
    } catch (e) {
      toast("error", String(e));
    } finally {
      setDeleting(false);
    }
  }

  function showMemorySuggestions(suggestions: Proposal[]) {
    for (const proposal of suggestions) {
      const label = proposal.category === "profile" ? "Profile" : "Preference";
      toast(
        "info",
        `Save ${label.toLowerCase()}?`,
        proposal.summary,
        [
          {
            label: "Save",
            variant: "primary",
            onClick: async () => {
              try {
                await api.approve(proposal.id);
                toast("success", `${label} saved`, proposal.summary);
              } catch (e) {
                toast("error", "Failed to save", String(e));
              }
            },
          },
          {
            label: "Review",
            onClick: () => navigate("/review"),
          },
        ]
      );
    }
  }

  async function sendMessage(textOverride?: string) {
    const text = (textOverride ?? input).trim();
    if (!text || !activeId || sending) return;
    if (!ollamaOk) {
      toast("error", "Ollama is offline", "Start with: ollama serve");
      return;
    }
    if (!modelReady) {
      toast("error", "Model not installed", `Run: ollama pull ${model}`);
      return;
    }

    setSending(true);
    setStreamText(null);
    setStreamThinking(null);
    setSearchEvent(null);
    setShellEvent(null);
    setContextEvent(null);
    if (!textOverride) setInput("");
    setSession((prev) =>
      prev
        ? { ...prev, turns: [...prev.turns, { role: "user", content: text, timestamp: null }] }
        : prev
    );
    try {
      const result = await api.sendChatMessage(
        activeId,
        text,
        (delta) => {
          setStreamText((prev) => (prev ?? "") + delta);
        },
        (event) => setSearchEvent(event),
        (context) => setContextEvent(context),
        (usage) => setContextUsage(usage),
        (event) => setShellEvent(event),
        (delta) => {
          setStreamThinking((prev) => (prev ?? "") + delta);
          setContextUsage((prev) => {
            if (!prev) return prev;
            const deltaTokens = Math.max(1, Math.ceil(delta.length / 4));
            const reasoning_tokens = (prev.reasoning_tokens ?? 0) + deltaTokens;
            const estimated_tokens = prev.estimated_tokens + deltaTokens;
            const remaining_tokens = Math.max(0, prev.context_limit - estimated_tokens);
            const usage_percent = Math.min(
              100,
              Math.round((100 * estimated_tokens) / prev.context_limit)
            );
            return {
              ...prev,
              reasoning_tokens,
              estimated_tokens,
              remaining_tokens,
              usage_percent,
            };
          });
        }
      );
      setSession(result.session);
      await loadSessions();
      if (result.memorySuggestions.length > 0) {
        showMemorySuggestions(result.memorySuggestions);
      }
    } catch (e) {
      if (!textOverride) setInput(text);
      toast("error", String(e));
      await loadSession(activeId).catch(() => undefined);
    } finally {
      setSending(false);
      setStreamText(null);
      setStreamThinking(null);
      setSearchEvent(null);
      setShellEvent(null);
      setContextEvent(null);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  const placeholder = !ollamaOk
    ? "Ollama offline — start with: ollama serve"
    : !modelReady
      ? `Pull model: ollama pull ${model}`
      : "Message membrane";

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-surface">
        <div className="flex items-center gap-3 text-ink-secondary">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Loading chat…</span>
        </div>
      </div>
    );
  }

  const isEmpty = !session || session.turns.length === 0;

  return (
    <div className="grid h-full grid-cols-1 bg-surface md:grid-cols-[260px_1fr]">
      <aside className="flex min-h-0 flex-col border-b border-white/10 bg-surface-sidebar p-3 md:border-b-0 md:border-r">
        <button
          type="button"
          onClick={startNewChat}
          className="mb-3 flex w-full items-center gap-2 rounded-lg border border-white/10 bg-transparent px-3 py-2.5 text-sm text-ink-primary transition hover:bg-surface-hover"
        >
          <Plus className="h-4 w-4" />
          New chat
        </button>

        <ScrollArea className="min-h-0 flex-1">
          <nav className="space-y-0.5 pr-2" aria-label="Chat history">
            {sessions.length === 0 ? (
              <p className="px-2 py-2 text-sm text-ink-muted">No conversations yet</p>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  className={cn(
                    "group/session grid w-full grid-cols-[minmax(0,1fr)_auto] items-center rounded-lg transition",
                    activeId === s.id
                      ? "bg-surface-hover text-ink-primary"
                      : "text-ink-secondary hover:bg-surface-hover/70 hover:text-ink-primary"
                  )}
                >
                  <button
                    type="button"
                    onClick={() => loadSession(s.id)}
                    title={s.preview || "New conversation"}
                    className="flex min-w-0 items-center gap-2 overflow-hidden px-3 py-2 text-left text-sm"
                  >
                    <MessageSquare className="h-4 w-4 shrink-0 opacity-60" />
                    <span className="min-w-0 flex-1 truncate">{s.preview || "New conversation"}</span>
                    {!s.include_in_training && (
                      <span className="shrink-0" title="Excluded from fine-tuning">
                        <GraduationCap className="h-3 w-3 text-ink-muted opacity-60" />
                      </span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(s.id)}
                    title="Delete chat"
                    aria-label="Delete chat"
                    className={cn(
                      "mr-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-muted transition hover:bg-white/10 hover:text-red-300",
                      activeId === s.id ? "opacity-100" : "opacity-0 group-hover/session:opacity-100"
                    )}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))
            )}
          </nav>
        </ScrollArea>
      </aside>

      <main className="flex min-h-0 min-w-0 flex-col">
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4 py-3 md:px-6">
          <div className="flex items-center gap-2 text-sm font-medium text-ink-primary">
            <Bot className="h-4 w-4 text-accent" />
            <span>membrane</span>
            {model && (
              <span className="rounded-full border border-white/10 px-2 py-0.5 text-xs font-normal text-ink-muted">
                {model}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {activeId && session && (
              <Switch
                label="Fine-tune"
                checked={sessionIncludeInTraining(session)}
                onCheckedChange={toggleIncludeInTraining}
                className="hidden sm:flex [&_label]:text-xs [&_label]:text-ink-muted"
              />
            )}
            {activeId && session && session.turns.length > 0 && (
              <Button
                variant="ghost"
                size="icon"
                aria-label="Copy chat"
                title="Copy chat"
                icon={<Copy className="h-3.5 w-3.5" />}
                className="text-ink-muted hover:text-ink-primary"
                onClick={copyChat}
              />
            )}
            {activeId && (
              <Button
                variant="ghost"
                size="icon"
                aria-label="Delete chat"
                title="Delete chat"
                icon={<Trash2 className="h-3.5 w-3.5" />}
                className="text-ink-muted hover:text-red-300"
                onClick={() => setDeleteTarget(activeId)}
              />
            )}
            <button
              type="button"
              onClick={toggleWebSearch}
              title={
                webSearch
                  ? "Web search on — the model can search the internet. Click to disable."
                  : "Web search off — the model stays fully local. Click to enable."
              }
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition",
                webSearch
                  ? "border-accent/40 bg-accent-muted text-accent"
                  : "border-white/10 text-ink-muted hover:border-white/20 hover:text-ink-secondary"
              )}
            >
              <Globe className="h-3.5 w-3.5" />
              Web {webSearch ? "on" : "off"}
            </button>
            <button
              type="button"
              onClick={toggleShell}
              title={
                shellEnabled
                  ? "Shell on — the model can run sandboxed Linux commands (no sudo). Click to disable."
                  : "Shell off — the model cannot run commands. Click to enable."
              }
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition",
                shellEnabled
                  ? "border-accent/40 bg-accent-muted text-accent"
                  : "border-white/10 text-ink-muted hover:border-white/20 hover:text-ink-secondary"
              )}
            >
              <Terminal className="h-3.5 w-3.5" />
              Shell {shellEnabled ? "on" : "off"}
            </button>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs",
                ollamaOk ? "bg-accent-muted text-emerald-300" : "bg-red-950/60 text-red-300"
              )}
            >
              <span
                className={cn("h-1.5 w-1.5 rounded-full", ollamaOk ? "bg-emerald-400" : "bg-red-400")}
              />
              {ollamaOk ? "Online" : "Offline"}
            </span>
            {ollamaOk && !modelReady && (
              <span className="rounded-full bg-red-950/60 px-2.5 py-1 text-xs text-red-300">
                Model missing
              </span>
            )}
          </div>
        </header>

        <ScrollArea className="min-h-0 flex-1" viewportClassName="[&>div]:!block">
          {isEmpty && !sending ? (
            <div className="flex min-h-full flex-col items-center justify-center px-4 py-16">
              <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-surface-elevated">
                <Sparkles className="h-7 w-7 text-accent" />
              </div>
              <h1 className="mb-2 text-center text-2xl font-medium tracking-tight text-ink-primary">
                How can I help you today?
              </h1>
              <p className="mb-8 max-w-md text-center text-sm leading-6 text-ink-secondary">
                Each new chat starts fresh — only this conversation&apos;s messages are sent to the
                model, plus your shared memory profile. Other chats are not included.{" "}
                {webSearch
                  ? "Web search is on — search queries are sent to DuckDuckGo."
                  : "Nothing leaves your machine."}
              </p>
              {ollamaOk && !modelReady && model && (
                <p className="mb-6 text-center text-sm text-amber-300/90">
                  Pull your model first:{" "}
                  <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-xs">
                    ollama pull {model}
                  </code>
                </p>
              )}
              <div className="grid w-full max-w-2xl gap-2 sm:grid-cols-3">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    disabled={!ollamaOk || !modelReady || sending}
                    onClick={() => sendMessage(suggestion)}
                    className="rounded-xl border border-white/10 bg-surface-elevated px-3 py-3 text-left text-sm text-ink-secondary transition hover:border-white/20 hover:bg-surface-hover hover:text-ink-primary disabled:opacity-40"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div>
              {session?.turns.map((turn, idx) => (
                <MessageRow
                  key={`${turn.role}-${idx}`}
                  role={turn.role === "user" ? "user" : "assistant"}
                  content={turn.content}
                  thinking={turn.role === "assistant" ? turn.metadata?.thinking : undefined}
                  references={turn.role === "assistant" ? turn.metadata : undefined}
                />
              ))}
              {sending && (
                <MessageRow
                  role="assistant"
                  content={streamText ?? undefined}
                  thinking={streamThinking ?? undefined}
                  thinkingStreaming={Boolean(streamThinking) && !streamText}
                  isThinking={!streamText && !streamThinking}
                  references={{
                    memory_context: contextEvent ?? undefined,
                    web_search: searchEvent?.query
                      ? { query: searchEvent.query, results: searchEvent.results ?? [] }
                      : undefined,
                    shell: shellEvent?.commands?.length
                      ? { commands: shellEvent.commands }
                      : undefined,
                  }}
                  search={searchEvent}
                  shell={shellEvent}
                />
              )}
              <div ref={bottomRef} className="h-4" />
            </div>
          )}
        </ScrollArea>

        <footer className="shrink-0 bg-gradient-to-t from-surface via-surface to-transparent px-4 pb-5 pt-2 md:px-6">
          <div className="mx-auto w-full max-w-3xl">
            {activeId && session && (
              <div className="mb-2 flex items-center justify-between gap-3 sm:hidden">
                <Switch
                  label="Include in fine-tuning"
                  checked={sessionIncludeInTraining(session)}
                  onCheckedChange={toggleIncludeInTraining}
                />
              </div>
            )}
            <div className="flex items-end gap-1 rounded-[1.75rem] border border-white/10 bg-surface-input p-2 shadow-composer focus-within:border-white/20">
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                disabled={!activeId || sending || !ollamaOk || !modelReady}
                placeholder={placeholder}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                className="max-h-[200px] min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 text-[0.95rem] leading-6 text-ink-primary outline-none placeholder:text-ink-muted disabled:opacity-50"
              />
              <ContextUsageRing usage={contextUsage} />
              <button
                type="button"
                onClick={() => sendMessage()}
                disabled={!canSend}
                aria-label="Send message"
                className={cn(
                  "mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition",
                  canSend
                    ? "bg-accent text-white hover:bg-accent-hover"
                    : "bg-white/10 text-ink-muted"
                )}
              >
                {sending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <SendHorizontal className="h-4 w-4" />
                )}
              </button>
            </div>
            <p className="mt-2 text-center text-xs text-ink-muted">
              membrane uses your local memory store. Click the ring for token breakdown.
            </p>
          </div>
        </footer>
      </main>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Delete chat"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="danger" loading={deleting} onClick={confirmDeleteChat}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-secondary">
          Delete this conversation? This cannot be undone.
        </p>
      </Dialog>
    </div>
  );
}
