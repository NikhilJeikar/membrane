import { useEffect, useState } from "react";
import {
  Button,
  Dropdown,
  InlineLoading,
  Toggle,
  Tile,
  ToastNotification,
} from "@carbon/react";
import PageHeader from "../components/PageHeader";
import { api, SourcePolicy, TrainingPolicy } from "../api";

const SOURCE_NAMES = ["email", "calendar", "search", "cursor", "whatsapp", "wiki"];

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

export default function PoliciesPage() {
  const [policy, setPolicy] = useState<TrainingPolicy | null>(null);
  const [selected, setSelected] = useState("email");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getPolicy().then(setPolicy).catch(console.error);
  }, []);

  if (!policy) return <InlineLoading description="Loading policies…" />;

  const src: SourcePolicy = policy.sources[selected] ?? DEFAULT_SOURCE;

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
    await api.putPolicy(policy);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

  const phases = [
    { id: "review", label: "Review (manual approve)" },
    { id: "policy", label: "Policy (automated rules)" },
  ];

  const toggles: { id: string; label: string; key: keyof SourcePolicy }[] = [
    { id: "ingest", label: "Ingest", key: "ingest" },
    { id: "extract", label: "Extract to proposals", key: "extract" },
    { id: "train", label: "Include in nightly training", key: "train" },
    { id: "redact", label: "Redact PII", key: "redact" },
    { id: "self_only", label: "Self only (WhatsApp / sent mail)", key: "self_only" },
    { id: "user_only", label: "User only (Cursor)", key: "user_only" },
    { id: "auto_approve_episodes", label: "Auto-approve episodes", key: "auto_approve_episodes" },
    { id: "auto_approve_profile", label: "Auto-approve profile", key: "auto_approve_profile" },
  ];

  return (
    <>
      <PageHeader
        title="Training & ingest policies"
        description="Phase 1: manual review. Phase 2: per-source rules for nightly ingest, extract, and training."
        breadcrumbs={[{ label: "shadow-pa", href: "/" }, { label: "Policies" }]}
      />

      <Dropdown
        id="phase"
        titleText="Global phase"
        label={policy.phase}
        items={phases}
        itemToString={(i) => (i ? i.label : "")}
        selectedItem={phases.find((p) => p.id === policy.phase)}
        onChange={({ selectedItem }) =>
          selectedItem &&
          setPolicy((prev) => (prev ? { ...prev, phase: selectedItem.id } : prev))
        }
        style={{ maxWidth: 360, marginTop: "1rem" }}
      />

      <Tile className="panel-tile" style={{ marginTop: "1rem" }}>
        <Toggle
          id="nightly"
          labelText="Nightly training enabled"
          toggled={policy.nightly.enabled}
          onToggle={(checked) =>
            setPolicy((prev) =>
              prev ? { ...prev, nightly: { ...prev.nightly, enabled: checked } } : prev
            )
          }
        />
      </Tile>

      <Dropdown
        id="source"
        titleText="Source"
        label={selected}
        items={SOURCE_NAMES.map((s) => ({ id: s, label: s }))}
        itemToString={(i) => (i ? i.label : "")}
        selectedItem={{ id: selected, label: selected }}
        onChange={({ selectedItem }) => selectedItem && setSelected(selectedItem.id)}
        style={{ maxWidth: 280, marginTop: "1.5rem" }}
      />

      <Tile className="policy-source" style={{ marginTop: "1rem" }}>
        {toggles.map((t) => (
          <Toggle
            key={t.id}
            id={`${selected}-${t.id}`}
            labelText={t.label}
            toggled={src[t.key] as boolean}
            onToggle={(v) => updateSource({ [t.key]: v })}
          />
        ))}
      </Tile>

      <Button onClick={save} style={{ marginTop: "1rem" }}>
        Save policies
      </Button>
      {saved && (
        <ToastNotification kind="success" title="Saved" subtitle="training_policy.yaml updated" />
      )}
    </>
  );
}
