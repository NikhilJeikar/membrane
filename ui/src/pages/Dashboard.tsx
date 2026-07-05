import PageHeader from "../components/PageHeader";
import { Card, SectionTitle } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { Tag, TagTone } from "../components/ui/Tag";
import { Status } from "../api";

type Props = { status: Status | null };

type StatItem = {
  label: string;
  value: string | number;
  hint?: string;
  tag?: { tone: TagTone; label: string };
};

type StatGroup = { title: string; items: StatItem[] };

export default function DashboardPage({ status }: Props) {
  if (!status) {
    return <Spinner label="Loading status…" />;
  }

  const groups: StatGroup[] = [
    {
      title: "Memory",
      items: [
        {
          label: "Pending review",
          value: status.pending_proposals,
          hint: "Needs approval",
          tag:
            status.pending_proposals > 0
              ? { tone: "red", label: "Review needed" }
              : { tone: "green", label: "Clear" },
        },
        { label: "Profile facts", value: status.profile_count },
        { label: "Preferences", value: status.preference_count },
        { label: "Episodes", value: status.episode_count },
      ],
    },
    {
      title: "Ingest",
      items: [
        { label: "Agent sessions", value: status.agent_sessions },
        { label: "Tracked files", value: status.tracked_entries },
        { label: "Needs re-extract", value: status.stale_extract_agents },
        { label: "Chat sessions", value: status.chats },
      ],
    },
    {
      title: "System",
      items: [
        {
          label: "Ollama",
          value: status.ollama_ok ? "Online" : "Offline",
          tag: status.ollama_ok
            ? { tone: "green", label: "Connected" }
            : { tone: "red", label: "Start Ollama" },
        },
        { label: "Model", value: status.ollama_model },
        { label: "Training phase", value: status.phase },
        { label: "Approved archive", value: status.approved_archive },
      ],
    },
  ];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Local control plane for memory review, ingest pipelines, and training policies. All data stays on your machine."
      />

      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.title}>
            <SectionTitle className="mb-3">{group.title}</SectionTitle>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {group.items.map((item) => (
                <Card key={item.label} className="flex min-h-[7rem] flex-col justify-between">
                  <div>
                    <p className="text-[13px] text-ink-secondary">{item.label}</p>
                    <p className="mt-1.5 truncate text-2xl font-light text-ink-primary" title={String(item.value)}>
                      {item.value}
                    </p>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    {item.tag && <Tag tone={item.tag.tone}>{item.tag.label}</Tag>}
                    {item.hint && <span className="text-xs text-ink-muted">{item.hint}</span>}
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
