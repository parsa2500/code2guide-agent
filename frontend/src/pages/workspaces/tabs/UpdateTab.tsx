import { useCallback, useEffect, useState } from "react";
import type { UpdateJob, WorkspaceDetailOut } from "../../../api/workspaces";
import {
  getWorkspace,
  listUpdates,
  pollUpdateJob,
  startUpdate,
} from "../../../api/workspaces";
import { formatFaDate } from "../../../utils/format";

type Props = {
  workspace: WorkspaceDetailOut;
  onWorkspaceChange: (ws: WorkspaceDetailOut) => void;
};

export default function UpdateTab({ workspace, onWorkspaceChange }: Props) {
  const [jobs, setJobs] = useState<UpdateJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const refreshJobs = useCallback(async () => {
    setError(null);
    try {
      const data = await listUpdates(workspace.id);
      setJobs(data.items);
      if (!expanded && data.items[0]) setExpanded(data.items[0].id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [workspace.id, expanded]);

  useEffect(() => {
    void refreshJobs();
  }, [workspace.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleUpdate() {
    setBusy(true);
    setError(null);
    try {
      const accepted = await startUpdate(workspace.id, { rebuild: true, scope: "full" });
      setExpanded(accepted.job_id);
      onWorkspaceChange({ ...workspace, status: "indexing" });

      const finished = await pollUpdateJob(workspace.id, accepted.job_id);
      await refreshJobs();

      const detail = await getWorkspace(workspace.id);
      onWorkspaceChange(detail);

      if (finished.status === "failed") {
        setError(finished.summary || finished.detail || "آپدیت ناموفق بود");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      try {
        const detail = await getWorkspace(workspace.id);
        onWorkspaceChange(detail);
      } catch {
        /* ignore */
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="tab-stack">
      <div className="toolbar">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void handleUpdate()}
          disabled={busy || workspace.status === "indexing"}
        >
          {busy || workspace.status === "indexing" ? "در حال آپدیت…" : "آپدیت workspace"}
        </button>
        <span className="status-line">وضعیت: {workspace.status}</span>
      </div>

      {error ? (
        <p className="empty-hint" data-tone="error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="panel-head">
        <span>Update logs</span>
        <span>{loading ? "…" : jobs.length}</span>
      </div>

      {loading ? (
        <p className="empty-hint">در حال بارگذاری…</p>
      ) : jobs.length === 0 ? (
        <p className="empty-hint">هنوز آپدیتی ثبت نشده.</p>
      ) : (
        <ul className="log-list">
          {jobs.map((log) => {
            const open = expanded === log.id;
            return (
              <li key={log.id} className="log-item">
                <button
                  type="button"
                  className="log-summary"
                  aria-expanded={open}
                  onClick={() => setExpanded(open ? null : log.id)}
                >
                  <span className={`ws-status status-${log.status}`}>{log.status}</span>
                  <strong>{log.summary || "—"}</strong>
                  <span className="ws-card-meta">{formatFaDate(log.started_at)}</span>
                </button>
                {open ? (
                  <pre className="log-detail" dir="ltr">
                    {log.detail || "(بدون جزئیات)"}
                  </pre>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
