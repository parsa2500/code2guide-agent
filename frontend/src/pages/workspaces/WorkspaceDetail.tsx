import { useEffect, useMemo, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import BackButton, { HubLink } from "../../components/BackButton";
import type { Workspace } from "../../mock/workspaceStore";
import { getWorkspace } from "../../mock/workspaceStore";
import ChatTab from "./tabs/ChatTab";
import UpdateTab from "./tabs/UpdateTab";
import SettingsTab from "./tabs/SettingsTab";
import LogsTab from "./tabs/LogsTab";

const TABS = [
  { id: "chat", label: "چت" },
  { id: "update", label: "Update" },
  { id: "settings", label: "تنظیمات" },
  { id: "logs", label: "لاگ‌ها" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function isTabId(v: string | null): v is TabId {
  return TABS.some((t) => t.id === v);
}

export default function WorkspaceDetail() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [workspace, setWorkspace] = useState<Workspace | undefined>(() => getWorkspace(id));

  useEffect(() => {
    setWorkspace(getWorkspace(id));
  }, [id]);

  const tab: TabId = isTabId(params.get("tab")) ? (params.get("tab") as TabId) : "chat";

  const title = useMemo(() => workspace?.name ?? "Workspace", [workspace]);

  if (!workspace || workspace.deletedAt) {
    return <Navigate to="/workspaces" replace />;
  }

  function setTab(next: TabId) {
    setParams({ tab: next });
  }

  return (
    <div className="app shell-page">
      <header className="strip">
        <div className="brand">
          <div className="brand-mark">Code2Guide</div>
          <div className="brand-sub">{title}</div>
        </div>
        <div className="leds">
          <BackButton to="/workspaces" />
          <HubLink />
        </div>
      </header>

      <main className="shell-main detail-main">
        <div className="panel-head">
          <span>Workspace</span>
          <span dir="ltr">{workspace.path}</span>
        </div>

        <div className="tabs" role="tablist" aria-label="بخش‌های workspace">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              className="tab-btn"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="tab-panel" role="tabpanel">
          {tab === "chat" ? (
            <ChatTab workspace={workspace} onChange={setWorkspace} />
          ) : null}
          {tab === "update" ? (
            <UpdateTab workspace={workspace} onChange={setWorkspace} />
          ) : null}
          {tab === "settings" ? (
            <SettingsTab workspace={workspace} onChange={setWorkspace} />
          ) : null}
          {tab === "logs" ? <LogsTab workspace={workspace} /> : null}
        </div>
      </main>
    </div>
  );
}
