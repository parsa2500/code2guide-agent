import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import BackButton, { HubLink } from "../../components/BackButton";
import type { WorkspaceDetailOut } from "../../api/workspaces";
import { getWorkspace } from "../../api/workspaces";
import ChatTab from "./tabs/ChatTab";
import AgentsTab from "./tabs/AgentsTab";
import AgentSettingsTab from "./tabs/AgentSettingsTab";
import UpdateTab from "./tabs/UpdateTab";
import SettingsTab from "./tabs/SettingsTab";
import LogsTab from "./tabs/LogsTab";

const TABS = [
  { id: "chat", label: "چت" },
  { id: "agents", label: "ایجنت‌ها" },
  { id: "agent-settings", label: "تنظیمات ایجنت" },
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
  const [workspace, setWorkspace] = useState<WorkspaceDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getWorkspace(id);
      if (data.deleted_at) {
        setNotFound(true);
        setWorkspace(null);
      } else {
        setWorkspace(data);
        setNotFound(false);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        setNotFound(true);
      } else {
        setError(msg);
      }
      setWorkspace(null);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const tab: TabId = isTabId(params.get("tab")) ? (params.get("tab") as TabId) : "chat";

  const title = useMemo(() => workspace?.name ?? "Workspace", [workspace]);

  function setTab(next: TabId) {
    setParams({ tab: next });
  }

  if (notFound && !loading) {
    return <Navigate to="/workspaces" replace />;
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
          <span dir="ltr">{workspace?.path ?? (loading ? "…" : "—")}</span>
        </div>

        {error ? (
          <p className="empty-hint" data-tone="error" role="alert">
            {error}
          </p>
        ) : null}

        {loading && !workspace ? (
          <p className="empty-hint">در حال بارگذاری…</p>
        ) : workspace ? (
          <>
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
              {tab === "chat" ? <ChatTab workspaceId={workspace.id} /> : null}
              {tab === "agents" ? <AgentsTab workspaceId={workspace.id} /> : null}
              {tab === "agent-settings" ? (
                <AgentSettingsTab workspaceId={workspace.id} />
              ) : null}
              {tab === "update" ? (
                <UpdateTab workspace={workspace} onWorkspaceChange={setWorkspace} />
              ) : null}
              {tab === "settings" ? (
                <SettingsTab workspace={workspace} onWorkspaceChange={setWorkspace} />
              ) : null}
              {tab === "logs" ? <LogsTab workspaceId={workspace.id} /> : null}
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}
