/** Guide chat (sessions + SSE) API client. */

import { apiFetch, parseError } from "./client";

export type GuideChatRole = "user" | "assistant";

export interface GuideSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface GuideStep {
  id: string;
  phase: string;
  title: string;
  detail: string;
}

export interface GuideMessage {
  id: string;
  role: GuideChatRole;
  text: string;
  at: string;
  steps?: GuideStep[] | null;
}

export interface GuideMessageListOut {
  items: GuideMessage[];
  total: number;
  limit: number;
  offset: number;
}

export type GuideStreamHandlers = {
  onStep?: (step: GuideStep) => void;
  onClarify?: (text: string) => void;
  onFinal?: (message: GuideMessage) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
};

export function listGuideSessions(workspaceId: string): Promise<{ items: GuideSession[] }> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/guide-sessions`,
  );
}

export function createGuideSession(workspaceId: string): Promise<GuideSession> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/guide-sessions`,
    { method: "POST", body: "{}" },
  );
}

export function deleteGuideSession(workspaceId: string, sessionId: string): Promise<void> {
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/guide-sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}

export function listGuideMessages(
  workspaceId: string,
  sessionId: string,
  opts?: { limit?: number; offset?: number },
): Promise<GuideMessageListOut> {
  const sp = new URLSearchParams();
  if (opts?.limit != null) sp.set("limit", String(opts.limit));
  if (opts?.offset != null) sp.set("offset", String(opts.offset));
  const q = sp.toString() ? `?${sp}` : "";
  return apiFetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/guide-sessions/${encodeURIComponent(sessionId)}/messages${q}`,
  );
}

function parseSseChunk(
  buffer: string,
  onEvent: (event: string, data: unknown) => void,
): string {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const block of parts) {
    if (!block.trim()) continue;
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    const raw = dataLines.join("\n");
    if (!raw) continue;
    try {
      onEvent(event, JSON.parse(raw));
    } catch {
      onEvent(event, { message: raw });
    }
  }
  return rest;
}

export async function streamGuideMessage(
  workspaceId: string,
  sessionId: string,
  text: string,
  handlers: GuideStreamHandlers,
): Promise<void> {
  const res = await fetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/guide-sessions/${encodeURIComponent(sessionId)}/messages/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ text }),
    },
  );
  if (!res.ok) throw new Error(await parseError(res));
  if (!res.body) throw new Error("No response body for SSE stream");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    handlers.onDone?.();
  };

  const dispatch = (event: string, data: unknown) => {
    const obj = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
    if (event === "step") {
      handlers.onStep?.({
        id: String(obj.id ?? ""),
        phase: String(obj.phase ?? ""),
        title: String(obj.title ?? ""),
        detail: String(obj.detail ?? ""),
      });
    } else if (event === "clarify") {
      handlers.onClarify?.(String(obj.text ?? ""));
    } else if (event === "final") {
      const msg = obj.message as GuideMessage | undefined;
      if (msg) handlers.onFinal?.(msg);
    } else if (event === "error") {
      handlers.onError?.(String(obj.message ?? "خطای ناشناخته"));
    } else if (event === "done") {
      finish();
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = parseSseChunk(buffer, dispatch);
  }
  if (buffer.trim()) {
    buffer = parseSseChunk(buffer + "\n\n", dispatch);
  }
  finish();
}
