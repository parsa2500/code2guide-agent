import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type {
  AgentKind,
  AgentOut,
  SettingsSchema,
  WorkspaceAgentBinding,
} from "../../../api/agents";
import {
  detachWorkspaceAgent,
  getAgent,
  listWorkspaceAgents,
  patchWorkspaceAgent,
} from "../../../api/agents";

type Props = {
  workspaceId: string;
};

const KIND_LABEL: Record<AgentKind, string> = {
  jarvis: "جارویس",
  end_user: "کاربر نهایی",
  technical: "فنی",
  custom: "سفارشی",
};

function bindingLabel(binding: WorkspaceAgentBinding, def?: AgentOut | null): string {
  return def?.name || binding.definition?.name || binding.agent_id;
}

function valueToInput(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function parseOverrideInput(raw: string, prototype: unknown): unknown {
  const trimmed = raw.trim();
  if (typeof prototype === "boolean") {
    if (trimmed === "true") return true;
    if (trimmed === "false") return false;
    throw new Error("مقدار بولی باید true یا false باشد.");
  }
  if (typeof prototype === "number") {
    if (trimmed === "") throw new Error("عدد خالی مجاز نیست.");
    const n = Number(trimmed);
    if (!Number.isFinite(n)) throw new Error("عدد نامعتبر است.");
    return n;
  }
  if (prototype !== null && typeof prototype === "object") {
    if (!trimmed) return prototype;
    try {
      return JSON.parse(trimmed) as unknown;
    } catch {
      throw new Error("JSON نامعتبر است.");
    }
  }
  return raw;
}

function overridableKeys(schema: SettingsSchema | undefined): string[] {
  if (!schema) return [];
  return Object.keys(schema)
    .filter((key) => schema[key]?.workspace_overridable === true)
    .sort();
}

export default function AgentSettingsTab({ workspaceId }: Props) {
  const [bindings, setBindings] = useState<WorkspaceAgentBinding[]>([]);
  const [definitions, setDefinitions] = useState<Record<string, AgentOut>>({});
  const [activeAgentId, setActiveAgentId] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [draftOverrides, setDraftOverrides] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [detaching, setDetaching] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = bindings.find((b) => b.agent_id === activeAgentId) ?? bindings[0];
  const definition =
    (active && (definitions[active.agent_id] || active.definition)) || null;
  const schema = definition?.settings_schema || {};
  const editableKeys = useMemo(() => overridableKeys(schema), [schema]);

  const hydrateDraft = useCallback((binding: WorkspaceAgentBinding, def: AgentOut | null) => {
    const keys = overridableKeys(def?.settings_schema);
    const next: Record<string, string> = {};
    for (const key of keys) {
      const current =
        binding.overrides[key] !== undefined
          ? binding.overrides[key]
          : binding.effective_settings[key] !== undefined
            ? binding.effective_settings[key]
            : def?.settings_schema[key]?.default;
      next[key] = valueToInput(current);
    }
    setDraftOverrides(next);
    setEnabled(binding.enabled);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const bound = await listWorkspaceAgents(workspaceId);
      setBindings(bound);

      const defs: Record<string, AgentOut> = {};
      await Promise.all(
        bound.map(async (b) => {
          if (b.definition) {
            defs[b.agent_id] = b.definition;
            return;
          }
          try {
            defs[b.agent_id] = await getAgent(b.agent_id);
          } catch {
            /* empty settings panel is OK when definition/schema is missing */
          }
        }),
      );
      setDefinitions(defs);

      const nextId =
        activeAgentId && bound.some((b) => b.agent_id === activeAgentId)
          ? activeAgentId
          : bound[0]?.agent_id || "";
      setActiveAgentId(nextId);
      const selected = bound.find((b) => b.agent_id === nextId);
      if (selected) {
        hydrateDraft(selected, defs[selected.agent_id] || selected.definition || null);
      } else {
        setDraftOverrides({});
        setEnabled(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [workspaceId, activeAgentId, hydrateDraft]);

  useEffect(() => {
    void refresh();
    // initial + workspace change only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  function selectBinding(agentId: string) {
    setActiveAgentId(agentId);
    const binding = bindings.find((b) => b.agent_id === agentId);
    if (binding) {
      hydrateDraft(binding, definitions[agentId] || binding.definition || null);
    }
    setSaved(false);
    setError(null);
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!active || saving) return;
    setSaving(true);
    setError(null);
    try {
      const patch: { enabled: boolean; overrides?: Record<string, unknown> } = {
        enabled,
      };
      if (editableKeys.length > 0) {
        const overrides: Record<string, unknown> = {};
        for (const key of editableKeys) {
          const prototype =
            active.overrides[key] !== undefined
              ? active.overrides[key]
              : active.effective_settings[key] !== undefined
                ? active.effective_settings[key]
                : schema[key]?.default;
          overrides[key] = parseOverrideInput(draftOverrides[key] ?? "", prototype);
        }
        patch.overrides = overrides;
      }
      const next = await patchWorkspaceAgent(workspaceId, active.agent_id, patch);
      setBindings((prev) =>
        prev.map((b) => (b.agent_id === next.agent_id ? next : b)),
      );
      if (next.definition) {
        setDefinitions((prev) => ({ ...prev, [next.agent_id]: next.definition as AgentOut }));
      }
      hydrateDraft(next, next.definition || definitions[next.agent_id] || null);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function onDetach() {
    if (!active || detaching) return;
    const label = bindingLabel(active, definition);
    const ok = window.confirm(`اتصال «${label}» از این workspace جدا شود؟`);
    if (!ok) return;
    setDetaching(true);
    setError(null);
    try {
      await detachWorkspaceAgent(workspaceId, active.agent_id);
      const remaining = bindings.filter((b) => b.agent_id !== active.agent_id);
      setBindings(remaining);
      setDefinitions((prev) => {
        const copy = { ...prev };
        delete copy[active.agent_id];
        return copy;
      });
      const next = remaining[0];
      setActiveAgentId(next?.agent_id || "");
      if (next) {
        hydrateDraft(next, definitions[next.agent_id] || next.definition || null);
      } else {
        setDraftOverrides({});
        setEnabled(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDetaching(false);
    }
  }

  if (loading) {
    return <p className="empty-hint">در حال بارگذاری تنظیمات ایجنت…</p>;
  }

  if (!active) {
    return (
      <p className="empty-hint">
        ایجنت متصلی نیست. از تب ایجنت‌ها یک ایجنت منتشرشده اضافه کنید.
      </p>
    );
  }

  return (
    <div className="tab-stack">
      <div className="toolbar" style={{ flexWrap: "wrap" }}>
        <label className="flap-label" htmlFor="settings-agent" style={{ margin: 0 }}>
          ایجنت
        </label>
        <select
          id="settings-agent"
          value={active.agent_id}
          onChange={(e) => selectBinding(e.target.value)}
          disabled={saving || detaching}
          style={{ minWidth: "12rem" }}
        >
          {bindings.map((b) => {
            const def = definitions[b.agent_id] || b.definition;
            const kind = def?.kind || "custom";
            return (
              <option key={b.agent_id} value={b.agent_id}>
                {bindingLabel(b, def)} ({KIND_LABEL[kind]})
              </option>
            );
          })}
        </select>
        <button
          type="button"
          className="btn"
          onClick={() => void refresh()}
          disabled={saving || detaching}
        >
          تازه‌سازی
        </button>
      </div>

      {error ? (
        <p className="empty-hint" data-tone="error" role="alert">
          {error}
        </p>
      ) : null}

      <form className="tab-stack form-grid" onSubmit={(e) => void onSave(e)}>
        <div className="panel-head">
          <span>{bindingLabel(active, definition)}</span>
          <span dir="ltr">{active.agent_id}</span>
        </div>

        <div className="flap">
          <label className="check-row">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              disabled={saving || detaching}
            />
            فعال در این workspace
          </label>
          <p className="field-hint">
            فقط کلیدهایی با{" "}
            <span dir="ltr">workspace_overridable=true</span> قابل ویرایش‌اند.
          </p>
        </div>

        {editableKeys.length === 0 ? (
          <p className="empty-hint">
            کلید قابل‌رونویسی برای این ایجنت تعریف نشده (پنل خالی مجاز است).
          </p>
        ) : (
          editableKeys.map((key) => {
            const field = schema[key];
            const prototype =
              active.overrides[key] !== undefined
                ? active.overrides[key]
                : active.effective_settings[key] !== undefined
                  ? active.effective_settings[key]
                  : field?.default;
            const isBool = typeof prototype === "boolean";
            const isObject = prototype !== null && typeof prototype === "object";
            return (
              <div className="flap" key={key}>
                <label className="flap-label" htmlFor={`ovr-${key}`}>
                  <span dir="ltr">{key}</span>
                </label>
                {isBool ? (
                  <select
                    id={`ovr-${key}`}
                    value={draftOverrides[key] ?? "false"}
                    onChange={(e) =>
                      setDraftOverrides((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                    disabled={saving || detaching}
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : isObject ? (
                  <textarea
                    id={`ovr-${key}`}
                    value={draftOverrides[key] ?? ""}
                    onChange={(e) =>
                      setDraftOverrides((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                    dir="ltr"
                    spellCheck={false}
                    rows={4}
                    disabled={saving || detaching}
                  />
                ) : (
                  <input
                    id={`ovr-${key}`}
                    value={draftOverrides[key] ?? ""}
                    onChange={(e) =>
                      setDraftOverrides((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                    dir="ltr"
                    spellCheck={false}
                    disabled={saving || detaching}
                  />
                )}
                <p className="field-hint">
                  پیش‌فرض:{" "}
                  <span dir="ltr">{valueToInput(field?.default)}</span>
                </p>
              </div>
            );
          })
        )}

        <div className="toolbar">
          <button type="submit" className="btn btn-primary" disabled={saving || detaching}>
            {saving ? "در حال ذخیره…" : "ذخیره تنظیمات ایجنت"}
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => void onDetach()}
            disabled={saving || detaching}
          >
            {detaching ? "در حال جداسازی…" : "جدا کردن از workspace"}
          </button>
          {saved ? (
            <span className="status-line" data-tone="ok">
              ذخیره شد
            </span>
          ) : null}
        </div>
      </form>
    </div>
  );
}
