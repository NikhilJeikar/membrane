import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Check, RefreshCw, X } from "lucide-react";
import PageHeader from "../components/PageHeader";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { CodeBlock } from "../components/ui/CodeBlock";
import { EmptyState } from "../components/ui/EmptyState";
import { Select } from "../components/ui/Select";
import { Spinner } from "../components/ui/Spinner";
import { Tag } from "../components/ui/Tag";
import { api, Proposal } from "../api";

const categories = [
  { value: "all", label: "All categories" },
  { value: "profile", label: "Profile" },
  { value: "preference", label: "Preference" },
  { value: "episode", label: "Episode" },
];

export default function ReviewPage() {
  const [items, setItems] = useState<Proposal[]>([]);
  const [total, setTotal] = useState(0);
  const [index, setIndex] = useState(0);
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.proposed(category === "all" ? undefined : category);
      setItems(data.items);
      setTotal(data.total);
      setIndex(0);
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    load();
  }, [load]);

  const current = items[index];
  const position = items.length > 0 ? index + 1 : 0;
  const progress = items.length > 0 ? Math.round((position / items.length) * 100) : 0;

  async function act(action: "approve" | "reject" | "skip") {
    if (!current || action === "skip") {
      setIndex((i) => Math.min(i + 1, Math.max(0, items.length - 1)));
      return;
    }
    setBusy(true);
    try {
      if (action === "approve") await api.approve(current.id);
      else await api.reject(current.id);
      const next = items.filter((p) => p.id !== current.id);
      setItems(next);
      setTotal((t) => t - 1);
      setIndex((i) => Math.min(i, Math.max(0, next.length - 1)));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner label="Loading proposals…" />;

  return (
    <>
      <PageHeader
        title="Memory review"
        description="Approve or reject extracted memory. Approved items commit to profile.json, preferences.json, and episodes.jsonl."
      />

      <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-[260px_1fr]">
        <aside className="space-y-5 md:sticky md:top-4">
          <Select
            label="Filter"
            value={category}
            options={categories}
            onValueChange={setCategory}
          />

          {total > 0 && (
            <div>
              <p className="mb-2 text-[13px] text-ink-secondary">
                {position} of {items.length} in view · {total} pending total
              </p>
              <div className="h-1 w-full overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-accent transition-[width]"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          <Button variant="ghost" size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={load}>
            Refresh list
          </Button>
        </aside>

        <main>
          {!current ? (
            <EmptyState
              title="No pending proposals"
              description="Run extract or change the category filter to see more items."
            />
          ) : (
            <Card className="p-6">
              <div className="mb-4 flex flex-wrap gap-2">
                <Tag tone="blue">{current.category}</Tag>
                <Tag tone="gray">{current.source}</Tag>
                <Tag tone="purple" title={current.id}>
                  {current.id.slice(0, 8)}…
                </Tag>
              </div>

              <h2 className="mb-4 text-lg leading-normal text-ink-primary">{current.summary}</h2>

              {current.reason && (
                <p className="mb-3 text-[13px] text-ink-secondary">
                  <strong className="font-medium text-ink-primary">Reason:</strong> {current.reason}
                </p>
              )}

              {current.existing_note && (
                <div className="mb-4 rounded-md border-l-2 border-amber-400 bg-amber-500/10 px-4 py-3 text-[13px] text-amber-200">
                  {current.existing_note}
                </div>
              )}

              <details className="mt-4">
                <summary className="mb-2 cursor-pointer text-[13px] text-ink-secondary hover:text-ink-primary">
                  Raw detail
                </summary>
                <CodeBlock code={JSON.stringify(current.detail, null, 2)} />
              </details>

              <div className="mt-6 flex flex-wrap gap-2">
                <Button
                  disabled={busy}
                  icon={<Check className="h-4 w-4" />}
                  onClick={() => act("approve")}
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  disabled={busy}
                  icon={<X className="h-4 w-4" />}
                  onClick={() => act("reject")}
                >
                  Reject
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  icon={<ArrowRight className="h-4 w-4" />}
                  onClick={() => act("skip")}
                >
                  Skip
                </Button>
              </div>
            </Card>
          )}
        </main>
      </div>
    </>
  );
}
