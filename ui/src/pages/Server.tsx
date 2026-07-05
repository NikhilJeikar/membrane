import { useEffect, useState } from "react";
import { CodeSnippet, Column, Grid, InlineLoading, Tile } from "@carbon/react";
import PageHeader from "../components/PageHeader";
import { api } from "../api";

export default function ServerPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.serverStatus().then(setData).catch(console.error);
  }, []);

  if (!data) return <InlineLoading description="Loading server status…" />;

  const curlExample = `curl -X POST http://${data.host}:${data.port}/v1/ingest/search \\
  -H "Authorization: Bearer ${data.token}" \\
  -H "Content-Type: application/json" \\
  -d '{"items":[{"query":"example search","engine":"google"}]}'`;

  return (
    <>
      <PageHeader
        title="Ingest server"
        description="Local HTTP collector for email, calendar, and search history. Start with shadow-pa server run."
        breadcrumbs={[{ label: "shadow-pa", href: "/" }, { label: "Server" }]}
      />

      <Grid narrow fullWidth>
        <Column sm={4} md={4} lg={8}>
          <Tile className="panel-tile">
            <p><strong>Endpoint</strong> {String(data.host)}:{String(data.port)}</p>
            <p><strong>Parse interval</strong> {String(data.parse_interval_seconds)}s</p>
            <p><strong>Auto extract</strong> {String(data.auto_extract)}</p>
            <p style={{ marginTop: "1rem" }}><strong>Auth token</strong></p>
            <CodeSnippet type="single" feedback="Copied to clipboard">
              {String(data.token)}
            </CodeSnippet>
          </Tile>
        </Column>
        <Column sm={4} md={4} lg={8}>
          <Tile className="panel-tile">
            <p><strong>Source counts</strong></p>
            <pre className="detail-pre" style={{ maxHeight: "12rem" }}>
              {JSON.stringify(data.sources, null, 2)}
            </pre>
          </Tile>
        </Column>
      </Grid>

      <h3 className="section-title">Example request</h3>
      <CodeSnippet type="multi" feedback="Copied to clipboard">
        {curlExample}
      </CodeSnippet>
    </>
  );
}
