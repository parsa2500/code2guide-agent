import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { GuideMessage, GuideSession, GuideStep } from "../../../api/guideChat";
import {
  createGuideSession,
  deleteGuideSession,
  listGuideMessages,
  listGuideSessions,
  streamGuideMessage,
} from "../../../api/guideChat";

type Props = {
  workspaceId: string;
};

type LiveTurn = {
  userText: string;
  steps: GuideStep[];
  clarify?: string;
};

export default function ChatTab({ workspaceId }: Props) {
  const [sessions, setSessions] = useState<GuideSession[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<GuideMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [live, setLive] = useState<LiveTurn | null>(null);
  const [error, setError] = useState<string | null>(null);

  const session = sessions.find((s) => s.id === activeId) ?? sessions[0];

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listGuideSessions(workspaceId);
      setSessions(data.items);
      setActiveId((prev) => {
        if (prev && data.items.some((s) => s.id === prev)) return prev;
        return data.items[0]?.id || "";
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const loadMessages = useCallback(
    async (sessionId: string) => {
      if (!sessionId) {
        setMessages([]);
        return;
      }
      setError(null);
      try {
        const data = await listGuideMessages(workspaceId, sessionId, { limit: 200 });
        setMessages(data.items);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [workspaceId],
  );

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (session?.id) void loadMessages(session.id);
    else setMessages([]);
  }, [session?.id, loadMessages]);

  async function onNewSession() {
    setError(null);
    try {
      const created = await createGuideSession(workspaceId);
      setSessions((prev) => [created, ...prev]);
      setActiveId(created.id);
      setMessages([]);
      setLive(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onDeleteSession(id: string) {
    setError(null);
    try {
      await deleteGuideSession(workspaceId, id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeId === id) {
        setActiveId("");
        setMessages([]);
        setLive(null);
      }
      await loadSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !session || sending) return;
    setSending(true);
    setError(null);
    setDraft("");
    setLive({ userText: text, steps: [] });

    const optimisticUser: GuideMessage = {
      id: `tmp-user-${Date.now()}`,
      role: "user",
      text,
      at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);

    try {
      await streamGuideMessage(workspaceId, session.id, text, {
        onStep: (step) => {
          setLive((prev) =>
            prev ? { ...prev, steps: [...prev.steps, step] } : { userText: text, steps: [step] },
          );
        },
        onClarify: (clarifyText) => {
          setLive((prev) => (prev ? { ...prev, clarify: clarifyText } : prev));
        },
        onFinal: (message) => {
          setMessages((prev) => {
            const withoutTmp = prev.filter((m) => m.id !== optimisticUser.id);
            return [...withoutTmp, { id: `u-${message.id}`, role: "user", text, at: message.at }, message];
          });
          setLive(null);
        },
        onError: (msg) => {
          setError(msg);
          setLive(null);
          setMessages((prev) => prev.filter((m) => m.id !== optimisticUser.id));
        },
        onDone: () => {
          void loadMessages(session.id);
          void loadSessions();
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setLive(null);
      setMessages((prev) => prev.filter((m) => m.id !== optimisticUser.id));
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return <p className="empty-hint">در حال بارگذاری چت راهنما…</p>;
  }

  return (
    <div className="chat-layout">
      <aside className="chat-bots" aria-label="Sessionها">
        <div className="guide-session-toolbar">
          <button type="button" className="btn btn-primary" onClick={() => void onNewSession()}>
            Session جدید
          </button>
        </div>
        {sessions.length === 0 ? (
          <p className="empty-hint">هنوز sessionای نیست.</p>
        ) : (
          sessions.map((s) => (
            <div key={s.id} className="guide-session-row">
              <button
                type="button"
                className="chat-bot-item"
                aria-pressed={s.id === session?.id}
                onClick={() => setActiveId(s.id)}
              >
                <span className="dest-code">CHT</span>
                <span>{s.title}</span>
              </button>
              <button
                type="button"
                className="guide-session-del"
                title="حذف"
                aria-label="حذف session"
                onClick={() => void onDeleteSession(s.id)}
              >
                ×
              </button>
            </div>
          ))
        )}
      </aside>
      <div className="chat-panel">
        <div className="panel-head">
          <span>{session?.title ?? "چت راهنما"}</span>
          <span>{sending ? "در حال فکر کردن…" : "آماده"}</span>
        </div>
        {error ? (
          <p className="empty-hint" data-tone="error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="chat-messages">
          {!session ? (
            <p className="empty-hint">یک Session جدید بسازید تا شروع کنید.</p>
          ) : messages.length === 0 && !live ? (
            <p className="empty-hint">هنوز پیامی نیست. چیزی بپرسید.</p>
          ) : (
            <>
              {messages.map((m) => (
                <div key={m.id} className={`chat-bubble chat-${m.role}`}>
                  <div className="guide-bubble-text">{m.text}</div>
                  {m.role === "assistant" && m.steps && m.steps.length > 0 ? (
                    <details className="guide-steps">
                      <summary>مراحل فکر ({m.steps.length})</summary>
                      <ol className="guide-step-list">
                        {m.steps.map((st) => (
                          <li key={st.id}>
                            <span className="chip">{st.phase}</span> {st.title}
                            {st.detail ? <pre className="log-detail">{st.detail}</pre> : null}
                          </li>
                        ))}
                      </ol>
                    </details>
                  ) : null}
                </div>
              ))}
              {live ? (
                <div className="chat-bubble chat-assistant guide-live">
                  <div className="guide-bubble-text">
                    {live.clarify
                      ? live.clarify
                      : sending
                        ? "در حال پردازش…"
                        : "…"}
                  </div>
                  {live.steps.length > 0 ? (
                    <div className="guide-steps guide-steps-live">
                      <div className="guide-steps-label">مراحل زنده</div>
                      <ol className="guide-step-list">
                        {live.steps.map((st) => (
                          <li key={st.id}>
                            <span className="chip">{st.phase}</span> {st.title}
                            {st.detail ? <pre className="log-detail">{st.detail}</pre> : null}
                          </li>
                        ))}
                      </ol>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </>
          )}
        </div>
        <form className="chat-compose" onSubmit={(e) => void send(e)}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={session ? "پیام خود را بنویسید…" : "ابتدا Session بسازید"}
            aria-label="پیام"
            disabled={sending || !session}
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={sending || !session || !draft.trim()}
          >
            {sending ? "…" : "ارسال"}
          </button>
        </form>
      </div>
    </div>
  );
}
