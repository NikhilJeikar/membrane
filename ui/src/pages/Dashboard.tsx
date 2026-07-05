import { Column, Grid, InlineLoading, Tag, Tile } from "@carbon/react";
import PageHeader from "../components/PageHeader";
import { Status } from "../api";

type Props = { status: Status | null };

type StatGroup = {
  title: string;
  items: { label: string; value: string | number; hint?: string; tag?: "green" | "red" | "gray" }[];
};

export default function DashboardPage({ status }: Props) {
  if (!status) {
    return <InlineLoading description="Loading status…" className="page-loading" />;
  }

  const groups: StatGroup[] = [
    {
      title: "Memory",
      items: [
        { label: "Pending review", value: status.pending_proposals, hint: "Needs approval", tag: status.pending_proposals > 0 ? "red" : "green" },
        { label: "Profile facts", value: status.profile_count },
        { label: "Preferences", value: status.preference_count },
        { label: "Episodes", value: status.episode_count },
      ],
    },
    {
      title: "Ingest",
      items: [
        { label: "Cursor sessions", value: status.cursor_parsed },
        { label: "Tracked files", value: status.tracked_entries },
        { label: "Needs re-extract", value: status.stale_extract_cursor },
        { label: "Chat sessions", value: status.chats },
      ],
    },
    {
      title: "System",
      items: [
        { label: "Ollama", value: status.ollama_ok ? "Online" : "Offline", tag: status.ollama_ok ? "green" : "red" },
        { label: "Model", value: status.ollama_model },
        { label: "Training phase", value: status.phase, tag: "gray" },
        { label: "Approved archive", value: status.approved_archive },
      ],
    },
  ];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Local control plane for memory review, ingest pipelines, and training policies. All data stays on your machine."
        breadcrumbs={[{ label: "shadow-pa", href: "/" }, { label: "Dashboard" }]}
      />

      {groups.map((group) => (
        <section key={group.title}>
          <h2 className="section-title">{group.title}</h2>
          <Grid fullWidth narrow>
            {group.items.map((item) => (
              <Column key={item.label} sm={4} md={4} lg={4} xlg={4}>
                <Tile className="stat-tile">
                  <div>
                    <p className="stat-tile__label">{item.label}</p>
                    <p className="stat-tile__value">{item.value}</p>
                  </div>
                  <div>
                    {item.tag && item.label === "Pending review" && (
                      <Tag type={item.tag} size="sm">
                        {status.pending_proposals > 0 ? "Review needed" : "Clear"}
                      </Tag>
                    )}
                    {item.tag && item.label === "Ollama" && (
                      <Tag type={item.tag} size="sm">
                        {status.ollama_ok ? "Connected" : "Start Ollama"}
                      </Tag>
                    )}
                    {item.hint && <span className="stat-tile__hint">{item.hint}</span>}
                  </div>
                </Tile>
              </Column>
            ))}
          </Grid>
        </section>
      ))}
    </>
  );
}
