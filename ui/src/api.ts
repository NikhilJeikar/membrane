const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type Status = {
  ollama_ok: boolean;
  ollama_model: string;
  pending_proposals: number;
  approved_archive: number;
  profile_count: number;
  preference_count: number;
  episode_count: number;
  tracked_entries: number;
  stale_extract_cursor: number;
  cursor_parsed: number;
  chats: number;
  phase: string;
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

export type MemorySnapshot = {
  profile: Array<{ id: string; key: string; value: string }>;
  preferences: Array<{ id: string; key: string; value: string }>;
  episodes: Array<{ id: string; summary: string; tags: string[] }>;
};

export type TrainingPolicy = {
  phase: string;
  nightly: { enabled: boolean; since_hours: number };
  sources: Record<string, SourcePolicy>;
};

export const api = {
  status: () => request<Status>("/api/status"),
  memorySnapshot: () => request<MemorySnapshot>("/api/memory/snapshot"),
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
  ingestStats: () => request<Record<string, { raw: number; parsed: number }>>("/api/ingest/stats"),
  parseIngest: (source = "all") =>
    request<Record<string, { processed: number; skipped: number }>>("/api/ingest/parse", {
      method: "POST",
      body: JSON.stringify({ source, force: false }),
    }),
  serverStatus: () => request<Record<string, unknown>>("/api/server/status"),
  getPolicy: () => request<TrainingPolicy>("/api/policy"),
  putPolicy: (policy: TrainingPolicy) =>
    request<TrainingPolicy>("/api/policy", {
      method: "PUT",
      body: JSON.stringify(policy),
    }),
};
