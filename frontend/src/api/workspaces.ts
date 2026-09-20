/** App shell workspace API — snake_case types matching backend. */

import { apiFetch } from "./client";

export type WorkspaceStatus = "ready" | "indexing" | "error" | "idle";
export type AudienceDefault = "end_user" | "technical";
export type UpdateJobStatus = "running" | "success" | "failed";
export type LogLevel = "info" | "warn" | "error";
export type ChatRole = "user" | "assistant";
export type ChatbotRole = "end_user" | "technical";

export interface WorkspaceOut {
  id: string;
  name: string;
  path: string;
  description: string;
  status: WorkspaceStatus;
  updated_at: string;
  deleted_at: string | null;
}

export interface WorkspaceSettings {
  default_agent: string;
  enabled_chatbots: string[];
  audience_default: AudienceDefault;
  auto_index: boolean;
  mcp_enabled: boolean;
}

export interface WorkspaceDetailOut extends WorkspaceOut {
  created_at: string;
  settings: WorkspaceSettings;
}

export interface WorkspaceInput {
  name: string;
  path: string;
  description: string;
}

export interface WorkspaceListOut {
  items: WorkspaceOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface UpdateJob {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: UpdateJobStatus;
  summary: string;
  detail: string;
}

export interface UpdateJobAccepted {
  job_id: string;
  status: UpdateJobStatus;
  started_at: string;
}

export interface UpdateJobListOut {
  items: UpdateJob[];
  total: number;
  limit: number;
  offset: number;
}

export interface ActivityLog {
  id: string;
  at: string;
  level: LogLevel;
  source: string;
  message: string;
}

export interface ActivityLogListOut {
  items: ActivityLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface Chatbot {
  id: string;
  name: string;
  role: ChatbotRole | string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  at: string;
}

export interface ChatMessageListOut {
  items: ChatMessage[];
  total: number;
  limit: number;
  offset: number;
}

export interface SendMessageOut {
  user_message: ChatMessage;
  assistant_message: ChatMessage;
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export function listWorkspaces(opts?: {
  q?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<WorkspaceListOut> {
  return apiFetch(`/api/v1/workspaces${qs(opts || {})}`);
}

export function listDeletedWorkspaces(opts?: {
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<WorkspaceListOut> {
  return apiFetch(`/api/v1/workspaces/deleted${qs(opts || {})}`);
}

export function getWorkspace(id: string): Promise<WorkspaceDetailOut> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(id)}`);
}

export function createWorkspace(input: WorkspaceInput): Promise<WorkspaceOut> {
  return apiFetch("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateWorkspace(
  id: string,
  input: Partial<WorkspaceInput>,
): Promise<WorkspaceOut> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteWorkspace(id: string): Promise<WorkspaceOut> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function restoreWorkspace(id: string): Promise<WorkspaceOut> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(id)}/restore`, {
    method: "POST",
  });
}

export function getSettings(workspaceId: string): Promise<WorkspaceSettings> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/settings`);
}

export function putSettings(
  workspaceId: string,
  settings: WorkspaceSettings,
): Promise<WorkspaceSettings> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/settings`, {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export function startUpdate(
  workspaceId: string,
  body?: { rebuild?: boolean; scope?: "full" | "incremental" },
): Promise<UpdateJobAccepted> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/update`, {
    method: "POST",
    body: JSON.stringify(body || { rebuild: true, scope: "full" }),
  });
}

export function listUpdates(
  workspaceId: string,
  opts?: { limit?: number; offset?: number },
): Promise<UpdateJobListOut> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/updates${qs(opts || {})}`,
  );
}

export function getUpdate(workspaceId: string, jobId: string): Promise<UpdateJob> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/updates/${encodeURIComponent(jobId)}`,
  );
}

export function listLogs(
  workspaceId: string,
  opts?: { level?: string; q?: string; limit?: number; offset?: number },
): Promise<ActivityLogListOut> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/logs${qs(opts || {})}`,
  );
}

export function listChatbots(workspaceId: string): Promise<{ items: Chatbot[] }> {
  return apiFetch(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/chatbots`);
}

export function listMessages(
  workspaceId: string,
  botId: string,
  opts?: { limit?: number; offset?: number },
): Promise<ChatMessageListOut> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/chatbots/${encodeURIComponent(botId)}/messages${qs(opts || {})}`,
  );
}

export function sendMessage(
  workspaceId: string,
  botId: string,
  text: string,
): Promise<SendMessageOut> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/chatbots/${encodeURIComponent(botId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ text }),
    },
  );
}

/** Poll an update job until it leaves `running`, or attempts are exhausted. */
export async function pollUpdateJob(
  workspaceId: string,
  jobId: string,
  opts?: { intervalMs?: number; maxAttempts?: number },
): Promise<UpdateJob> {
  const intervalMs = opts?.intervalMs ?? 1500;
  const maxAttempts = opts?.maxAttempts ?? 60;
  let last = await getUpdate(workspaceId, jobId);
  for (let i = 0; i < maxAttempts && last.status === "running"; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    last = await getUpdate(workspaceId, jobId);
  }
  return last;
}
