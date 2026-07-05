import { useEffect, useState } from "react";
import { RefreshCw, Save } from "lucide-react";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, SectionTitle } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import { Spinner } from "../components/ui/Spinner";
import { Switch } from "../components/ui/Switch";
import { Table, TBody, TD, TH, THead, TR } from "../components/ui/Table";
import { Tag } from "../components/ui/Tag";
import { useToast } from "../components/ui/Toast";
import { api, IngestStats, SourcePolicy, TrainingPolicy } from "../api";

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

function BacklogTag({ count }: { count: number }) {
  return <Tag tone={count > 0 ? "red" : "green"}>{count}</Tag>;
}

export default function IngestPage() {
  const [stats, setStats] = useState<IngestStats | null>(null);
  const [policy, setPolicy] = useState<TrainingPolicy | null>(null);
  const [parsing, setParsing] = useState(false);
  const [savingTrain, setSavingTrain] = useState<string | null>(null);
  const [model, setModel] = useState("");
  const [extractorModel, setExtractorModel] = useState("");
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaOk, setOllamaOk] = useState(true);
  const [savingModel, setSavingModel] = useState(false);
  const toast = useToast();

  const load = async () => {
    const [ingest, persona, ollama, trainingPolicy] = await Promise.all([
      api.ingestStats(),
      api.getPersona(),
      api.ollamaModels().catch(() => ({ models: [], ollama_ok: false })),
      api.getPolicy(),
    ]);
    setStats(ingest);
    setPolicy(trainingPolicy);
    setModel(persona.llm.model);
    setExtractorModel(persona.llm.extractor_model);
    setOllamaModels(ollama.models);
    setOllamaOk(ollama.ollama_ok);
  };

  useEffect(() => {
    load().catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function parseAll() {
    setParsing(true);
    try {
      const result = await api.parseIngest("all");
      toast("info", "Parse result", JSON.stringify(result, null, 2));
      await load();
    } catch (e) {
      toast("error", "Parse failed", String(e));
    } finally {
      setParsing(false);
    }
  }

  async function saveModels() {
    setSavingModel(true);
    try {
      await api.putPersona({
        llm: {
          model: model.trim(),
          extractor_model: extractorModel.trim(),
        },
      });
      toast("success", "Model settings saved");
    } catch (e) {
      toast("error", "Failed to save model", String(e));
    } finally {
      setSavingModel(false);
    }
  }

  async function toggleTrain(source: string, enabled: boolean) {
    if (!policy) return;
    setSavingTrain(source);
    const current = policy.sources[source] ?? DEFAULT_SOURCE;
    const next: TrainingPolicy = {
      ...policy,
      sources: {
        ...policy.sources,
        [source]: { ...current, train: enabled },
      },
    };
    setPolicy(next);
    try {
      await api.putPolicy(next);
      toast(
        "success",
        enabled ? `Training enabled for ${source}` : `Training disabled for ${source}`
      );
      const ingest = await api.ingestStats();
      setStats(ingest);
    } catch (e) {
      setPolicy(policy);
      toast("error", "Failed to update training policy", String(e));
    } finally {
      setSavingTrain(null);
    }
  }

  if (!stats || !policy) return <Spinner label="Loading ingest stats…" />;

  const rows = Object.entries(stats.sources).map(([source, s]) => ({
    source,
    raw: s.raw,
    parsed: s.parsed,
    needs_parse: s.needs_parse,
    needs_extract: s.needs_extract,
    needs_train: s.needs_train,
    train: (policy.sources[source] ?? DEFAULT_SOURCE).train,
  }));

  const summary = [
    { label: "Needs parse", value: stats.totals.needs_parse, hint: "Raw files waiting to be parsed" },
    { label: "Needs extract", value: stats.totals.needs_extract, hint: "Parsed docs waiting for LLM extraction" },
    { label: "Needs train", value: stats.totals.needs_train, hint: "Extract backlog from train-enabled sources" },
  ];

  function modelOptions(current: string) {
    const options = ollamaModels.map((m) => ({ value: m, label: m }));
    if (current && !ollamaModels.includes(current)) {
      options.unshift({ value: current, label: `${current} (not installed)` });
    }
    return options;
  }

  return (
    <>
      <PageHeader
        title="Ingest"
        description="Track the raw → parsed → extract pipeline and configure which Ollama models run inference and extraction."
      />

      <section>
        <SectionTitle className="mb-3">Pipeline backlog</SectionTitle>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {summary.map((item) => (
            <Card key={item.label} className="flex min-h-[7rem] flex-col justify-between">
              <div>
                <p className="text-[13px] text-ink-secondary">{item.label}</p>
                <p className="mt-1.5 text-2xl font-light text-ink-primary">{item.value}</p>
              </div>
              <span className="mt-3 text-xs text-ink-muted">{item.hint}</span>
            </Card>
          ))}
        </div>
      </section>

      <Card className="mt-6">
        <SectionTitle className="mb-4">Model settings</SectionTitle>
        <div className="flex flex-wrap items-start gap-4">
          <Select
            label="Inference model"
            helper="Used for chat and inference"
            placeholder="Select a model"
            value={model}
            options={modelOptions(model)}
            onValueChange={setModel}
            className="w-64"
          />
          <Select
            label="Extractor model"
            helper="Used when extracting memory from parsed docs"
            placeholder="Select a model"
            value={extractorModel}
            options={modelOptions(extractorModel)}
            onValueChange={setExtractorModel}
            className="w-64"
          />
          <Button
            icon={<Save className="h-4 w-4" />}
            onClick={saveModels}
            loading={savingModel}
            disabled={!model.trim() || !extractorModel.trim()}
            className="mt-[26px]"
          >
            {savingModel ? "Saving…" : "Save models"}
          </Button>
        </div>
        {!ollamaOk && (
          <p className="mt-3 text-xs text-ink-muted">
            Ollama is not reachable — showing only the configured models. Start it with{" "}
            <code>ollama serve</code> to list installed models.
          </p>
        )}
      </Card>

      <div className="my-6">
        <Button
          variant="secondary"
          icon={<RefreshCw className="h-4 w-4" />}
          onClick={parseAll}
          loading={parsing}
        >
          {parsing ? "Parsing…" : "Parse server sources now"}
        </Button>
      </div>

      <Table>
        <THead>
          <TR>
            <TH>Source</TH>
            <TH>Raw files</TH>
            <TH>Parsed files</TH>
            <TH>Needs parse</TH>
            <TH>Needs extract</TH>
            <TH>Needs train</TH>
            <TH>Train enabled</TH>
          </TR>
        </THead>
        <TBody>
          {rows.map((row) => (
            <TR key={row.source}>
              <TD className="font-medium">{row.source}</TD>
              <TD>{row.raw}</TD>
              <TD>{row.parsed}</TD>
              <TD>
                <BacklogTag count={row.needs_parse} />
              </TD>
              <TD>
                <BacklogTag count={row.needs_extract} />
              </TD>
              <TD>
                <BacklogTag count={row.needs_train} />
              </TD>
              <TD>
                <Switch
                  checked={row.train}
                  disabled={savingTrain === row.source}
                  onCheckedChange={(checked) => toggleTrain(row.source, checked)}
                />
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </>
  );
}
