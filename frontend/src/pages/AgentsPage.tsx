import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import BackButton, { HubLink } from "../components/BackButton";
import AgentFormModal from "../components/AgentFormModal";
import type { AgentInput, AgentKind, AgentOut } from "../api/agents";
import {
  createAgent,
  getAgent,
  listAgents,
  patchAgent,
  publishAgent,
} from "../api/agents";

const KIND_LABEL: Record<AgentKind, string> = {
  jarvis: "جارویس",
  end_user: "کاربر نهایی",
  technical: "فنی",
  custom: "سفارشی",
};

export default function AgentsPage() {
  const [items, setItems] = useState<AgentOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [mode, setMode] = useState<"create" | "edit">("create");
  const [editing, setEditing] = useState<AgentOut | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAgents();
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

  async function openEdit(agent: AgentOut) {
    setMode("edit");
    setEditing(agent);
    setModalOpen(true);
    try {
      const fresh = await getAgent(agent.id);
      setEditing((current) => (current?.id === agent.id ? fresh : current));
    } catch {
      /* list payload is enough if GET is not ready yet */
    }
  }

  async function handleSubmit(input: AgentInput) {
    setSaving(true);
    setError(null);
    try {
      if (mode === "create") {
        await createAgent(input);
      } else if (editing) {
        await patchAgent(editing.id, {
          name: input.name,
          kind: input.kind,
          policy: input.policy,
          reject_text: input.reject_text,
          clarify_first: input.clarify_first,
          settings_schema: input.settings_schema,
        });
        if (input.published !== editing.published) {
          await publishAgent(editing.id, input.published);
        }
      }
      setModalOpen(false);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function togglePublished(agent: AgentOut) {
    setPendingId(agent.id);
    setError(null);
    try {
      const requested = !agent.published;
      const next = await publishAgent(agent.id, requested);
      setItems((prev) => prev.map((item) => (item.id === agent.id ? next : item)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPendingId(null);
    }
  }

  return (
    <div className="app shell-page">
      <header className="strip">
        <div className="brand">
          <div className="brand-mark">Code2Guide</div>
          <div className="brand-sub">ایجنت‌ها</div>
        </div>
        <div className="leds">
          <BackButton to="/" />
          <HubLink />
          <Link to="/brain-settings" className="btn btn-nav">
            تنظیمات مغز
          </Link>
        </div>
      </header>

      <main className="shell-main">
        <div className="panel-head">
          <span>Agents</span>
          <span>{loading ? "…" : `${items.length} registered`}</span>
        </div>

        <div className="toolbar">
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            ایجنت جدید
          </button>
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
        ) : items.length === 0 && !error ? (
          <p className="empty-hint">ایجنتی ثبت نشده. یکی بسازید یا صبر کنید تا بذر بک‌اند بیاید.</p>
        ) : (
          <div className="ws-grid">
            {items.map((agent) => (
              <article key={agent.id} className="ws-card">
                <button type="button" className="ws-card-main" onClick={() => void openEdit(agent)}>
                  <div className="ws-card-top">
                    <span className="ws-card-code">{KIND_LABEL[agent.kind]}</span>
                    <span
                      className={`ws-status ${agent.published ? "status-ok" : "status-idle"}`}
                    >
                      {agent.published ? "منتشرشده" : "منتشرنشده"}
                    </span>
                  </div>
                  <h3 className="ws-card-title">{agent.name}</h3>
                  <p className="ws-card-path" dir="ltr">
                    {agent.id}
                  </p>
                  <p className="ws-card-desc">
                    {agent.clarify_first ? "اول شفاف‌سازی" : "بدون شفاف‌سازی اجباری"}
                    {agent.policy
                      ? ` — ${agent.policy.slice(0, 80)}${agent.policy.length > 80 ? "…" : ""}`
                      : ""}
                  </p>
                </button>
                <div className="ws-card-actions">
                  <button type="button" className="btn btn-teal" onClick={() => void openEdit(agent)}>
                    ویرایش
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => void togglePublished(agent)}
                    disabled={pendingId === agent.id}
                  >
                    {pendingId === agent.id
                      ? "…"
                      : agent.published
                        ? "برداشتن انتشار"
                        : "انتشار"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>

      <AgentFormModal
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
