import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { Workspace, WorkspaceSettings } from "../../../mock/workspaceStore";
import { saveWorkspaceSettings } from "../../../mock/workspaceStore";

type Props = {
  workspace: Workspace;
  onChange: (ws: Workspace) => void;
};

export default function SettingsTab({ workspace, onChange }: Props) {
  const [settings, setSettings] = useState<WorkspaceSettings>(workspace.settings);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSettings(workspace.settings);
  }, [workspace]);

  function toggleBot(id: string) {
    setSettings((s) => {
      const has = s.enabledChatbots.includes(id);
      return {
        ...s,
        enabledChatbots: has
          ? s.enabledChatbots.filter((x) => x !== id)
          : [...s.enabledChatbots, id],
      };
    });
  }

  function onSave(e: FormEvent) {
    e.preventDefault();
    const next = saveWorkspaceSettings(workspace.id, settings);
    if (next) {
      onChange(next);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    }
  }

  return (
    <form className="tab-stack form-grid" onSubmit={onSave}>
      <div className="flap">
        <label className="flap-label" htmlFor="default-agent">
          ایجنت پیش‌فرض
        </label>
        <select
          id="default-agent"
          value={settings.defaultAgent}
          onChange={(e) => setSettings({ ...settings, defaultAgent: e.target.value })}
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
          value={settings.audienceDefault}
          onChange={(e) =>
            setSettings({
              ...settings,
              audienceDefault: e.target.value as WorkspaceSettings["audienceDefault"],
            })
          }
        >
          <option value="end_user">کاربر نهایی</option>
          <option value="technical">فنی</option>
        </select>
      </div>

      <div className="flap">
        <span className="flap-label">چت‌بات‌ها</span>
        <div className="check-list">
          {workspace.chatbots.map((b) => (
            <label key={b.id} className="check-row">
              <input
                type="checkbox"
                checked={settings.enabledChatbots.includes(b.id)}
                onChange={() => toggleBot(b.id)}
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
            checked={settings.autoIndex}
            onChange={(e) => setSettings({ ...settings, autoIndex: e.target.checked })}
          />
          ایندکس خودکار پس از آپدیت
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={settings.mcpEnabled}
            onChange={(e) => setSettings({ ...settings, mcpEnabled: e.target.checked })}
          />
          فعال‌سازی MCP
        </label>
      </div>

      <div className="toolbar">
        <button type="submit" className="btn btn-primary">
          ذخیره تنظیمات
        </button>
        {saved ? (
          <span className="status-line" data-tone="ok">
            ذخیره شد (mock)
          </span>
        ) : null}
      </div>
    </form>
  );
}
