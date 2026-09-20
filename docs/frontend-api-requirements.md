# Frontend API requirements (planned)

This document lists the backend APIs the new Code2Guide shell will need once mock UI is wired. Nothing below is implemented yet except the existing ask/index endpoints used by `/ask`.

Base path assumption: `/api/v1`

---

## Already used (Ask console)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ask` | Technical Persian guide |
| `POST` | `/ask-enduser` | End-user Persian guide |
| `POST` | `/index-workspace` | Deep index FE + BE |
| `GET` | `/index/status` | Index health / counts |

Request bodies already match `frontend/src/api/client.ts`.

---

## Workspaces CRUD + soft delete

### `GET /workspaces`
List active workspaces (`deleted_at IS NULL`).

**Query (optional):** `q`, `status`, `limit`, `offset`

**Response `200`:**
```json
{
  "items": [
    {
      "id": "ws_…",
      "name": "پنل مناقصات",
      "path": "sample_workspace",
      "description": "…",
      "status": "ready",
      "updated_at": "2026-09-20T08:00:00Z",
      "deleted_at": null
    }
  ],
  "total": 1
}
```

### `GET /workspaces/deleted`
List soft-deleted workspaces.

Same item shape; `deleted_at` required.

### `GET /workspaces/{id}`
Workspace detail including settings summary.

### `POST /workspaces`
Create workspace.

**Body:**
```json
{
  "name": "…",
  "path": "…",
  "description": "…"
}
```

**Response `201`:** created workspace object.

### `PATCH /workspaces/{id}`
Update name / path / description.

### `DELETE /workspaces/{id}`
Soft delete → set `deleted_at`.

**Response `200`:** updated workspace (or `204`).

### `POST /workspaces/{id}/restore`
Clear `deleted_at` and return workspace to active list.

---

## Workspace update jobs + logs

### `POST /workspaces/{id}/update`
Start reindex / refresh job for one workspace.

**Body (optional):**
```json
{ "rebuild": true, "scope": "full" }
```

**Response `202`:**
```json
{
  "job_id": "upd_…",
  "status": "running",
  "started_at": "…"
}
```

### `GET /workspaces/{id}/updates`
List update jobs (newest first).

**Item:**
```json
{
  "id": "upd_…",
  "started_at": "…",
  "finished_at": "…",
  "status": "success",
  "summary": "ایندکس کامل شد",
  "detail": "Routes: …"
}
```

### `GET /workspaces/{id}/updates/{job_id}`
Single update job detail (full log body).

---

## Workspace settings

### `GET /workspaces/{id}/settings`
```json
{
  "default_agent": "guide-agent",
  "enabled_chatbots": ["bot_user", "bot_tech"],
  "audience_default": "end_user",
  "auto_index": true,
  "mcp_enabled": false
}
```

### `PUT /workspaces/{id}/settings`
Replace settings object (same shape).

---

## Workspace activity logs

### `GET /workspaces/{id}/logs`
Full activity stream for the workspace.

**Query:** `level` (`info|warn|error`), `q`, `from`, `to`, `limit`, `offset`

**Item:**
```json
{
  "id": "log_…",
  "at": "…",
  "level": "info",
  "source": "indexer",
  "message": "…"
}
```

---

## Chat (workspace tab)

### `GET /workspaces/{id}/chatbots`
List chatbots configured for the workspace.

### `GET /workspaces/{id}/chatbots/{bot_id}/messages`
Paginated messages.

### `POST /workspaces/{id}/chatbots/{bot_id}/messages`
Send user message; return assistant reply (or job id if async).

**Body:**
```json
{ "text": "چطور مناقصه ثبت کنم؟" }
```

**Response `200`:**
```json
{
  "user_message": { "id": "…", "role": "user", "text": "…", "at": "…" },
  "assistant_message": { "id": "…", "role": "assistant", "text": "…", "at": "…" }
}
```

---

## Future hub surfaces (stubs today)

Not required for the current mock shell, but expected later:

| Area | Suggested endpoints |
|------|---------------------|
| Agents | `GET/POST/PATCH /agents`, bind agent → workspace |
| API & MCP | `GET /mcp/servers`, `POST /mcp/servers`, health |
| Pipeline | `GET /pipelines`, `GET /pipelines/{id}/runs` |
| Product guide | static docs or `GET /docs/product` |

---

## Frontend mapping (mock → future)

| UI | Mock store today | Future API |
|----|------------------|------------|
| Workspace cards | `listActiveWorkspaces` | `GET /workspaces` |
| Soft delete | `softDeleteWorkspace` | `DELETE /workspaces/{id}` |
| Trash / restore | `listDeleted` / `restore` | `GET …/deleted`, `POST …/restore` |
| Edit modal | `updateWorkspace` | `PATCH /workspaces/{id}` |
| Update tab | `runMockUpdate` | `POST …/update` + `GET …/updates` |
| Settings tab | `saveWorkspaceSettings` | `PUT …/settings` |
| Logs tab | `activityLogs` | `GET …/logs` |
| Chat tab | `appendChatMessage` | chatbots + messages APIs |

Persistence note: mock UI uses `localStorage` key `c2g.workspaces.v1` until these endpoints exist.
