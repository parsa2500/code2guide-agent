import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Modal from "./Modal";
import type { WorkspaceInput, WorkspaceOut } from "../api/workspaces";

type Props = {
  open: boolean;
  mode: "create" | "edit";
  initial?: WorkspaceOut | null;
  busy?: boolean;
  onClose: () => void;
  onSubmit: (input: WorkspaceInput) => void;
};

export default function WorkspaceFormModal({
  open,
  mode,
  initial,
  busy = false,
  onClose,
  onSubmit,
}: Props) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setPath(initial?.path ?? "");
    setDescription(initial?.description ?? "");
  }, [open, initial]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !path.trim() || busy) return;
    onSubmit({ name: name.trim(), path: path.trim(), description: description.trim() });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === "create" ? "ساخت workspace جدید" : "ویرایش workspace"}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            انصراف
          </button>
          <button type="submit" form="ws-form" className="btn btn-primary" disabled={busy}>
            {busy ? "…" : mode === "create" ? "ایجاد" : "ذخیره"}
          </button>
        </>
      }
    >
      <form id="ws-form" className="form-grid" onSubmit={handleSubmit}>
        <div className="flap">
          <label className="flap-label" htmlFor="ws-name">
            نام
          </label>
          <input
            id="ws-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="مثلاً پنل مناقصات"
            disabled={busy}
          />
        </div>
        <div className="flap">
          <label className="flap-label" htmlFor="ws-path">
            مسیر
          </label>
          <input
            id="ws-path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            required
            dir="ltr"
            placeholder="C:/path/to/project یا sample_workspace"
            spellCheck={false}
            disabled={busy}
          />
        </div>
        <div className="flap">
          <label className="flap-label" htmlFor="ws-desc">
            توضیح
          </label>
          <textarea
            id="ws-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="توضیح کوتاه درباره این workspace"
            disabled={busy}
          />
        </div>
      </form>
    </Modal>
  );
}
