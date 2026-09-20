import type { Workspace } from "../mock/workspaceStore";
import { formatFaDate } from "../mock/workspaceStore";

type Props = {
  workspace: Workspace;
  onOpen: () => void;
  onEdit: () => void;
  onDelete: () => void;
};

export default function WorkspaceCard({ workspace, onOpen, onEdit, onDelete }: Props) {
  return (
    <article className="ws-card">
      <button type="button" className="ws-card-main" onClick={onOpen}>
        <div className="ws-card-top">
          <span className="ws-card-code">WS</span>
          <span className={`ws-status status-${workspace.status}`}>{workspace.status}</span>
        </div>
        <h3 className="ws-card-title">{workspace.name}</h3>
        <p className="ws-card-path" dir="ltr">
          {workspace.path}
        </p>
        <p className="ws-card-desc">{workspace.description || "بدون توضیح"}</p>
        <p className="ws-card-meta">به‌روزرسانی: {formatFaDate(workspace.updatedAt)}</p>
      </button>
      <div className="ws-card-actions">
        <button
          type="button"
          className="btn btn-teal"
          onClick={(e) => {
            e.stopPropagation();
            onEdit();
          }}
        >
          ویرایش
        </button>
        <button
          type="button"
          className="btn btn-danger"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          حذف
        </button>
      </div>
    </article>
  );
}
