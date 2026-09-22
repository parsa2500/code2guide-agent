import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type {
  AgentChatOut,
  AgentKind,
  AgentOut,
  WorkspaceAgentBinding,
} from "../../../api/agents";
import {
  attachWorkspaceAgent,
  chatWorkspaceAgent,
  listAgents,
  listWorkspaceAgents,
} from "../../../api/agents";

type Props = {
  workspaceId: string;
};

type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  clarify?: boolean;
  rejected?: boolean;
};

const KIND_LABEL: Record<AgentKind, string> = {
  jarvis: "جارویس",
  end_user: "کاربر نهایی",
  technical: "فنی",
  custom: "سفارشی",
};

function kindCode(kind: AgentKind | undefined): string {
  switch (kind) {
    case "jarvis":
      return "JAR";
    case "technical":
      return "TEC";
    case "end_user":
      return "USR";
    default:
      return "AGT";
  }
}

function bindingLabel(binding: WorkspaceAgentBinding): string {
  return binding.definition?.name || binding.agent_id;
}

function bindingKind(binding: WorkspaceAgentBinding): AgentKind {
  return binding.definition?.kind || "custom";
}

export default function AgentsTab({ workspaceId }: Props) {
  const [bindings, setBindings] = useState<WorkspaceAgentBinding[]>([]);
  const [catalog, setCatalog] = useState<AgentOut[]>([]);
  const [activeAgentId, setActiveAgentId] = useState("");
  const [pickerId, setPickerId] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [attaching, setAttaching] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = bindings.find((b) => b.agent_id === activeAgentId) ?? bindings[0];

  const availableToAttach = useMemo(() => {
    const bound = new Set(bindings.map((b) => b.agent_id));
    return catalog.filter((a) => a.published && !bound.has(a.id));
  }, [bindings, catalog]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [bound, agents] = await Promise.all([
        listWorkspaceAgents(workspaceId),
        listAgents(),
      ]);
      setBindings(bound);
      setCatalog(agents.items);
      setActiveAgentId((prev) => {
        if (prev && bound.some((b) => b.agent_id === prev)) return prev;
        return bound[0]?.agent_id || "";
      });
      setPickerId((prev) => {
        const open = agents.items.filter(
          (a) => a.published && !bound.some((b) => b.agent_id === a.id),
        );
        if (prev && open.some((a) => a.id === prev)) return prev;
        return open[0]?.id || "";
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    setTurns([]);
    setDraft("");
  }, [active?.agent_id]);

  async function attach() {
    if (!pickerId || attaching) return;
    setAttaching(true);
    setError(null);
    try {
      const attached = await attachWorkspaceAgent(workspaceId, pickerId);
      const fromCatalog = catalog.find((a) => a.id === attached.agent_id) || null;
      const next: WorkspaceAgentBinding = attached.definition
        ? attached
        : { ...attached, definition: fromCatalog };
      setBindings((prev) => {
        if (prev.some((b) => b.agent_id === next.agent_id)) {
          return prev.map((b) => (b.agent_id === next.agent_id ? next : b));
        }
        return [...prev, next];
      });
      setActiveAgentId(next.agent_id);
      const remaining = availableToAttach.filter((a) => a.id !== pickerId);
      setPickerId(remaining[0]?.id || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAttaching(false);
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !active || sending) return;
    setSending(true);
    setError(null);
    const userTurn: ChatTurn = {
      id: `u-${Date.now()}`,
      role: "user",
      text,
    };
    setTurns((prev) => [...prev, userTurn]);
    setDraft("");
    try {
      const result: AgentChatOut = await chatWorkspaceAgent(
        workspaceId,
        active.agent_id,
        text,
      );
      setTurns((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: result.answer || "",
          clarify: Boolean(result.clarify),
          rejected: Boolean(result.rejected),
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return <p className="empty-hint">در حال بارگذاری ایجنت‌ها…</p>;
  }

  return (
    <div className="tab-stack">
      <div className="toolbar" style={{ flexWrap: "wrap" }}>
        <label className="flap-label" htmlFor="attach-agent" style={{ margin: 0 }}>
          افزودن ایجنت منتشرشده
        </label>
        <select
          id="attach-agent"
          value={pickerId}
          onChange={(e) => setPickerId(e.target.value)}
          disabled={attaching || availableToAttach.length === 0}
          style={{ minWidth: "12rem" }}
        >
          {availableToAttach.length === 0 ? (
            <option value="">ایجنت منتشرشدهٔ آزاد نیست</option>
          ) : (
            availableToAttach.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({KIND_LABEL[a.kind]})
              </option>
            ))
          )}
        </select>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void attach()}
          disabled={attaching || !pickerId || availableToAttach.length === 0}
        >
          {attaching ? "در حال اتصال…" : "اتصال"}
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

      {!active ? (
        <p className="empty-hint">
          هنوز ایجنتی به این workspace وصل نیست. یک ایجنت منتشرشده اضافه کنید.
        </p>
      ) : (
        <div className="chat-layout">
          <aside className="chat-bots" aria-label="ایجنت‌های متصل">
            {bindings.map((b) => (
              <button
                key={b.agent_id}
                type="button"
                className="chat-bot-item"
                aria-pressed={b.agent_id === active.agent_id}
                onClick={() => setActiveAgentId(b.agent_id)}
              >
                <span className="dest-code">{kindCode(bindingKind(b))}</span>
                <span>{bindingLabel(b)}</span>
                <span className="status-line">
                  {b.enabled ? "فعال" : "غیرفعال"}
                  {b.definition?.published === false ? " · منتشرنشده" : ""}
                </span>
              </button>
            ))}
          </aside>
          <div className="chat-panel">
            <div className="panel-head">
              <span>{bindingLabel(active)}</span>
              <span>{sending ? "در حال پاسخ…" : "آماده"}</span>
            </div>
            <div className="chat-messages">
              {turns.length === 0 ? (
                <p className="empty-hint">هنوز پیامی نیست. از ایجنت بپرسید.</p>
              ) : (
                turns.map((m) => (
                  <div key={m.id} className={`chat-bubble chat-${m.role}`}>
                    <div>{m.text}</div>
                    {m.role === "assistant" && (m.clarify || m.rejected) ? (
                      <div className="meta" style={{ padding: "0.55rem 0 0" }}>
                        {m.clarify ? <span className="chip chip-amber">clarify</span> : null}
                        {m.rejected ? <span className="chip">rejected</span> : null}
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
            <form className="chat-compose" onSubmit={(e) => void send(e)}>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="پیام برای ایجنت…"
                aria-label="پیام ایجنت"
                disabled={sending || !active.enabled}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={sending || !draft.trim() || !active.enabled}
              >
                {sending ? "…" : "ارسال"}
              </button>
            </form>
            {!active.enabled ? (
              <p className="empty-hint" style={{ padding: "0 1rem 0.75rem" }}>
                این ایجنت غیرفعال است. از تب تنظیمات ایجنت فعالش کنید.
              </p>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
