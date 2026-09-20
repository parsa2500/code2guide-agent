import { useCallback, useState } from "react";
import BackButton, { HubLink } from "../../components/BackButton";
import {
  formatFaDate,
  listDeletedWorkspaces,
  restoreWorkspace,
} from "../../mock/workspaceStore";

export default function WorkspaceTrash() {
  const [items, setItems] = useState(() => listDeletedWorkspaces());

  const refresh = useCallback(() => {
    setItems(listDeletedWorkspaces());
  }, []);

  function handleRestore(id: string) {
    restoreWorkspace(id);
    refresh();
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
          <span>{items.length} soft-deleted</span>
        </div>

        {items.length === 0 ? (
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
                  <p className="ws-card-meta">حذف: {formatFaDate(ws.deletedAt)}</p>
                </div>
                <button
                  type="button"
                  className="btn btn-teal"
                  onClick={() => handleRestore(ws.id)}
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
