/**
 * Global agent registry + workspace agent bindings.
 *
 * Live wire (`src/api/schemas/agents.py`, shell routes):
 * - `GET/POST /api/v1/agents`
 * - `GET/PATCH /api/v1/agents/{agent_id}`
 * - `POST /api/v1/agents/{agent_id}/publish` body `{ published }`
 * - `GET/POST /api/v1/workspaces/{ws_id}/agents`
 * - `PATCH/DELETE /api/v1/workspaces/{ws_id}/agents/{agent_id}`
 * - `POST /api/v1/workspaces/{ws_id}/agents/{agent_id}/chat` body `{ message }`
 *
 * Wire field is `policy_text`. UI state keeps the friendly name `policy`.
 * List envelope is `{ items, total }` (no limit/offset).
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
  /** UI-facing policy text; wire name is `policy_text`. */
  policy: string;
  reject_text: string;
  clarify_first: boolean;
  published: boolean;
  settings_schema: SettingsSchema;
  created_at?: string;
  updated_at?: string;
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
}

/** Row from `GET /api/v1/workspaces/{ws_id}/agents` — key is `agent_id`. */
export interface WorkspaceAgentBinding {
  workspace_id: string;
  agent_id: string;
  enabled: boolean;
  overrides: Record<string, unknown>;
  effective_settings: Record<string, unknown>;
  definition?: AgentOut | null;
}

export interface WorkspaceAgentPatch {
  enabled?: boolean;
  overrides?: Record<string, unknown>;
}

export interface AgentChatOut {
  agent_id: string;
  answer: string;
  clarify: boolean;
  rejected: boolean;
  hits: Record<string, unknown>[];
  effective_settings: Record<string, unknown>;
}

const KINDS: readonly AgentKind[] = ["jarvis", "end_user", "technical", "custom"];

function isKind(value: unknown): value is AgentKind {
  return typeof value === "string" && (KINDS as readonly string[]).includes(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function readPolicy(row: Record<string, unknown>): string {
  if (typeof row.policy_text === "string") return row.policy_text;
  if (typeof row.policy === "string") return row.policy;
  return "";
}

/** Strict parse for form submit — backend expects key → {default, workspace_overridable}. */
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

/** Lenient response parse — empty `{}` and well-formed keys; ignore unknown shapes. */
function readSchema(raw: unknown): SettingsSchema {
  if (raw == null) return {};
  let parsed: unknown = raw;
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) return {};
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return {};
    }
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return {};
  const out: SettingsSchema = {};
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (!key.trim()) continue;
    if (value === null || typeof value !== "object" || Array.isArray(value)) continue;
    const field = value as Record<string, unknown>;
    if (!("default" in field) || typeof field.workspace_overridable !== "boolean") continue;
    out[key] = {
      default: field.default,
      workspace_overridable: field.workspace_overridable,
    };
  }
  return out;
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
    policy: readPolicy(row),
    reject_text: typeof row.reject_text === "string" ? row.reject_text : "",
    clarify_first: Boolean(row.clarify_first),
    published: Boolean(row.published),
    settings_schema: readSchema(row.settings_schema),
    created_at: typeof row.created_at === "string" ? row.created_at : undefined,
    updated_at: typeof row.updated_at === "string" ? row.updated_at : undefined,
  };
}

/** Overlay partial responses onto a known agent (publish always returns full Out). */
export function overlayAgent(current: AgentOut, raw: unknown): AgentOut {
  if (!raw || typeof raw !== "object") return current;
  const row = raw as Record<string, unknown>;
  const policy =
    typeof row.policy_text === "string" || typeof row.policy === "string"
      ? readPolicy(row)
      : current.policy;
  return {
    ...current,
    id: typeof row.id === "string" && row.id ? row.id : current.id,
    name: typeof row.name === "string" ? row.name : current.name,
    kind: isKind(row.kind) ? row.kind : current.kind,
    policy,
    reject_text: typeof row.reject_text === "string" ? row.reject_text : current.reject_text,
    clarify_first: typeof row.clarify_first === "boolean" ? row.clarify_first : current.clarify_first,
    published: typeof row.published === "boolean" ? row.published : current.published,
    settings_schema:
      row.settings_schema !== undefined ? readSchema(row.settings_schema) : current.settings_schema,
    created_at: typeof row.created_at === "string" ? row.created_at : current.created_at,
    updated_at: typeof row.updated_at === "string" ? row.updated_at : current.updated_at,
  };
}

function normalizeList(data: unknown): AgentListOut {
  if (Array.isArray(data)) {
    const items = data.map((row) => normalizeAgent(row));
    return { items, total: items.length };
  }
  if (data && typeof data === "object" && Array.isArray((data as { items?: unknown }).items)) {
    const body = data as { items: unknown[]; total?: number };
    const items = body.items.map((row) => normalizeAgent(row));
    return {
      items,
      total: typeof body.total === "number" ? body.total : items.length,
    };
  }
  throw new Error("فهرست ایجنت‌ها شکل مورد انتظار را ندارد.");
}

/** Wire body — always `policy_text`, never bare `policy`. */
function agentCreateBody(input: AgentInput): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: input.name,
    kind: input.kind,
    policy_text: input.policy,
    reject_text: input.reject_text,
    clarify_first: input.clarify_first,
    settings_schema: input.settings_schema,
    published: input.published,
  };
  if (input.id?.trim()) body.id = input.id.trim();
  return body;
}

function agentPatchBody(
  input: Partial<Omit<AgentInput, "id" | "published">>,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.kind !== undefined) body.kind = input.kind;
  if (input.policy !== undefined) body.policy_text = input.policy;
  if (input.reject_text !== undefined) body.reject_text = input.reject_text;
  if (input.clarify_first !== undefined) body.clarify_first = input.clarify_first;
  if (input.settings_schema !== undefined) body.settings_schema = input.settings_schema;
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
    body: JSON.stringify(agentCreateBody(input)),
  }).then((raw) => normalizeAgent(raw, input.id));
}

export function patchAgent(
  id: string,
  input: Partial<Omit<AgentInput, "id" | "published">>,
): Promise<AgentOut> {
  return apiFetch<unknown>(`/api/v1/agents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(agentPatchBody(input)),
  }).then((raw) => normalizeAgent(raw, id));
}

/** Internal publish flag. `POST /api/v1/agents/{agent_id}/publish`. */
export async function publishAgent(id: string, published: boolean): Promise<AgentOut> {
  const data = await apiFetch<unknown>(`/api/v1/agents/${encodeURIComponent(id)}/publish`, {
    method: "POST",
    body: JSON.stringify({ published }),
  });
  return normalizeAgent(data, id);
}

function wsAgentsPath(workspaceId: string, agentId?: string): string {
  const base = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/agents`;
  return agentId ? `${base}/${encodeURIComponent(agentId)}` : base;
}

function normalizeBinding(raw: unknown, fallbackWorkspaceId?: string): WorkspaceAgentBinding {
  if (raw === null || typeof raw !== "object") {
    throw new Error("اتصال ایجنت نامعتبر است.");
  }
  const row = raw as Record<string, unknown>;
  const agentId = typeof row.agent_id === "string" ? row.agent_id : "";
  if (!agentId) throw new Error("اتصال ایجنت بدون agent_id است.");
  const definition =
    row.definition && typeof row.definition === "object"
      ? normalizeAgent(row.definition, agentId)
      : null;
  return {
    workspace_id:
      typeof row.workspace_id === "string" && row.workspace_id
        ? row.workspace_id
        : fallbackWorkspaceId || "",
    agent_id: agentId,
    enabled: typeof row.enabled === "boolean" ? row.enabled : true,
    overrides: asRecord(row.overrides),
    effective_settings: asRecord(row.effective_settings),
    definition,
  };
}

export async function listWorkspaceAgents(workspaceId: string): Promise<WorkspaceAgentBinding[]> {
  const data = await apiFetch<unknown>(wsAgentsPath(workspaceId));
  if (Array.isArray(data)) {
    return data.map((row) => normalizeBinding(row, workspaceId));
  }
  if (data && typeof data === "object" && Array.isArray((data as { items?: unknown[] }).items)) {
    return (data as { items: unknown[] }).items.map((row) => normalizeBinding(row, workspaceId));
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
  }).then((raw) => normalizeBinding(raw, workspaceId));
}

export function patchWorkspaceAgent(
  workspaceId: string,
  agentId: string,
  patch: WorkspaceAgentPatch,
): Promise<WorkspaceAgentBinding> {
  return apiFetch<unknown>(wsAgentsPath(workspaceId, agentId), {
    method: "PATCH",
    body: JSON.stringify(patch),
  }).then((raw) => normalizeBinding(raw, workspaceId));
}

export async function detachWorkspaceAgent(workspaceId: string, agentId: string): Promise<void> {
  await apiFetch(wsAgentsPath(workspaceId, agentId), { method: "DELETE" });
}

export function chatWorkspaceAgent(
  workspaceId: string,
  agentId: string,
  message: string,
): Promise<AgentChatOut> {
  return apiFetch(`${wsAgentsPath(workspaceId, agentId)}/chat`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
