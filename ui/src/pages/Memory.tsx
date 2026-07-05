import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { EmptyState } from "../components/ui/EmptyState";
import { Input } from "../components/ui/Input";
import { Spinner } from "../components/ui/Spinner";
import { Table, TBody, TD, TH, THead, TR } from "../components/ui/Table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/Tabs";
import { useToast } from "../components/ui/Toast";
import {
  api,
  MemorySnapshot,
  PreferenceEntry,
  ProfileEntry,
} from "../api";

type EntryKind = "profile" | "preference";

type FormState = {
  key: string;
  value: string;
  confidence: number;
  strength: number;
};

const emptyForm = (): FormState => ({
  key: "",
  value: "",
  confidence: 0.8,
  strength: 0.7,
});

export default function MemoryPage() {
  const [snapshot, setSnapshot] = useState<MemorySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [kind, setKind] = useState<EntryKind>("profile");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [deleteTarget, setDeleteTarget] = useState<{ kind: EntryKind; key: string } | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSnapshot(await api.memorySnapshot());
    } catch (err) {
      console.error(err);
      toast("error", "Failed to load memory");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  function openAdd(entryKind: EntryKind) {
    setKind(entryKind);
    setEditingKey(null);
    setForm(emptyForm());
    setModalOpen(true);
  }

  function openEdit(entryKind: EntryKind, entry: ProfileEntry | PreferenceEntry) {
    setKind(entryKind);
    setEditingKey(entry.key);
    setForm({
      key: entry.key,
      value: entry.value,
      confidence: "confidence" in entry ? entry.confidence : 0.8,
      strength: "strength" in entry ? entry.strength : 0.7,
    });
    setModalOpen(true);
  }

  function openDelete(entryKind: EntryKind, key: string) {
    setDeleteTarget({ kind: entryKind, key });
    setDeleteOpen(true);
  }

  async function saveEntry() {
    if (!form.key.trim() || !form.value.trim()) {
      toast("error", "Key and value are required");
      return;
    }
    setBusy(true);
    try {
      if (kind === "profile") {
        await api.upsertProfile({
          key: form.key.trim(),
          value: form.value.trim(),
          confidence: form.confidence,
        });
      } else {
        await api.upsertPreference({
          key: form.key.trim(),
          value: form.value.trim(),
          strength: form.strength,
        });
      }
      setModalOpen(false);
      toast("success", editingKey ? "Entry updated" : "Entry added");
      await load();
    } catch (err) {
      console.error(err);
      toast("error", "Failed to save entry");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      if (deleteTarget.kind === "profile") {
        await api.deleteProfile(deleteTarget.key);
      } else {
        await api.deletePreference(deleteTarget.key);
      }
      setDeleteOpen(false);
      setDeleteTarget(null);
      toast("success", "Entry deleted");
      await load();
    } catch (err) {
      console.error(err);
      toast("error", "Failed to delete entry");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !snapshot) return <Spinner label="Loading memory…" />;

  const { profile, preferences: prefs, episodes } = snapshot ?? {
    profile: [],
    preferences: [],
    episodes: [],
  };

  type Row = {
    id: string;
    key: string;
    value: string;
    meta: string;
    entry: ProfileEntry | PreferenceEntry;
  };

  const profileRows: Row[] = profile.map((r) => ({
    id: r.id || r.key,
    key: r.key,
    value: r.value,
    meta: `confidence ${(r.confidence * 100).toFixed(0)}%`,
    entry: r,
  }));

  const preferenceRows: Row[] = prefs.map((r) => ({
    id: r.id || r.key,
    key: r.key,
    value: r.value,
    meta: `strength ${(r.strength * 100).toFixed(0)}%`,
    entry: r,
  }));

  function renderTable(entryKind: EntryKind, rows: Row[]) {
    if (rows.length === 0) {
      return (
        <EmptyState
          title={`No ${entryKind === "profile" ? "profile facts" : "preferences"} yet`}
          description="Add entries manually or approve extracted proposals on the review page."
        />
      );
    }
    return (
      <Table>
        <THead>
          <TR>
            <TH>Key</TH>
            <TH>Value</TH>
            <TH>Meta</TH>
            <TH className="w-24" />
          </TR>
        </THead>
        <TBody>
          {rows.map((row) => (
            <TR key={row.id}>
              <TD className="font-medium">{row.key}</TD>
              <TD className="max-w-md">{row.value}</TD>
              <TD className="whitespace-nowrap text-ink-secondary">{row.meta}</TD>
              <TD>
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Edit"
                    icon={<Pencil className="h-3.5 w-3.5" />}
                    onClick={() => openEdit(entryKind, row.entry)}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Delete"
                    icon={<Trash2 className="h-3.5 w-3.5" />}
                    onClick={() => openDelete(entryKind, row.key)}
                  />
                </div>
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    );
  }

  return (
    <>
      <PageHeader
        title="Live memory"
        description="Committed facts injected at inference time. Add or edit profile and preferences directly."
      />

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile ({profile.length})</TabsTrigger>
          <TabsTrigger value="preferences">Preferences ({prefs.length})</TabsTrigger>
          <TabsTrigger value="episodes">Episodes ({episodes.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <div className="mb-4">
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => openAdd("profile")}>
              Add profile fact
            </Button>
          </div>
          {renderTable("profile", profileRows)}
        </TabsContent>

        <TabsContent value="preferences">
          <div className="mb-4">
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => openAdd("preference")}>
              Add preference
            </Button>
          </div>
          {renderTable("preference", preferenceRows)}
        </TabsContent>

        <TabsContent value="episodes">
          {episodes.length === 0 ? (
            <EmptyState
              title="No episodes yet"
              description="Approve episodic proposals to build timeline memory."
            />
          ) : (
            <div className="space-y-3">
              {episodes.map((ep) => (
                <article
                  key={ep.id}
                  className="rounded-md border-l-2 border-accent bg-surface-card px-4 py-3"
                >
                  <p className="text-[11px] uppercase tracking-wide text-ink-muted">
                    {ep.tags?.join(" · ") || "general"}
                  </p>
                  <p className="mt-1.5 text-sm leading-6 text-ink-primary">{ep.summary}</p>
                </article>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <Dialog
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingKey ? `Edit ${kind}` : `Add ${kind}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button loading={busy} onClick={saveEntry}>
              {editingKey ? "Save" : "Add"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Key"
            placeholder="e.g. location, communication_style"
            value={form.key}
            disabled={!!editingKey}
            onChange={(e) => setForm((prev) => ({ ...prev, key: e.target.value }))}
          />
          <Input
            label="Value"
            placeholder="The fact or preference"
            value={form.value}
            onChange={(e) => setForm((prev) => ({ ...prev, value: e.target.value }))}
          />
          {kind === "profile" ? (
            <Input
              label="Confidence"
              helper="How certain you are (0–1)"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={form.confidence}
              onChange={(e) => {
                const value = Number(e.target.value);
                setForm((prev) => ({
                  ...prev,
                  confidence: Number.isFinite(value) ? value : prev.confidence,
                }));
              }}
            />
          ) : (
            <Input
              label="Strength"
              helper="How strongly this preference applies (0–1)"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={form.strength}
              onChange={(e) => {
                const value = Number(e.target.value);
                setForm((prev) => ({
                  ...prev,
                  strength: Number.isFinite(value) ? value : prev.strength,
                }));
              }}
            />
          )}
        </div>
      </Dialog>

      <Dialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete entry"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={busy} onClick={confirmDelete}>
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-ink-secondary">
          Delete <strong className="text-ink-primary">{deleteTarget?.key}</strong>? This cannot be
          undone.
        </p>
      </Dialog>
    </>
  );
}
