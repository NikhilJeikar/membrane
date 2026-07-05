import { Save, UserRound } from "lucide-react";
import { Button } from "./ui/Button";
import { Card, SectionTitle } from "./ui/Card";
import { Input } from "./ui/Input";
import { Select } from "./ui/Select";
import { Switch } from "./ui/Switch";
import type { Persona } from "../api";

type Props = {
  persona: Persona;
  onChange: (next: Persona) => void;
  onSave: () => void;
  saving: boolean;
};

function num(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function PersonaBehaviorPanel({ persona, onChange, onSave, saving }: Props) {
  const patch = (partial: Partial<Persona>) => onChange({ ...persona, ...partial });

  return (
    <Card className="space-y-4">
      <SectionTitle>Identity & behavior</SectionTitle>
      <Input
        label="Assistant name"
        value={String(persona.identity?.name ?? "")}
        onChange={(e) => patch({ identity: { ...persona.identity, name: e.target.value } })}
      />
      <Input
        label="Timezone"
        helper="IANA timezone, e.g. Asia/Kolkata"
        value={String(persona.identity?.timezone ?? "")}
        onChange={(e) => patch({ identity: { ...persona.identity, timezone: e.target.value } })}
      />
      <Input
        label="Self names"
        helper="Comma-separated names that refer to you in chats (WhatsApp ingest, etc.)"
        value={(persona.self_names ?? []).join(", ")}
        onChange={(e) =>
          patch({
            self_names: e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
          })
        }
      />
      <Select
        label="Response format"
        value={String(persona.style?.format ?? "bullets")}
        options={[
          { value: "bullets", label: "Bullets" },
          { value: "prose", label: "Prose" },
        ]}
        onValueChange={(format) =>
          patch({ style: { ...persona.style, format } })
        }
      />
      <Select
        label="Response length"
        value={String(persona.style?.max_length ?? "short")}
        options={[
          { value: "short", label: "Short" },
          { value: "medium", label: "Medium" },
          { value: "long", label: "Long" },
        ]}
        onValueChange={(max_length) =>
          patch({ style: { ...persona.style, max_length } })
        }
      />
      <Input
        label="Empathy level"
        type="number"
        min={0}
        max={1}
        step={0.1}
        value={String(persona.style?.empathy_level ?? 0.6)}
        onChange={(e) =>
          patch({ style: { ...persona.style, empathy_level: num(e.target.value, 0.6) } })
        }
      />
      <Input
        label="Proactivity"
        type="number"
        min={0}
        max={1}
        step={0.1}
        value={String(persona.style?.proactivity ?? 0.4)}
        onChange={(e) =>
          patch({ style: { ...persona.style, proactivity: num(e.target.value, 0.4) } })
        }
      />
      <Switch
        label="Independent opinions"
        helper="Let the assistant share its own view and respectfully disagree instead of mirroring yours."
        checked={persona.style?.independent_opinions !== false}
        onCheckedChange={(independent_opinions) =>
          patch({ style: { ...persona.style, independent_opinions } })
        }
      />
      <Switch
        label="Use profile in context"
        checked={Boolean(persona.memory?.use_profile)}
        onCheckedChange={(use_profile) =>
          patch({ memory: { ...persona.memory, use_profile } })
        }
      />
      <Switch
        label="Use preferences in context"
        checked={Boolean(persona.memory?.use_preferences)}
        onCheckedChange={(use_preferences) =>
          patch({ memory: { ...persona.memory, use_preferences } })
        }
      />
      <Switch
        label="Use episodes in context"
        checked={Boolean(persona.memory?.use_episodes)}
        onCheckedChange={(use_episodes) =>
          patch({ memory: { ...persona.memory, use_episodes } })
        }
      />
      <Input
        label="Max episodes in context"
        type="number"
        min={1}
        max={20}
        value={String(persona.memory?.max_episodes_in_context ?? 5)}
        onChange={(e) =>
          patch({
            memory: {
              ...persona.memory,
              max_episodes_in_context: num(e.target.value, 5),
            },
          })
        }
      />
      <Switch
        label="Confirm before saving memory"
        checked={Boolean(persona.memory?.confirm_before_save)}
        onCheckedChange={(confirm_before_save) =>
          patch({ memory: { ...persona.memory, confirm_before_save } })
        }
      />
      <Switch
        label="Ask when unsure"
        checked={Boolean(persona.boundaries?.ask_when_unsure)}
        onCheckedChange={(ask_when_unsure) =>
          patch({ boundaries: { ...persona.boundaries, ask_when_unsure } })
        }
      />
      <Input
        label="Never claim to have done"
        helper="Comma-separated verbs the assistant must not claim (booked, sent email, …)"
        value={((persona.boundaries?.never_claim_to_have_done as string[]) ?? []).join(", ")}
        onChange={(e) =>
          patch({
            boundaries: {
              ...persona.boundaries,
              never_claim_to_have_done: e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            },
          })
        }
      />
      <Button icon={<Save className="h-4 w-4" />} onClick={onSave} loading={saving}>
        Save persona settings
      </Button>
    </Card>
  );
}

export function ModelAdvancedPanel({ persona, onChange, onSave, saving }: Props) {
  const patchLlm = (partial: Partial<Persona["llm"]>) =>
    onChange({ ...persona, llm: { ...persona.llm, ...partial } });
  const patchPerf = (workers: number) =>
    onChange({ ...persona, performance: { ...persona.performance, workers } });

  return (
    <Card className="space-y-4">
      <SectionTitle>Ollama & performance</SectionTitle>
      <Input
        label="Ollama base URL"
        value={persona.llm.base_url}
        onChange={(e) => patchLlm({ base_url: e.target.value })}
      />
      <Input
        label="Temperature"
        type="number"
        min={0}
        max={2}
        step={0.1}
        value={String(persona.llm.temperature)}
        onChange={(e) => patchLlm({ temperature: num(e.target.value, 0.3) })}
      />
      <Input
        label="Request timeout (seconds)"
        type="number"
        min={30}
        value={String(persona.llm.timeout_seconds)}
        onChange={(e) => patchLlm({ timeout_seconds: num(e.target.value, 600) })}
      />
      <Input
        label="Max retries"
        type="number"
        min={0}
        max={5}
        value={String(persona.llm.max_retries)}
        onChange={(e) => patchLlm({ max_retries: num(e.target.value, 2) })}
      />
      <Input
        label="CPU threads per request"
        helper="0 = use all cores"
        type="number"
        min={0}
        value={String(persona.llm.num_threads)}
        onChange={(e) => patchLlm({ num_threads: num(e.target.value, 0) })}
      />
      <Input
        label="Parallel Ollama requests"
        helper="0 or 1 recommended on CPU-only"
        type="number"
        min={0}
        value={String(persona.llm.parallel_requests)}
        onChange={(e) => patchLlm({ parallel_requests: num(e.target.value, 0) })}
      />
      <Input
        label="Context window (tokens)"
        type="number"
        min={1024}
        value={String(persona.llm.context_window)}
        onChange={(e) => patchLlm({ context_window: num(e.target.value, 8192) })}
      />
      <Switch
        label="Chain-of-thought (thinking models)"
        helper="Show reasoning traces from Ollama thinking models (DeepSeek R1, Qwen3, …). Requires a compatible model."
        checked={Boolean(persona.llm.thinking_enabled)}
        onCheckedChange={(thinking_enabled) => patchLlm({ thinking_enabled })}
      />
      <Input
        label="Parallel ingest/extract workers"
        helper="0 = CPU cores - 1"
        type="number"
        min={0}
        value={String(persona.performance?.workers ?? 0)}
        onChange={(e) => patchPerf(num(e.target.value, 0))}
      />
      <Button icon={<Save className="h-4 w-4" />} onClick={onSave} loading={saving}>
        Save advanced model settings
      </Button>
    </Card>
  );
}

export function WebToolsPanel({
  persona,
  onChange,
  fetchSearchPages,
}: Props & { fetchSearchPages: boolean }) {
  const patchWeb = (partial: Partial<Persona["web_search"]>) =>
    onChange({ ...persona, web_search: { ...persona.web_search, ...partial } });
  const patchFirecrawl = (partial: Partial<Persona["firecrawl"]>) =>
    onChange({ ...persona, firecrawl: { ...persona.firecrawl, ...partial } });

  return (
    <>
      <Card className="space-y-4">
        <SectionTitle>Web search</SectionTitle>
        <Switch
          label="Web search in chat"
          helper="Allow DuckDuckGo search during conversations."
          checked={persona.web_search.enabled}
          onCheckedChange={(enabled) => patchWeb({ enabled })}
        />
        <Input
          label="Max search results"
          type="number"
          min={1}
          max={10}
          value={String(persona.web_search.max_results)}
          onChange={(e) => patchWeb({ max_results: num(e.target.value, 5) })}
          disabled={!persona.web_search.enabled}
        />
        <Input
          label="Search timeout (seconds)"
          type="number"
          min={1}
          max={60}
          value={String(persona.web_search.timeout_seconds)}
          onChange={(e) => patchWeb({ timeout_seconds: num(e.target.value, 10) })}
          disabled={!persona.web_search.enabled}
        />
      </Card>

      <Card className="space-y-4">
        <SectionTitle>Firecrawl</SectionTitle>
        <Switch
          label="Firecrawl page scraping"
          helper="Use a local Firecrawl instance for richer page content."
          checked={persona.firecrawl.enabled}
          onCheckedChange={(enabled) => patchFirecrawl({ enabled })}
        />
        {persona.firecrawl.enabled && (
          <>
            <Input
              label="Firecrawl base URL"
              value={persona.firecrawl.base_url}
              onChange={(e) => patchFirecrawl({ base_url: e.target.value })}
              placeholder="http://localhost:3002"
            />
            <Input
              label="Firecrawl API key"
              type="password"
              helper="Optional — only if USE_DB_AUTHENTICATION is enabled on Firecrawl"
              value={persona.firecrawl.api_key}
              onChange={(e) => patchFirecrawl({ api_key: e.target.value })}
            />
            <Input
              label="Scrape timeout (seconds)"
              type="number"
              min={5}
              max={120}
              value={String(persona.firecrawl.timeout_seconds)}
              onChange={(e) => patchFirecrawl({ timeout_seconds: num(e.target.value, 30) })}
            />
            <Input
              label="Max scraped characters"
              type="number"
              min={1000}
              max={50000}
              value={String(persona.firecrawl.max_chars)}
              onChange={(e) => patchFirecrawl({ max_chars: num(e.target.value, 8000) })}
            />
            <Switch
              label="Scrape search results in chat"
              checked={persona.firecrawl.scrape_in_chat}
              onCheckedChange={(scrape_in_chat) => patchFirecrawl({ scrape_in_chat })}
              disabled={!persona.web_search.enabled}
            />
            <Input
              label="Max pages per search"
              type="number"
              min={0}
              max={5}
              value={String(persona.firecrawl.max_pages_in_chat)}
              onChange={(e) =>
                patchFirecrawl({ max_pages_in_chat: num(e.target.value, 2) })
              }
              disabled={!persona.firecrawl.scrape_in_chat && !fetchSearchPages}
            />
          </>
        )}
      </Card>

      <Card className="space-y-4">
        <SectionTitle>Shell commands</SectionTitle>
        <Switch
          label="Shell commands in chat"
          helper="Run commands in a bubblewrap sandbox. The workspace is writable; the rest of the system is read-only. Sudo is blocked."
          checked={persona.shell?.enabled ?? false}
          onCheckedChange={(enabled) =>
            onChange({
              ...persona,
              shell: { ...persona.shell, enabled },
            })
          }
        />
        <Input
          label="Sandbox workspace"
          helper="Writable directory for shell commands (default: data/shell_workspace)"
          value={persona.shell?.workspace_dir ?? ""}
          onChange={(e) =>
            onChange({
              ...persona,
              shell: { ...persona.shell, workspace_dir: e.target.value },
            })
          }
          disabled={!persona.shell?.enabled}
          placeholder="data/shell_workspace"
        />
        <Switch
          label="Allow network in sandbox"
          helper="Off by default. When enabled, sandboxed commands can reach the network."
          checked={persona.shell?.allow_network ?? false}
          onCheckedChange={(allow_network) =>
            onChange({
              ...persona,
              shell: { ...persona.shell, allow_network },
            })
          }
          disabled={!persona.shell?.enabled}
        />
        <Input
          label="Command timeout (seconds)"
          type="number"
          min={1}
          max={300}
          value={String(persona.shell?.timeout_seconds ?? 30)}
          onChange={(e) =>
            onChange({
              ...persona,
              shell: { ...persona.shell, timeout_seconds: num(e.target.value, 30) },
            })
          }
          disabled={!persona.shell?.enabled}
        />
        <Input
          label="Max output characters"
          type="number"
          min={500}
          max={50000}
          value={String(persona.shell?.max_output_chars ?? 8000)}
          onChange={(e) =>
            onChange({
              ...persona,
              shell: { ...persona.shell, max_output_chars: num(e.target.value, 8000) },
            })
          }
          disabled={!persona.shell?.enabled}
        />
        <Input
          label="Max commands per message"
          type="number"
          min={1}
          max={10}
          value={String(persona.shell?.max_commands_per_turn ?? 5)}
          onChange={(e) =>
            onChange({
              ...persona,
              shell: { ...persona.shell, max_commands_per_turn: num(e.target.value, 5) },
            })
          }
          disabled={!persona.shell?.enabled}
        />
      </Card>
    </>
  );
}

export function PersonaTabIcon() {
  return <UserRound className="mr-1.5 h-3.5 w-3.5" />;
}
