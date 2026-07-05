import { useEffect, useState } from "react";
import { Check, Copy, Save } from "lucide-react";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { Card, SectionTitle } from "../components/ui/Card";
import { CodeBlock } from "../components/ui/CodeBlock";
import { Input } from "../components/ui/Input";
import { Spinner } from "../components/ui/Spinner";
import { Switch } from "../components/ui/Switch";
import { Table, TBody, TD, TH, THead, TR } from "../components/ui/Table";
import { useToast } from "../components/ui/Toast";
import { api, ServerStatus } from "../api";

type FormState = {
  host: string;
  port: string;
  token: string;
  parseInterval: string;
  autoExtract: boolean;
};

export default function ServerPage() {
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const toast = useToast();

  useEffect(() => {
    Promise.all([api.serverStatus(), api.getPersona()])
      .then(([data, persona]) => {
        setStatus(data);
        setForm({
          host: data.host,
          port: String(data.port),
          token: persona.server.token,
          parseInterval: String(data.parse_interval_seconds),
          autoExtract: data.auto_extract,
        });
      })
      .catch(console.error);
  }, []);

  if (!status || !form) return <Spinner label="Loading server status…" />;

  const port = Number(form.port);
  const parseInterval = Number(form.parseInterval);
  const portValid = Number.isInteger(port) && port >= 1 && port <= 65535;
  const intervalValid = Number.isInteger(parseInterval) && parseInterval >= 30;
  const canSave = form.host.trim() !== "" && portValid && intervalValid && !saving;

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  // Effective token: persona override if set, else the auto-generated file token.
  const effectiveToken = form.token.trim() || status.token;

  async function copyToken() {
    await navigator.clipboard.writeText(effectiveToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function save() {
    if (!form) return;
    setSaving(true);
    try {
      const persona = await api.putPersona({
        server: {
          host: form.host.trim(),
          port,
          token: form.token.trim(),
          parse_interval_seconds: parseInterval,
          auto_extract: form.autoExtract,
        },
      });
      const server = persona.server;
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              host: server.host,
              port: server.port,
              parse_interval_seconds: server.parse_interval_seconds,
              auto_extract: server.auto_extract,
            }
          : prev
      );
      toast("success", "Server settings saved", "Restart `membrane server run` to apply changes.");
    } catch (e) {
      toast("error", "Failed to save server settings", String(e));
    } finally {
      setSaving(false);
    }
  }

  const curlExample = `curl -X POST http://${form.host}:${form.port}/v1/ingest/search \\
  -H "Authorization: Bearer ${effectiveToken}" \\
  -H "Content-Type: application/json" \\
  -d '{"items":[{"query":"example search","engine":"google"}]}'`;

  return (
    <>
      <PageHeader
        title="Ingest server"
        description="Local HTTP collector for email, calendar, and search history. Start with membrane server run."
      />

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Card>
          <SectionTitle className="mb-4">Connection settings</SectionTitle>
          <div className="space-y-4">
            <div className="grid grid-cols-[1fr_8rem] gap-3">
              <Input
                label="Host"
                value={form.host}
                onChange={(e) => set("host", e.target.value)}
              />
              <Input
                label="Port"
                type="number"
                min={1}
                max={65535}
                value={form.port}
                helper={portValid ? undefined : "1–65535"}
                onChange={(e) => set("port", e.target.value)}
              />
            </div>
            <Input
              label="Parse interval (seconds)"
              helper="How often raw files are parsed. Minimum 30."
              type="number"
              min={30}
              value={form.parseInterval}
              onChange={(e) => set("parseInterval", e.target.value)}
            />
            <Switch
              label="Auto extract"
              helper="After parsing, run the offline extractor and create proposals."
              checked={form.autoExtract}
              onCheckedChange={(v) => set("autoExtract", v)}
            />
            <div className="flex items-end gap-2">
              <Input
                label="Auth token"
                helper="Leave empty to use the auto-generated token."
                placeholder={status.token}
                value={form.token}
                onChange={(e) => set("token", e.target.value)}
                className="flex-1"
                inputClassName="font-mono text-[13px]"
              />
              <Button
                variant="secondary"
                size="icon"
                aria-label="Copy token"
                className="mb-[26px] h-9 w-9"
                icon={
                  copied ? (
                    <Check className="h-4 w-4 text-emerald-400" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )
                }
                onClick={copyToken}
              />
            </div>
            <div className="flex items-center gap-3 border-t border-line pt-4">
              <Button
                icon={<Save className="h-4 w-4" />}
                onClick={save}
                loading={saving}
                disabled={!canSave}
              >
                {saving ? "Saving…" : "Save settings"}
              </Button>
              <p className="text-xs text-ink-muted">Restart the server to apply changes.</p>
            </div>
          </div>
        </Card>

        <Card>
          <SectionTitle className="mb-4">Source counts</SectionTitle>
          <Table>
            <THead>
              <TR>
                <TH>Source</TH>
                <TH className="text-right">Raw files</TH>
                <TH className="text-right">Parsed files</TH>
              </TR>
            </THead>
            <TBody>
              {Object.entries(status.sources).map(([source, counts]) => (
                <TR key={source}>
                  <TD className="font-medium">{source}</TD>
                  <TD className="text-right tabular-nums">{counts.raw}</TD>
                  <TD className="text-right tabular-nums">{counts.parsed}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      </div>

      <SectionTitle className="mb-3 mt-8">Example request</SectionTitle>
      <CodeBlock code={curlExample} />
    </>
  );
}
