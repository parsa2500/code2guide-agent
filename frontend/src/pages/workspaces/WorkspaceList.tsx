import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import BackButton, { HubLink } from "../../components/BackButton";
import WorkspaceCard from "../../components/WorkspaceCard";
import WorkspaceFormModal from "../../components/WorkspaceFormModal";
import type { WorkspaceInput, WorkspaceOut } from "../../api/workspaces";
import {
  createWorkspace,
  deleteWorkspace,
  listWorkspaces,
  updateWorkspace,
} from "../../api/workspaces";

export default function WorkspaceList() {
  const navigate = useNavigate();
  const [items, setItems] = useState<WorkspaceOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [mode, setMode] = useState<"create" | "edit">("create");
  const [editing, setEditing] = useState<WorkspaceOut | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkspaces();
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

  function openCreate() {
    setMode("create");
    setEditing(null);
    setModalOpen(true);
  }

  function openEdit(ws: WorkspaceOut) {
    setMode("edit");
    setEditing(ws);
    setModalOpen(true);
  }

  async function handleSubmit(input: WorkspaceInput) {
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        await createWorkspace(input);
      } else if (editing) {
        await updateWorkspace(editing.id, input);
      }
      setModalOpen(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(ws: WorkspaceOut) {
    const ok = window.confirm(`«${ws.name}» به لیست حذف‌شده‌ها منتقل شود؟`);
    if (!ok) return;
    setError(null);
    try {
      await deleteWorkspace(ws.id);
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
          <span>{loading ? "…" : `${items.length} active`}</span>
        </div>

        <div className="toolbar">
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            ساخت workspace جدید
          </button>
          <Link to="/workspaces/trash" className="btn btn-teal">
            حذف‌شده‌ها
          </Link>
          <button type="button" className="btn" onClick={() => void refresh()} disabled={loading}>
            تازه‌سازی
          </button>
        </div>

        {error ? (
          <p className="empty-hint" data-tone="error" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="empty-hint">در حال بارگذاری…</p>
        ) : items.length === 0 ? (
          <p className="empty-hint">workspace فعالی نیست. یکی بسازید یا از حذف‌شده‌ها بازیابی کنید.</p>
        ) : (
          <div className="ws-grid">
            {items.map((ws) => (
              <WorkspaceCard
                key={ws.id}
                workspace={ws}
                onOpen={() => navigate(`/workspaces/${ws.id}`)}
                onEdit={() => openEdit(ws)}
                onDelete={() => void handleDelete(ws)}
              />
            ))}
          </div>
        )}
      </main>

      <WorkspaceFormModal
        open={modalOpen}
        mode={mode}
        initial={editing}
        busy={saving}
        onClose={() => setModalOpen(false)}
        onSubmit={(input) => void handleSubmit(input)}
      />
    </div>
  );
}
