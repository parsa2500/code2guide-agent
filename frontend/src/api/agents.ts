/**
 * Global agent registry.
 *
 * Contract (snake_case, same envelope style as `/api/v1/workspaces`):
 * - `GET  /api/v1/agents` → `{ items, total, limit, offset }` or a bare array
 * - `POST /api/v1/agents` → `AgentOut`
 * - `GET  /api/v1/agents/{id}` → `AgentOut`
 * - `PATCH /api/v1/agents/{id}` → `AgentOut` (partial; publish is `{ published }`)
 *
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
  system_policy: string;
  reject_text: string;
  clarify_first: boolean;
  published: boolean;
  settings_schema: SettingsSchema;
}

export interface AgentInput {
  name: string;
  kind: AgentKind;
  system_policy: string;
  reject_text: string;
  clarify_first: boolean;
  published: boolean;
  settings_schema: SettingsSchema;
}

export interface AgentListOut {
  items: AgentOut[];
  total: number;
  limit: number;
  offset: number;
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

function normalizeAgent(raw: unknown): AgentOut {
  if (raw === null || typeof raw !== "object") {
    throw new Error("پاسخ ایجنت نامعتبر است.");
  }
  const row = raw as Record<string, unknown>;
  const id = typeof row.id === "string" ? row.id : "";
  if (!id) throw new Error("ایجنت بدون id برگشته است.");
  let settings_schema: SettingsSchema = {};
  if (typeof row.settings_schema === "string") {
    settings_schema = parseSettingsSchema(row.settings_schema);
  } else if (row.settings_schema && typeof row.settings_schema === "object") {
    settings_schema = parseSettingsSchema(JSON.stringify(row.settings_schema));
  }
  return {
    id,
    name: typeof row.name === "string" ? row.name : id,
    kind: isKind(row.kind) ? row.kind : "custom",
    system_policy: typeof row.system_policy === "string" ? row.system_policy : "",
    reject_text: typeof row.reject_text === "string" ? row.reject_text : "",
    clarify_first: Boolean(row.clarify_first),
    published: Boolean(row.published),
    settings_schema,
  };
}

function normalizeList(data: AgentListOut | AgentOut[] | unknown): AgentListOut {
  if (Array.isArray(data)) {
    const items = data.map(normalizeAgent);
    return { items, total: items.length, limit: items.length, offset: 0 };
  }
  if (data && typeof data === "object" && Array.isArray((data as AgentListOut).items)) {
    const body = data as AgentListOut;
    const items = body.items.map(normalizeAgent);
    return {
      items,
      total: typeof body.total === "number" ? body.total : items.length,
      limit: typeof body.limit === "number" ? body.limit : items.length,
      offset: typeof body.offset === "number" ? body.offset : 0,
    };
  }
  throw new Error("فهرست ایجنت‌ها شکل مورد انتظار را ندارد.");
}

export async function listAgents(): Promise<AgentListOut> {
  const data = await apiFetch<AgentListOut | AgentOut[]>("/api/v1/agents");
  return normalizeList(data);
}

export function getAgent(id: string): Promise<AgentOut> {
  return apiFetch<unknown>(`/api/v1/agents/${encodeURIComponent(id)}`).then(normalizeAgent);
}

export function createAgent(input: AgentInput): Promise<AgentOut> {
  return apiFetch<unknown>("/api/v1/agents", {
    method: "POST",
    body: JSON.stringify(input),
  }).then(normalizeAgent);
}

export function patchAgent(id: string, input: Partial<AgentInput>): Promise<AgentOut> {
  return apiFetch<unknown>(`/api/v1/agents/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  }).then(normalizeAgent);
}

/** Internal publish flag. PATCH `{ published }` — not a separate canvas action. */
export function setAgentPublished(id: string, published: boolean): Promise<AgentOut> {
  return patchAgent(id, { published });
}
