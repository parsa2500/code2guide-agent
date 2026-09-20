import { useState } from "react";
import type { Workspace } from "../../../mock/workspaceStore";
import { formatFaDate, runMockUpdate } from "../../../mock/workspaceStore";

type Props = {
  workspace: Workspace;
  onChange: (ws: Workspace) => void;
};

export default function UpdateTab({ workspace, onChange }: Props) {
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(
    workspace.updateLogs[0]?.id ?? null,
  );

  function handleUpdate() {
    setBusy(true);
    window.setTimeout(() => {
      const next = runMockUpdate(workspace.id);
      if (next) {
        onChange(next);
        setExpanded(next.updateLogs[0]?.id ?? null);
      }
      setBusy(false);
    }, 600);
  }

  return (
    <div className="tab-stack">
      <div className="toolbar">
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleUpdate}
          disabled={busy}
        >
          {busy ? "در حال آپدیت…" : "آپدیت workspace"}
        </button>
        <span className="status-line">آپدیت mock — بدون اتصال به بک</span>
      </div>

      <div className="panel-head">
        <span>Update logs</span>
        <span>{workspace.updateLogs.length}</span>
      </div>

      {workspace.updateLogs.length === 0 ? (
        <p className="empty-hint">هنوز آپدیتی ثبت نشده.</p>
      ) : (
        <ul className="log-list">
          {workspace.updateLogs.map((log) => {
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
                  <strong>{log.summary}</strong>
                  <span className="ws-card-meta">{formatFaDate(log.startedAt)}</span>
                </button>
                {open ? (
                  <pre className="log-detail" dir="ltr">
                    {log.detail}
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
