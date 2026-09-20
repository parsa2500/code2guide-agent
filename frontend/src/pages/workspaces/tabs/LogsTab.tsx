import { useCallback, useEffect, useState } from "react";
import type { ActivityLog, LogLevel } from "../../../api/workspaces";
import { listLogs } from "../../../api/workspaces";
import { formatFaDate } from "../../../utils/format";

type Props = {
  workspaceId: string;
};

type LevelFilter = "all" | LogLevel;

export default function LogsTab({ workspaceId }: Props) {
  const [level, setLevel] = useState<LevelFilter>("all");
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [rows, setRows] = useState<ActivityLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setQDebounced(q.trim()), 300);
    return () => window.clearTimeout(t);
  }, [q]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listLogs(workspaceId, {
        level: level === "all" ? undefined : level,
        q: qDebounced || undefined,
        limit: 200,
      });
      setRows(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [workspaceId, level, qDebounced]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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
        <span>{loading ? "…" : total}</span>
      </div>

      {error ? (
        <p className="empty-hint" data-tone="error" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="empty-hint">در حال بارگذاری…</p>
      ) : rows.length === 0 ? (
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
