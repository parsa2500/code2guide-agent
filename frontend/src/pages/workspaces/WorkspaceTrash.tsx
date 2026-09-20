import { useCallback, useEffect, useState } from "react";
import BackButton, { HubLink } from "../../components/BackButton";
import { formatFaDate } from "../../utils/format";
import type { WorkspaceOut } from "../../api/workspaces";
import { listDeletedWorkspaces, restoreWorkspace } from "../../api/workspaces";

export default function WorkspaceTrash() {
  const [items, setItems] = useState<WorkspaceOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDeletedWorkspaces();
      setItems(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleRestore(id: string) {
    setError(null);
    try {
      await restoreWorkspace(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="app shell-page">
      <header className="strip">
        <div className="brand">
          <div className="brand-mark">Code2Guide</div>
          <div className="brand-sub">workspaceهای حذف‌شده</div>
        </div>
        <div className="leds">
          <BackButton to="/workspaces" />
          <HubLink />
        </div>
      </header>

      <main className="shell-main">
        <div className="panel-head">
          <span>Trash</span>
          <span>{loading ? "…" : `${items.length} soft-deleted`}</span>
        </div>

        {error ? (
          <p className="empty-hint" data-tone="error" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="empty-hint">در حال بارگذاری…</p>
        ) : items.length === 0 ? (
          <p className="empty-hint">حذف‌شده‌ای نیست.</p>
        ) : (
          <div className="trash-list">
            {items.map((ws) => (
              <div key={ws.id} className="trash-row">
                <div>
                  <strong>{ws.name}</strong>
                  <p className="ws-card-path" dir="ltr">
                    {ws.path}
                  </p>
                  <p className="ws-card-meta">حذف: {formatFaDate(ws.deleted_at)}</p>
                </div>
                <button
                  type="button"
                  className="btn btn-teal"
                  onClick={() => void handleRestore(ws.id)}
                >
                  بازیابی
                </button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
