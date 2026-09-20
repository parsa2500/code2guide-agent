import { useMemo, useState } from "react";
import type { Workspace } from "../../../mock/workspaceStore";
import { formatFaDate } from "../../../mock/workspaceStore";

type Props = {
  workspace: Workspace;
};

type LevelFilter = "all" | "info" | "warn" | "error";

export default function LogsTab({ workspace }: Props) {
  const [level, setLevel] = useState<LevelFilter>("all");
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    return workspace.activityLogs.filter((log) => {
      if (level !== "all" && log.level !== level) return false;
      if (q.trim() && !`${log.message} ${log.source}`.includes(q.trim())) return false;
      return true;
    });
  }, [workspace.activityLogs, level, q]);

  return (
    <div className="tab-stack">
      <div className="toolbar filters">
        <div className="flap compact">
          <label className="flap-label" htmlFor="log-level">
            سطح
          </label>
          <select
            id="log-level"
            value={level}
            onChange={(e) => setLevel(e.target.value as LevelFilter)}
          >
            <option value="all">همه</option>
            <option value="info">info</option>
            <option value="warn">warn</option>
            <option value="error">error</option>
          </select>
        </div>
        <div className="flap compact grow">
          <label className="flap-label" htmlFor="log-q">
            جستجو
          </label>
          <input
            id="log-q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="متن لاگ…"
          />
        </div>
      </div>

      <div className="panel-head">
        <span>Activity logs</span>
        <span>{rows.length}</span>
      </div>

      {rows.length === 0 ? (
        <p className="empty-hint">لاگی مطابق فیلتر نیست.</p>
      ) : (
        <div className="table-wrap">
          <table className="log-table">
            <thead>
              <tr>
                <th>زمان</th>
                <th>سطح</th>
                <th>منبع</th>
                <th>پیام</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((log) => (
                <tr key={log.id}>
                  <td>{formatFaDate(log.at)}</td>
                  <td>
                    <span className={`ws-status status-${log.level}`}>{log.level}</span>
                  </td>
                  <td dir="ltr">{log.source}</td>
                  <td>{log.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
