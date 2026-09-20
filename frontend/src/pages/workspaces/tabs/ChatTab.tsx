import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { Chatbot, ChatMessage } from "../../../api/workspaces";
import { listChatbots, listMessages, sendMessage } from "../../../api/workspaces";

type Props = {
  workspaceId: string;
};

export default function ChatTab({ workspaceId }: Props) {
  const [bots, setBots] = useState<Chatbot[]>([]);
  const [activeBotId, setActiveBotId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bot = bots.find((b) => b.id === activeBotId) ?? bots[0];

  const loadBots = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listChatbots(workspaceId);
      setBots(data.items);
      setActiveBotId((prev) => prev || data.items[0]?.id || "");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  const loadMessages = useCallback(
    async (botId: string) => {
      if (!botId) {
        setMessages([]);
        return;
      }
      setError(null);
      try {
        const data = await listMessages(workspaceId, botId, { limit: 200 });
        setMessages(data.items);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [workspaceId],
  );

  useEffect(() => {
    void loadBots();
  }, [loadBots]);

  useEffect(() => {
    if (bot?.id) void loadMessages(bot.id);
  }, [bot?.id, loadMessages]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !bot || sending) return;
    setSending(true);
    setError(null);
    try {
      const result = await sendMessage(workspaceId, bot.id, text);
      setMessages((prev) => [...prev, result.user_message, result.assistant_message]);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return <p className="empty-hint">در حال بارگذاری چت‌بات‌ها…</p>;
  }

  if (!bot) {
    return <p className="empty-hint">چت‌باتی تعریف نشده.</p>;
  }

  return (
    <div className="chat-layout">
      <aside className="chat-bots" aria-label="چت‌بات‌ها">
        {bots.map((b) => (
          <button
            key={b.id}
            type="button"
            className="chat-bot-item"
            aria-pressed={b.id === bot.id}
            onClick={() => setActiveBotId(b.id)}
          >
            <span className="dest-code">{b.role === "technical" ? "TEC" : "USR"}</span>
            <span>{b.name}</span>
          </button>
        ))}
      </aside>
      <div className="chat-panel">
        <div className="panel-head">
          <span>{bot.name}</span>
          <span>{sending ? "در حال پاسخ…" : "آماده"}</span>
        </div>
        {error ? (
          <p className="empty-hint" data-tone="error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="chat-messages">
          {messages.length === 0 ? (
            <p className="empty-hint">هنوز پیامی نیست. چیزی بپرسید.</p>
          ) : (
            messages.map((m) => (
              <div key={m.id} className={`chat-bubble chat-${m.role}`}>
                {m.text}
              </div>
            ))
          )}
        </div>
        <form className="chat-compose" onSubmit={(e) => void send(e)}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="پیام خود را بنویسید…"
            aria-label="پیام"
            disabled={sending}
          />
          <button type="submit" className="btn btn-primary" disabled={sending || !draft.trim()}>
            {sending ? "…" : "ارسال"}
          </button>
        </form>
      </div>
    </div>
  );
}
