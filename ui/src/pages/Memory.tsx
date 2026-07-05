import { useEffect, useState } from "react";
import {
  DataTable,
  InlineLoading,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
} from "@carbon/react";
import PageHeader from "../components/PageHeader";
import { api, MemorySnapshot } from "../api";

export default function MemoryPage() {
  const [snapshot, setSnapshot] = useState<MemorySnapshot | null>(null);

  useEffect(() => {
    api.memorySnapshot().then(setSnapshot).catch(console.error);
  }, []);

  if (!snapshot) return <InlineLoading description="Loading memory…" />;

  const { profile, preferences: prefs, episodes } = snapshot;

  const headers = [
    { key: "key", header: "Key" },
    { key: "value", header: "Value" },
  ];

  return (
    <>
      <PageHeader
        title="Live memory"
        description="Committed facts injected at inference time. Proposed drafts are not shown here."
        breadcrumbs={[{ label: "membrane", href: "/" }, { label: "Live memory" }]}
      />

      <Tabs>
        <TabList aria-label="Memory tabs" contained>
          <Tab>Profile ({profile.length})</Tab>
          <Tab>Preferences ({prefs.length})</Tab>
          <Tab>Episodes ({episodes.length})</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <DataTable rows={profile.map((r) => ({ ...r, id: r.id || r.key }))} headers={headers}>
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
          </TabPanel>
          <TabPanel>
            <DataTable rows={prefs.map((r) => ({ ...r, id: r.id || r.key }))} headers={headers}>
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
          </TabPanel>
          <TabPanel>
            {episodes.length === 0 ? (
              <div className="empty-state">
                <h3>No episodes yet</h3>
                <p>Approve episodic proposals to build timeline memory.</p>
              </div>
            ) : (
              episodes.map((ep) => (
                <article key={ep.id} className="episode-item">
                  <small>{ep.tags?.join(" · ") || "general"}</small>
                  <p>{ep.summary}</p>
                </article>
              ))
            )}
          </TabPanel>
        </TabPanels>
      </Tabs>
    </>
  );
}
