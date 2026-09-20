import { useCallback, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import BackButton, { HubLink } from "../../components/BackButton";
import WorkspaceCard from "../../components/WorkspaceCard";
import WorkspaceFormModal from "../../components/WorkspaceFormModal";
import type { Workspace, WorkspaceInput } from "../../mock/workspaceStore";
import {
  createWorkspace,
  listActiveWorkspaces,
  softDeleteWorkspace,
  updateWorkspace,
} from "../../mock/workspaceStore";

export default function WorkspaceList() {
  const navigate = useNavigate();
  const [items, setItems] = useState(() => listActiveWorkspaces());
  const [modalOpen, setModalOpen] = useState(false);
  const [mode, setMode] = useState<"create" | "edit">("create");
  const [editing, setEditing] = useState<Workspace | null>(null);

  const refresh = useCallback(() => {
    setItems(listActiveWorkspaces());
  }, []);

  function openCreate() {
    setMode("create");
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(ws: Workspace) {
    setMode("edit");
    setEditing(ws);
    setModalOpen(true);
  }

  function handleSubmit(input: WorkspaceInput) {
    if (mode === "create") {
      createWorkspace(input);
    } else if (editing) {
      updateWorkspace(editing.id, input);
    }
    setModalOpen(false);
    refresh();
  }

  function handleDelete(ws: Workspace) {
    const ok = window.confirm(`«${ws.name}» به لیست حذف‌شده‌ها منتقل شود؟`);
    if (!ok) return;
    softDeleteWorkspace(ws.id);
    refresh();
  }

  return (
    <div className="app shell-page">
      <header className="strip">
        <div className="brand">
          <div className="brand-mark">Code2Guide</div>
          <div className="brand-sub">انتخاب workspace</div>
        </div>
        <div className="leds">
          <BackButton to="/" />
          <HubLink />
        </div>
      </header>

      <main className="shell-main">
        <div className="panel-head">
          <span>Workspaces</span>
          <span>{items.length} active</span>
        </div>

        <div className="toolbar">
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            ساخت workspace جدید
          </button>
          <Link to="/workspaces/trash" className="btn btn-teal">
            حذف‌شده‌ها
          </Link>
        </div>

        {items.length === 0 ? (
          <p className="empty-hint">workspace فعالی نیست. یکی بسازید یا از حذف‌شده‌ها بازیابی کنید.</p>
        ) : (
          <div className="ws-grid">
            {items.map((ws) => (
              <WorkspaceCard
                key={ws.id}
                workspace={ws}
                onOpen={() => navigate(`/workspaces/${ws.id}`)}
                onEdit={() => openEdit(ws)}
                onDelete={() => handleDelete(ws)}
              />
            ))}
          </div>
        )}
      </main>

      <WorkspaceFormModal
        open={modalOpen}
        mode={mode}
        initial={editing}
        onClose={() => setModalOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  );
}
