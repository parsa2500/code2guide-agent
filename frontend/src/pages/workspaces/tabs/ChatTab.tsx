import { useState } from "react";
import type { FormEvent } from "react";
import type { Workspace } from "../../../mock/workspaceStore";
import { appendChatMessage } from "../../../mock/workspaceStore";

type Props = {
  workspace: Workspace;
  onChange: (ws: Workspace) => void;
};

export default function ChatTab({ workspace, onChange }: Props) {
  const bots = workspace.chatbots;
  const [activeBotId, setActiveBotId] = useState(bots[0]?.id ?? "");
  const [draft, setDraft] = useState("");
  const bot = bots.find((b) => b.id === activeBotId) ?? bots[0];

  function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || !bot) return;
    const next = appendChatMessage(workspace.id, bot.id, text);
    if (next) onChange(next);
    setDraft("");
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
          <span>Mock chat</span>
        </div>
        <div className="chat-messages">
          {bot.messages.length === 0 ? (
            <p className="empty-hint">هنوز پیامی نیست. چیزی بپرسید.</p>
          ) : (
            bot.messages.map((m) => (
              <div key={m.id} className={`chat-bubble chat-${m.role}`}>
                {m.text}
              </div>
            ))
          )}
        </div>
        <form className="chat-compose" onSubmit={send}>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="پیام خود را بنویسید…"
            aria-label="پیام"
          />
          <button type="submit" className="btn btn-primary">
            ارسال
          </button>
        </form>
      </div>
    </div>
  );
}
