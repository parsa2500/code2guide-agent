import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type {
  Chatbot,
  WorkspaceDetailOut,
  WorkspaceSettings,
} from "../../../api/workspaces";
import { listChatbots, putSettings } from "../../../api/workspaces";

type Props = {
  workspace: WorkspaceDetailOut;
  onWorkspaceChange: (ws: WorkspaceDetailOut) => void;
};

export default function SettingsTab({ workspace, onWorkspaceChange }: Props) {
  const [settings, setSettings] = useState<WorkspaceSettings>(workspace.settings);
  const [bots, setBots] = useState<Chatbot[]>([]);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSettings(workspace.settings);
  }, [workspace]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await listChatbots(workspace.id);
        if (!cancelled) setBots(data.items);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspace.id]);

  function toggleBot(id: string) {
    setSettings((s) => {
      const has = s.enabled_chatbots.includes(id);
      return {
        ...s,
        enabled_chatbots: has
          ? s.enabled_chatbots.filter((x) => x !== id)
          : [...s.enabled_chatbots, id],
      };
    });
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const next = await putSettings(workspace.id, settings);
      onWorkspaceChange({ ...workspace, settings: next });
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="tab-stack form-grid" onSubmit={(e) => void onSave(e)}>
      {error ? (
        <p className="empty-hint" data-tone="error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="flap">
        <label className="flap-label" htmlFor="default-agent">
          ایجنت پیش‌فرض
        </label>
        <select
          id="default-agent"
          value={settings.default_agent}
          onChange={(e) => setSettings({ ...settings, default_agent: e.target.value })}
          disabled={saving}
        >
          <option value="guide-agent">guide-agent</option>
          <option value="flow-agent">flow-agent</option>
          <option value="index-agent">index-agent</option>
        </select>
      </div>

      <div className="flap">
        <label className="flap-label" htmlFor="audience-default">
          مخاطب پیش‌فرض
        </label>
        <select
          id="audience-default"
          value={settings.audience_default}
          onChange={(e) =>
            setSettings({
              ...settings,
              audience_default: e.target.value as WorkspaceSettings["audience_default"],
            })
          }
          disabled={saving}
        >
          <option value="end_user">کاربر نهایی</option>
          <option value="technical">فنی</option>
        </select>
      </div>

      <div className="flap">
        <span className="flap-label">چت‌بات‌ها</span>
        <div className="check-list">
          {(bots.length > 0
            ? bots
            : settings.enabled_chatbots.map(
                (id): Chatbot => ({ id, name: id, role: "end_user" }),
              )
          ).map((b) => (
            <label key={b.id} className="check-row">
              <input
                type="checkbox"
                checked={settings.enabled_chatbots.includes(b.id)}
                onChange={() => toggleBot(b.id)}
                disabled={saving}
              />
              {b.name}
            </label>
          ))}
        </div>
      </div>

      <div className="flap">
        <label className="check-row">
          <input
            type="checkbox"
            checked={settings.auto_index}
            onChange={(e) => setSettings({ ...settings, auto_index: e.target.checked })}
            disabled={saving}
          />
          ایندکس خودکار پس از آپدیت
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={settings.mcp_enabled}
            onChange={(e) => setSettings({ ...settings, mcp_enabled: e.target.checked })}
            disabled={saving}
          />
          فعال‌سازی MCP
        </label>
      </div>

      <div className="toolbar">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "در حال ذخیره…" : "ذخیره تنظیمات"}
        </button>
        {saved ? (
          <span className="status-line" data-tone="ok">
            ذخیره شد
          </span>
        ) : null}
      </div>
    </form>
  );
}
