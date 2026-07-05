import { lazy, Suspense, useEffect, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import {
  BookOpen,
  Database,
  Hexagon,
  LayoutDashboard,
  ListChecks,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Server,
  SlidersHorizontal,
  Wrench,
} from "lucide-react";
import { api, Status } from "../api";
import { Spinner } from "./ui/Spinner";
import { cn } from "../lib/utils";

const DashboardPage = lazy(() => import("../pages/Dashboard"));
const ChatPage = lazy(() => import("../pages/Chat"));
const ReviewPage = lazy(() => import("../pages/Review"));
const MemoryPage = lazy(() => import("../pages/Memory"));
const IngestPage = lazy(() => import("../pages/Ingest"));
const BooksPage = lazy(() => import("../pages/Books"));
const ServerPage = lazy(() => import("../pages/Server"));
const PoliciesPage = lazy(() => import("../pages/Policies"));
const ToolsPage = lazy(() => import("../pages/Tools"));

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/review", label: "Memory review", icon: ListChecks },
  { to: "/memory", label: "Live memory", icon: Database },
  { to: "/books", label: "Books", icon: BookOpen },
  { to: "/ingest", label: "Ingest", icon: RefreshCw },
  { to: "/server", label: "Server", icon: Server },
  { to: "/tools", label: "Model & tools", icon: Wrench },
  { to: "/policies", label: "Policies", icon: SlidersHorizontal },
] as const;

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={cn("h-1.5 w-1.5 shrink-0 rounded-full", ok ? "bg-emerald-400" : "bg-red-400")}
    />
  );
}

export default function AppShell() {
  const location = useLocation();
  const [status, setStatus] = useState<Status | null>(null);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    api.status().then(setStatus).catch(console.error);
    const t = setInterval(() => api.status().then(setStatus).catch(console.error), 30000);
    return () => clearInterval(t);
  }, []);

  const isChat = location.pathname === "/chat";

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-line bg-surface-sidebar transition-[width] duration-150",
          expanded ? "w-[220px]" : "w-[56px]"
        )}
      >
        <div
          className={cn(
            "flex h-14 shrink-0 items-center gap-2.5 border-b border-line",
            expanded ? "px-4" : "justify-center px-0"
          )}
        >
          <Hexagon className="h-5 w-5 shrink-0 text-accent" />
          {expanded && (
            <span className="text-sm font-semibold tracking-tight text-ink-primary">membrane</span>
          )}
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => {
            const active = location.pathname === item.to;
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                title={expanded ? undefined : item.label}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition",
                  expanded ? "" : "justify-center px-0",
                  active
                    ? "bg-surface-hover text-ink-primary"
                    : "text-ink-secondary hover:bg-surface-hover/60 hover:text-ink-primary"
                )}
              >
                <Icon className={cn("h-4 w-4 shrink-0", active ? "text-accent" : "opacity-70")} />
                {expanded && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="shrink-0 border-t border-line p-2">
          {status && expanded && (
            <div className="mb-2 space-y-1.5 px-2.5 py-2">
              <div className="flex items-center gap-2 text-xs text-ink-secondary">
                <StatusDot ok={status.ollama_ok} />
                <span className="truncate">
                  Ollama {status.ollama_ok ? "online" : "offline"}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs text-ink-secondary">
                <StatusDot ok={status.pending_proposals === 0} />
                <span className="truncate">{status.pending_proposals} pending review</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-ink-secondary">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
                <span className="truncate">Phase: {status.phase}</span>
              </div>
            </div>
          )}
          {status && !expanded && (
            <div
              className="mb-2 flex justify-center py-2"
              title={`Ollama ${status.ollama_ok ? "online" : "offline"} · ${status.pending_proposals} pending · phase ${status.phase}`}
            >
              <StatusDot ok={status.ollama_ok && status.pending_proposals === 0} />
            </div>
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-ink-muted transition hover:bg-surface-hover/60 hover:text-ink-primary",
              expanded ? "" : "justify-center px-0"
            )}
          >
            {expanded ? (
              <>
                <PanelLeftClose className="h-4 w-4 shrink-0 opacity-70" />
                <span>Collapse</span>
              </>
            ) : (
              <PanelLeftOpen className="h-4 w-4 shrink-0 opacity-70" />
            )}
          </button>
        </div>
      </aside>

      <main id="main-content" className={cn("min-w-0 flex-1", isChat ? "overflow-hidden" : "overflow-y-auto")}>
        <Suspense fallback={<Spinner label="Loading page…" className="px-8" />}>
          {isChat ? (
            <Routes>
              <Route path="/chat" element={<ChatPage />} />
            </Routes>
          ) : (
            <div className="mx-auto w-full max-w-5xl px-8 py-8 pb-16">
              <Routes>
                <Route path="/" element={<DashboardPage status={status} />} />
                <Route path="/review" element={<ReviewPage />} />
                <Route path="/memory" element={<MemoryPage />} />
                <Route path="/books" element={<BooksPage />} />
                <Route path="/ingest" element={<IngestPage />} />
                <Route path="/server" element={<ServerPage />} />
                <Route path="/tools" element={<ToolsPage />} />
                <Route path="/policies" element={<PoliciesPage />} />
              </Routes>
            </div>
          )}
        </Suspense>
      </main>
    </div>
  );
}
