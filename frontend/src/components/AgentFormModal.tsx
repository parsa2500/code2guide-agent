import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Modal from "./Modal";
import type { AgentInput, AgentKind, AgentOut } from "../api/agents";
import { formatSettingsSchema, parseSettingsSchema } from "../api/agents";

const KIND_OPTIONS: { value: AgentKind; label: string }[] = [
  { value: "jarvis", label: "جارویس" },
  { value: "end_user", label: "کاربر نهایی" },
  { value: "technical", label: "فنی" },
  { value: "custom", label: "سفارشی" },
];

type Props = {
  open: boolean;
  mode: "create" | "edit";
  initial?: AgentOut | null;
  busy?: boolean;
  onClose: () => void;
  onSubmit: (input: AgentInput) => void;
};

export default function AgentFormModal({
  open,
  mode,
  initial,
  busy = false,
  onClose,
  onSubmit,
}: Props) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState<AgentKind>("custom");
  const [policy, setPolicy] = useState("");
  const [rejectText, setRejectText] = useState("");
  const [clarifyFirst, setClarifyFirst] = useState(false);
  const [published, setPublished] = useState(false);
  const [schemaText, setSchemaText] = useState("{\n}\n");
  const [schemaError, setSchemaError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setId("");
    setName(initial?.name ?? "");
    setKind(initial?.kind ?? "custom");
    setPolicy(initial?.policy ?? "");
    setRejectText(initial?.reject_text ?? "");
    setClarifyFirst(initial?.clarify_first ?? false);
    setPublished(initial?.published ?? false);
    setSchemaText(formatSettingsSchema(initial?.settings_schema));
    setSchemaError(null);
  }, [open, initial]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    let settings_schema;
    try {
      settings_schema = parseSettingsSchema(schemaText);
    } catch (err) {
      setSchemaError(err instanceof Error ? err.message : String(err));
      return;
    }
    setSchemaError(null);
    const next: AgentInput = {
      name: name.trim(),
      kind,
      policy,
      reject_text: rejectText,
      clarify_first: clarifyFirst,
      published,
      settings_schema,
    };
    if (mode === "create" && id.trim()) next.id = id.trim();
    onSubmit(next);
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === "create" ? "ایجنت جدید" : "ویرایش ایجنت"}
      wide
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            انصراف
          </button>
          <button type="submit" form="agent-form" className="btn btn-primary" disabled={busy}>
            {busy ? "…" : mode === "create" ? "ایجاد" : "ذخیره"}
          </button>
        </>
      }
    >
      <form id="agent-form" className="form-grid" onSubmit={handleSubmit}>
        {mode === "create" ? (
          <div className="flap">
            <label className="flap-label" htmlFor="agent-id">
              شناسه
            </label>
            <input
              id="agent-id"
              value={id}
              onChange={(e) => setId(e.target.value)}
              dir="ltr"
              spellCheck={false}
              disabled={busy}
              placeholder="اختیاری — خالی یعنی سرور بسازد"
            />
          </div>
        ) : null}
        <div className="flap">
          <label className="flap-label" htmlFor="agent-name">
            نام
          </label>
          <input
            id="agent-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            disabled={busy}
            placeholder="مثلاً جارویس"
          />
        </div>
        <div className="flap">
          <label className="flap-label" htmlFor="agent-kind">
            نوع
          </label>
          <select
            id="agent-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as AgentKind)}
            disabled={busy}
          >
            {KIND_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flap">
          <label className="flap-label" htmlFor="agent-policy">
            سیاست / policy
          </label>
          <textarea
            id="agent-policy"
            value={policy}
            onChange={(e) => setPolicy(e.target.value)}
            rows={5}
            disabled={busy}
            placeholder="دستور سیستم و سیاست پاسخ‌گویی"
          />
        </div>
        <div className="flap">
          <label className="flap-label" htmlFor="agent-reject">
            متن رد
          </label>
          <textarea
            id="agent-reject"
            value={rejectText}
            onChange={(e) => setRejectText(e.target.value)}
            rows={3}
            disabled={busy}
            placeholder="متنی که هنگام رد درخواست نشان داده می‌شود"
          />
        </div>
        <div className="flap">
          <label className="check-row">
            <input
              type="checkbox"
              checked={clarifyFirst}
              onChange={(e) => setClarifyFirst(e.target.checked)}
              disabled={busy}
            />
            اول شفاف‌سازی کن
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={published}
              onChange={(e) => setPublished(e.target.checked)}
              disabled={busy}
            />
            منتشر شده (پرچم داخلی)
          </label>
        </div>
        <div className="flap">
          <label className="flap-label" htmlFor="agent-schema">
            اسکیمای تنظیمات
          </label>
          <textarea
            id="agent-schema"
            value={schemaText}
            onChange={(e) => {
              setSchemaText(e.target.value);
              setSchemaError(null);
            }}
            rows={8}
            dir="ltr"
            spellCheck={false}
            disabled={busy}
          />
          <p className="field-hint">
            JSON: هر کلید یک شیء با <span dir="ltr">default</span> و{" "}
            <span dir="ltr">workspace_overridable</span>.
          </p>
          {schemaError ? (
            <p className="field-hint" data-tone="error" role="alert">
              {schemaError}
            </p>
          ) : null}
        </div>
      </form>
    </Modal>
  );
}
