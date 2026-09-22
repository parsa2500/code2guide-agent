/**
 * Global agent registry + workspace agent bindings.
 *
 * Locked contract (all under `/api/v1`):
 * - `GET/POST /api/v1/agents`
 * - `GET/PATCH /api/v1/agents/{id}`
 * - `POST /api/v1/agents/{id}/publish` body `{ published }`
 * - `GET/POST /api/v1/workspaces/{ws_id}/agents`
 * - `PATCH/DELETE /api/v1/workspaces/{ws_id}/agents/{id}`
 * - `POST /api/v1/workspaces/{ws_id}/agents/{id}/chat` body `{ message }`
 *
 * Agent body: `id?`, `name`, `kind`, `policy`, `reject_text`, `clarify_first`,
 * `settings_schema`, `published`.
 * Seed ids `jarvis`, `bot_user`, `bot_tech` are owned by the backend.
 */

import { apiFetch } from "./client";

export type AgentKind = "jarvis" | "end_user" | "technical" | "custom";

export interface AgentSettingField {
  default: unknown;
  workspace_overridable: boolean;
}

export type SettingsSchema = Record<string, AgentSettingField>;

export interface AgentOut {
  id: string;
  name: string;
  kind: AgentKind;
  policy: string;
  reject_text: string;
  clarify_first: boolean;
  published: boolean;
  settings_schema: SettingsSchema;
}

export interface AgentInput {
  id?: string;
  name: string;
  kind: AgentKind;
  policy: string;
  reject_text: string;
  clarify_first: boolean;
  settings_schema: SettingsSchema;
  published: boolean;
}

export interface AgentListOut {
  items: AgentOut[];
  total: number;
  limit: number;
  offset: number;
}

/** Row from `GET /api/v1/workspaces/{ws_id}/agents`. */
export interface WorkspaceAgentBinding {
  id: string;
  agent_id: string;
  enabled: boolean;
  overrides: Record<string, unknown>;
}

export interface WorkspaceAgentPatch {
  enabled?: boolean;
  overrides?: Record<string, unknown>;
}

const KINDS: readonly AgentKind[] = ["jarvis", "end_user", "technical", "custom"];

function isKind(value: unknown): value is AgentKind {
  return typeof value === "string" && (KINDS as readonly string[]).includes(value);
}

export function parseSettingsSchema(text: string): SettingsSchema {
  const trimmed = text.trim();
  if (!trimmed) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error("JSON اسکیما نامعتبر است.");
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("اسکیما باید یک شیء باشد: کلید → {default, workspace_overridable}.");
  }
  const out: SettingsSchema = {};
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (!key.trim()) throw new Error("کلید خالی در اسکیما مجاز نیست.");
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`«${key}» باید شیء {default, workspace_overridable} باشد.`);
    }
    const field = value as Record<string, unknown>;
    if (!("default" in field)) throw new Error(`«${key}» فیلد default ندارد.`);
    if (typeof field.workspace_overridable !== "boolean") {
      throw new Error(`«${key}» باید workspace_overridable بولی داشته باشد.`);
    }
    out[key] = {
      default: field.default,
      workspace_overridable: field.workspace_overridable,
    };
  }
  return out;
}

export function formatSettingsSchema(schema: SettingsSchema | undefined): string {
  if (!schema || Object.keys(schema).length === 0) return "{\n}\n";
  return `${JSON.stringify(schema, null, 2)}\n`;
}

function readSchema(raw: unknown): SettingsSchema | undefined {
  if (typeof raw === "string") return parseSettingsSchema(raw);
  if (raw && typeof raw === "object") return parseSettingsSchema(JSON.stringify(raw));
  return undefined;
}

function normalizeAgent(raw: unknown, fallbackId?: string): AgentOut {
  if (raw === null || typeof raw !== "object") {
    throw new Error("پاسخ ایجنت نامعتبر است.");
  }
  const row = raw as Record<string, unknown>;
  const id = typeof row.id === "string" && row.id ? row.id : fallbackId || "";
  if (!id) throw new Error("ایجنت بدون id برگشته است.");
  return {
    id,
    name: typeof row.name === "string" ? row.name : id,
    kind: isKind(row.kind) ? row.kind : "custom",
    policy: typeof row.policy === "string" ? row.policy : "",
    reject_text: typeof row.reject_text === "string" ? row.reject_text : "",
    clarify_first: Boolean(row.clarify_first),
    published: Boolean(row.published),
    settings_schema: readSchema(row.settings_schema) ?? {},
  };
}

/** Keep fields the response omitted (publish may return only `{ published }`). */
export function overlayAgent(current: AgentOut, raw: unknown): AgentOut {
  if (!raw || typeof raw !== "object") return current;
  const row = raw as Record<string, unknown>;
  const schema = readSchema(row.settings_schema);
  return {
    ...current,
    id: typeof row.id === "string" && row.id ? row.id : current.id,
    name: typeof row.name === "string" ? row.name : current.name,
    kind: isKind(row.kind) ? row.kind : current.kind,
    policy: typeof row.policy === "string" ? row.policy : current.policy,
    reject_text: typeof row.reject_text === "string" ? row.reject_text : current.reject_text,
    clarify_first: typeof row.clarify_first === "boolean" ? row.clarify_first : current.clarify_first,
    published: typeof row.published === "boolean" ? row.published : current.published,
    settings_schema: schema ?? current.settings_schema,
  };
}

function normalizeList(data: unknown): AgentListOut {
  if (Array.isArray(data)) {
    const items = data.map((row) => normalizeAgent(row));
    return { items, total: items.length, limit: items.length, offset: 0 };
  }
  if (data && typeof data === "object" && Array.isArray((data as AgentListOut).items)) {
    const body = data as AgentListOut;
    const items = body.items.map((row) => normalizeAgent(row));
    return {
      items,
      total: typeof body.total === "number" ? body.total : items.length,
      limit: typeof body.limit === "number" ? body.limit : items.length,
      offset: typeof body.offset === "number" ? body.offset : 0,
    };
  }
  throw new Error("فهرست ایجنت‌ها شکل مورد انتظار را ندارد.");
}

function agentBody(input: AgentInput): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: input.name,
    kind: input.kind,
    policy: input.policy,
    reject_text: input.reject_text,
    clarify_first: input.clarify_first,
    settings_schema: input.settings_schema,
    published: input.published,
  };
  if (input.id?.trim()) body.id = input.id.trim();
  return body;
}

export async function listAgents(): Promise<AgentListOut> {
  const data = await apiFetch<unknown>("/api/v1/agents");
  return normalizeList(data);
}

export function getAgent(id: string): Promise<AgentOut> {
  return apiFetch<unknown>(`/api/v1/agents/${encodeURIComponent(id)}`).then((raw) =>
    normalizeAgent(raw, id),
  );
}

export function createAgent(input: AgentInput): Promise<AgentOut> {
  return apiFetch<unknown>("/api/v1/agents", {
    method: "POST",
    body: JSON.stringify(agentBody(input)),
  }).then((raw) => normalizeAgent(raw, input.id));
}

export function patchAgent(
  id: string,
  input: Partial<Omit<AgentInput, "id" | "published">>,
): Promise<AgentOut> {
  return apiFetch<unknown>(`/api/v1/agents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  }).then((raw) => normalizeAgent(raw, id));
}

/** Internal publish flag. `POST /api/v1/agents/{id}/publish`. */
export async function publishAgent(id: string, published: boolean): Promise<unknown> {
  const data = await apiFetch<unknown>(`/api/v1/agents/${encodeURIComponent(id)}/publish`, {
    method: "POST",
    body: JSON.stringify({ published }),
  });
  return data ?? { id, published };
}

function wsAgentsPath(workspaceId: string, id?: string): string {
  const base = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/agents`;
  return id ? `${base}/${encodeURIComponent(id)}` : base;
}

function normalizeBinding(raw: unknown): WorkspaceAgentBinding {
  if (raw === null || typeof raw !== "object") {
    throw new Error("اتصال ایجنت نامعتبر است.");
  }
  const row = raw as Record<string, unknown>;
  const id = typeof row.id === "string" ? row.id : "";
  const agentId = typeof row.agent_id === "string" ? row.agent_id : id;
  if (!id && !agentId) throw new Error("اتصال ایجنت بدون شناسه است.");
  const overrides =
    row.overrides && typeof row.overrides === "object" && !Array.isArray(row.overrides)
      ? (row.overrides as Record<string, unknown>)
      : {};
  return {
    id: id || agentId,
    agent_id: agentId,
    enabled: typeof row.enabled === "boolean" ? row.enabled : true,
    overrides,
  };
}

export async function listWorkspaceAgents(workspaceId: string): Promise<WorkspaceAgentBinding[]> {
  const data = await apiFetch<unknown>(wsAgentsPath(workspaceId));
  if (Array.isArray(data)) return data.map(normalizeBinding);
  if (data && typeof data === "object" && Array.isArray((data as { items?: unknown[] }).items)) {
    return (data as { items: unknown[] }).items.map(normalizeBinding);
  }
  throw new Error("فهرست ایجنت‌های workspace شکل مورد انتظار را ندارد.");
}

export function attachWorkspaceAgent(
  workspaceId: string,
  agentId: string,
): Promise<WorkspaceAgentBinding> {
  return apiFetch<unknown>(wsAgentsPath(workspaceId), {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId }),
  }).then(normalizeBinding);
}

export function patchWorkspaceAgent(
  workspaceId: string,
  id: string,
  patch: WorkspaceAgentPatch,
): Promise<WorkspaceAgentBinding> {
  return apiFetch<unknown>(wsAgentsPath(workspaceId, id), {
    method: "PATCH",
    body: JSON.stringify(patch),
  }).then(normalizeBinding);
}

export async function detachWorkspaceAgent(workspaceId: string, id: string): Promise<void> {
  await apiFetch(wsAgentsPath(workspaceId, id), { method: "DELETE" });
}

/** Chat runtime response is passed through; request body is `{ message }`. */
export function chatWorkspaceAgent(
  workspaceId: string,
  id: string,
  message: string,
): Promise<unknown> {
  return apiFetch(`${wsAgentsPath(workspaceId, id)}/chat`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
