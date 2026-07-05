import { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, SectionTitle } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Spinner } from "../components/ui/Spinner";
import { Switch } from "../components/ui/Switch";
import { useToast } from "../components/ui/Toast";
import { api, SourcePolicy, TrainingPolicy } from "../api";

const SOURCE_NAMES = ["email", "calendar", "search", "cursor", "claude", "openai", "whatsapp", "wiki"];

const DEFAULT_SOURCE: SourcePolicy = {
  ingest: true,
  extract: true,
  train: false,
  auto_approve_episodes: false,
  auto_approve_profile: false,
  auto_approve_preference: false,
  redact: true,
  self_only: false,
  user_only: false,
};

const TOGGLE_META: Record<keyof SourcePolicy, { label: string; helper: string }> = {
  ingest: {
    label: "Ingest",
    helper: "Accept and parse raw files for this source.",
  },
  extract: {
    label: "Extract to proposals",
    helper: "Run the LLM extractor to create memory proposals.",
  },
  train: {
    label: "Include in training",
    helper: "Include extracted data in nightly training export backlog.",
  },
  redact: {
    label: "Redact PII",
    helper: "Mask sensitive fields when parsing raw content.",
  },
  self_only: {
    label: "Self only",
    helper: "WhatsApp: only extract messages you sent (is_self=true).",
  },
  user_only: {
    label: "User only",
    helper: "Agent chats: only extract user turns, skip assistant replies.",
  },
  auto_approve_episodes: {
    label: "Auto-approve episodes",
    helper: "When phase is Policy, commit episode proposals without review.",
  },
  auto_approve_profile: {
    label: "Auto-approve profile",
    helper: "When phase is Policy, commit profile proposals without review.",
  },
  auto_approve_preference: {
    label: "Auto-approve preferences",
    helper: "When phase is Policy, commit preference proposals without review.",
  },
};

export default function PoliciesPage() {
  const [policy, setPolicy] = useState<TrainingPolicy | null>(null);
  const [capabilities, setCapabilities] = useState<Record<string, string[]>>({});
  const [descriptions, setDescriptions] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState("email");
  const toast = useToast();

  useEffect(() => {
    Promise.all([api.getPolicy(), api.getPolicyCapabilities()])
      .then(([p, caps]) => {
        setPolicy(p);
        setCapabilities(caps.sources);
        setDescriptions(caps.descriptions);
      })
      .catch(console.error);
  }, []);

  if (!policy) return <Spinner label="Loading policies…" />;

  const src: SourcePolicy = policy.sources[selected] ?? DEFAULT_SOURCE;
  const supported = new Set(capabilities[selected] ?? []);
  const pipelineToggles = (["ingest", "extract", "train"] as const).filter((k) => supported.has(k));
  const filterToggles = (["redact", "self_only", "user_only"] as const).filter((k) => supported.has(k));
  const autoToggles = (
    ["auto_approve_episodes", "auto_approve_profile", "auto_approve_preference"] as const
  ).filter((k) => supported.has(k));

  function updateSource(patch: Partial<SourcePolicy>) {
    setPolicy((prev) => {
      if (!prev) return prev;
      const current = prev.sources[selected] ?? DEFAULT_SOURCE;
      return {
        ...prev,
        sources: {
          ...prev.sources,
          [selected]: { ...current, ...patch },
        },
      };
    });
  }

  async function save() {
    if (!policy) return;
    const since_hours = Math.min(168, Math.max(1, policy.nightly.since_hours || 24));
    const normalized = { ...policy, nightly: { ...policy.nightly, since_hours } };
    setPolicy(normalized);
    await api.putPolicy(normalized);
    toast("success", "Saved", "Config database updated");
  }

  const phases = [
    { value: "review", label: "Review (manual approve)" },
    { value: "policy", label: "Policy (automated rules)" },
  ];

  function renderToggleGroup(title: string, keys: (keyof SourcePolicy)[]) {
    if (keys.length === 0) return null;
    return (
      <div className="space-y-4 [&+&]:mt-6 [&+&]:border-t [&+&]:border-line [&+&]:pt-6">
        <SectionTitle>{title}</SectionTitle>
        {keys.map((key) => {
          const meta = TOGGLE_META[key];
          return (
            <Switch
              key={`${selected}-${key}`}
              label={meta.label}
              helper={meta.helper}
              checked={src[key] as boolean}
              onCheckedChange={(v) => updateSource({ [key]: v })}
            />
          );
        })}
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Training & ingest policies"
        description="Per-source rules for ingest, extraction, and training. Only relevant toggles are shown for each source type."
      />

      <div className="space-y-5">
        <Select
          label="Global phase"
          className="max-w-sm"
          value={policy.phase}
          options={phases}
          onValueChange={(phase) => setPolicy((prev) => (prev ? { ...prev, phase } : prev))}
        />

        <Card className="space-y-4">
          <SectionTitle>Training schedule</SectionTitle>
          <Switch
            label="Nightly training enabled"
            helper="Schedules automated training export when the nightly job is enabled."
            checked={policy.nightly.enabled}
            onCheckedChange={(checked) =>
              setPolicy((prev) =>
                prev ? { ...prev, nightly: { ...prev.nightly, enabled: checked } } : prev
              )
            }
          />
          <div className="flex flex-wrap gap-4">
            <Input
              label="Run at"
              helper="Local time of day (24h) when the training job runs."
              type="time"
              className="w-40"
              disabled={!policy.nightly.enabled}
              value={policy.nightly.time}
              onChange={(e) => {
                const time = e.target.value;
                if (!time) return;
                setPolicy((prev) =>
                  prev ? { ...prev, nightly: { ...prev.nightly, time } } : prev
                );
              }}
            />
            <Input
              label="Lookback window (hours)"
              helper="Include data from the last N hours in each export (1–168)."
              type="number"
              min={1}
              max={168}
              className="w-52"
              disabled={!policy.nightly.enabled}
              value={policy.nightly.since_hours}
              onChange={(e) => {
                const since_hours = Number(e.target.value);
                setPolicy((prev) =>
                  prev ? { ...prev, nightly: { ...prev.nightly, since_hours } } : prev
                );
              }}
            />
          </div>
        </Card>

        <Select
          label="Source"
          className="max-w-xs"
          value={selected}
          options={SOURCE_NAMES.map((s) => ({ value: s, label: s }))}
          onValueChange={setSelected}
        />

        {descriptions[selected] && (
          <p className="max-w-2xl text-[13px] leading-5 text-ink-secondary">
            {descriptions[selected]}
          </p>
        )}

        <Card className="p-6">
          {renderToggleGroup("Pipeline", pipelineToggles)}
          {renderToggleGroup("Filtering & privacy", filterToggles)}
          {autoToggles.length > 0 &&
            renderToggleGroup(
              policy.phase === "policy" ? "Automation (active)" : "Automation (phase: Review)",
              autoToggles
            )}
        </Card>

        <Button onClick={save}>Save policies</Button>
      </div>
    </>
  );
}
