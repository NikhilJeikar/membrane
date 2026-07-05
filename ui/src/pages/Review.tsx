import { useCallback, useEffect, useState } from "react";
import {
  Button,
  ButtonSet,
  Dropdown,
  InlineLoading,
  ProgressBar,
  Tag,
} from "@carbon/react";
import { Checkmark, Close, ArrowRight } from "@carbon/icons-react";
import PageHeader from "../components/PageHeader";
import { api, Proposal } from "../api";

const categories = [
  { id: "", label: "All categories" },
  { id: "profile", label: "Profile" },
  { id: "preference", label: "Preference" },
  { id: "episode", label: "Episode" },
];

export default function ReviewPage() {
  const [items, setItems] = useState<Proposal[]>([]);
  const [total, setTotal] = useState(0);
  const [index, setIndex] = useState(0);
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.proposed(category || undefined);
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

  if (loading) return <InlineLoading description="Loading proposals…" />;

  return (
    <>
      <PageHeader
        title="Memory review"
        description="Approve or reject extracted memory. Approved items commit to profile.json, preferences.json, and episodes.jsonl."
        breadcrumbs={[
          { label: "shadow-pa", href: "/" },
          { label: "Memory review" },
        ]}
      />

      <div className="review-layout">
        <aside className="review-sidebar">
          <Dropdown
            id="category-filter"
            titleText="Filter"
            label={categories.find((c) => c.id === category)?.label ?? "All categories"}
            items={categories}
            itemToString={(i) => (i ? i.label : "")}
            selectedItem={categories.find((c) => c.id === category)}
            onChange={({ selectedItem }) => setCategory(selectedItem?.id ?? "")}
          />

          {total > 0 && (
            <div style={{ marginTop: "1.5rem" }}>
              <p className="review-card__meta">
                {position} of {items.length} in view · {total} pending total
              </p>
              <ProgressBar
                label="Queue"
                value={items.length > 0 ? Math.round((position / items.length) * 100) : 0}
              />
            </div>
          )}

          <div style={{ marginTop: "1.5rem" }}>
            <Button kind="ghost" size="sm" onClick={load}>
              Refresh list
            </Button>
          </div>
        </aside>

        <main>
          {!current ? (
            <div className="empty-state">
              <h3>No pending proposals</h3>
              <p>Run extract or change the category filter to see more items.</p>
            </div>
          ) : (
            <article className="review-card">
              <div className="review-card__tags">
                <Tag type="blue">{current.category}</Tag>
                <Tag type="gray">{current.source}</Tag>
                <Tag type="purple" title={current.id}>
                  {current.id.slice(0, 8)}…
                </Tag>
              </div>

              <h2 className="review-card__summary">{current.summary}</h2>

              {current.reason && (
                <p className="review-card__meta">
                  <strong>Reason:</strong> {current.reason}
                </p>
              )}

              {current.existing_note && (
                <div className="review-card__warning">{current.existing_note}</div>
              )}

              <details style={{ marginTop: "1rem" }}>
                <summary style={{ cursor: "pointer", marginBottom: "0.5rem" }}>
                  Raw detail
                </summary>
                <pre className="detail-pre">{JSON.stringify(current.detail, null, 2)}</pre>
              </details>

              <ButtonSet style={{ marginTop: "1.5rem" }}>
                <Button
                  kind="primary"
                  disabled={busy}
                  renderIcon={Checkmark}
                  onClick={() => act("approve")}
                >
                  Approve
                </Button>
                <Button
                  kind="danger--tertiary"
                  disabled={busy}
                  renderIcon={Close}
                  onClick={() => act("reject")}
                >
                  Reject
                </Button>
                <Button
                  kind="ghost"
                  disabled={busy}
                  renderIcon={ArrowRight}
                  onClick={() => act("skip")}
                >
                  Skip
                </Button>
              </ButtonSet>
            </article>
          )}
        </main>
      </div>
    </>
  );
}
