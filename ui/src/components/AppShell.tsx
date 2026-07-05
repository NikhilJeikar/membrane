import { useEffect, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import {
  Content,
  Header,
  HeaderGlobalBar,
  HeaderMenuButton,
  HeaderName,
  SideNav,
  SideNavItems,
  SideNavLink,
  SkipToContent,
  Tag,
} from "@carbon/react";
import {
  Dashboard,
  DataBase,
  Policy,
  Renew,
  Rule,
  ServerProxy,
} from "@carbon/icons-react";
import { api, Status } from "../api";
import DashboardPage from "../pages/Dashboard";
import ReviewPage from "../pages/Review";
import MemoryPage from "../pages/Memory";
import IngestPage from "../pages/Ingest";
import PoliciesPage from "../pages/Policies";
import ServerPage from "../pages/Server";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: Dashboard, end: true },
  { to: "/review", label: "Memory review", icon: Rule },
  { to: "/memory", label: "Live memory", icon: DataBase },
  { to: "/ingest", label: "Ingest", icon: Renew },
  { to: "/server", label: "Server", icon: ServerProxy },
  { to: "/policies", label: "Policies", icon: Policy },
] as const;

export default function AppShell() {
  const location = useLocation();
  const [status, setStatus] = useState<Status | null>(null);
  const [sideNavExpanded, setSideNavExpanded] = useState(true);

  useEffect(() => {
    api.status().then(setStatus).catch(console.error);
    const t = setInterval(() => api.status().then(setStatus).catch(console.error), 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className={`app-shell${sideNavExpanded ? " app-shell--nav-expanded" : ""}`}>
      <Header aria-label="membrane">
        <SkipToContent href="#main-content" />
        <HeaderMenuButton
          aria-label={sideNavExpanded ? "Close navigation" : "Open navigation"}
          isActive={sideNavExpanded}
          onClick={() => setSideNavExpanded((open) => !open)}
        />
        <HeaderName as={Link} to="/" prefix="">
          membrane
        </HeaderName>
        <HeaderGlobalBar>
          {status && (
            <div className="header-meta">
              <Tag type={status.ollama_ok ? "green" : "red"} size="md">
                Ollama {status.ollama_ok ? "online" : "offline"}
              </Tag>
              <Tag type={status.pending_proposals > 0 ? "red" : "gray"} size="md">
                {status.pending_proposals} pending
              </Tag>
              <Tag type="blue" size="md">
                {status.phase}
              </Tag>
            </div>
          )}
        </HeaderGlobalBar>
      </Header>

      <SideNav
        aria-label="Side navigation"
        expanded={sideNavExpanded}
        isFixedNav
        isChildOfHeader
        className="app-sidenav"
      >
        <SideNavItems>
          {NAV_ITEMS.map((item) => (
            <SideNavLink
              key={item.to}
              as={Link}
              to={item.to}
              isActive={"end" in item && item.end ? location.pathname === item.to : location.pathname === item.to}
              renderIcon={item.icon}
            >
              {item.label}
            </SideNavLink>
          ))}
        </SideNavItems>
      </SideNav>

      <Content id="main-content" className="page-content">
        <Routes>
          <Route path="/" element={<DashboardPage status={status} />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/ingest" element={<IngestPage />} />
          <Route path="/server" element={<ServerPage />} />
          <Route path="/policies" element={<PoliciesPage />} />
        </Routes>
      </Content>
    </div>
  );
}
