import { useEffect, useState } from "react";
import {
  Button,
  DataTable,
  InlineLoading,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  ToastNotification,
} from "@carbon/react";
import { Renew } from "@carbon/icons-react";
import PageHeader from "../components/PageHeader";
import { api } from "../api";

export default function IngestPage() {
  const [stats, setStats] = useState<Record<string, { raw: number; parsed: number }> | null>(null);
  const [parsing, setParsing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = () => api.ingestStats().then(setStats).catch(console.error);

  useEffect(() => {
    load();
  }, []);

  async function parseAll() {
    setParsing(true);
    try {
      const result = await api.parseIngest("all");
      setToast(JSON.stringify(result, null, 2));
      load();
    } catch (e) {
      setToast(String(e));
    } finally {
      setParsing(false);
    }
  }

  if (!stats) return <InlineLoading description="Loading ingest stats…" />;

  const rows = Object.entries(stats).map(([source, s]) => ({
    id: source,
    source,
    raw: s.raw,
    parsed: s.parsed,
  }));

  const headers = [
    { key: "source", header: "Source" },
    { key: "raw", header: "Raw files" },
    { key: "parsed", header: "Parsed files" },
  ];

  return (
    <>
      <PageHeader
        title="Ingest"
        description="Raw → parsed pipeline with hash tracking. Unchanged files are skipped automatically."
        breadcrumbs={[{ label: "membrane", href: "/" }, { label: "Ingest" }]}
      />

      <Button
        renderIcon={Renew}
        onClick={parseAll}
        disabled={parsing}
        style={{ marginBottom: "1.5rem" }}
      >
        {parsing ? "Parsing…" : "Parse server sources now"}
      </Button>

      {toast && (
        <ToastNotification
          kind="info"
          title="Parse result"
          subtitle={toast.slice(0, 200)}
          onClose={() => setToast(null)}
          style={{ marginBottom: "1rem", maxWidth: "100%" }}
        />
      )}

      <DataTable rows={rows} headers={headers}>
        {({ rows, headers, getTableProps, getHeaderProps, getRowProps }) => (
          <TableContainer className="panel-tile">
            <Table {...getTableProps()} size="lg">
              <TableHead>
                <TableRow>
                  {headers.map((h) => (
                    <TableHeader {...getHeaderProps({ header: h })} key={h.key}>
                      {h.header}
                    </TableHeader>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow {...getRowProps({ row })} key={row.id}>
                    {row.cells.map((cell) => (
                      <TableCell key={cell.id}>{cell.value}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </DataTable>
    </>
  );
}
