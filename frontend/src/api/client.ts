export type Audience = "technical" | "end_user";

export interface AskResponse {
  query: string;
  guide: string;
  breadcrumbs: string[];
  routes_found: number;
  forms_found: number;
  steps_taken: string[];
}

export interface IndexStatus {
  workspace_path?: string;
  exists?: boolean;
  indexed?: boolean;
  last_indexed_at?: string | null;
  routes?: number;
  forms?: number;
  api_endpoints?: number;
  services?: number;
  entities?: number;
  edges?: number;
  message?: string;
  [key: string]: unknown;
}

export interface IndexResponse {
  workspace_path: string;
  duration_ms: number;
  routes: number;
  forms: number;
  api_endpoints: number;
  services: number;
  entities: number;
  tables: number;
  edges: number;
  message: string;
  [key: string]: unknown;
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("؛ ");
    }
    return JSON.stringify(body);
  } catch {
    return `HTTP ${res.status}`;
  }
}

export async function askGuide(
  query: string,
  audience: Audience,
  workspacePath?: string,
): Promise<AskResponse> {
  const path = audience === "end_user" ? "/api/v1/ask-enduser" : "/api/v1/ask";
  const body: Record<string, string> = { query };
  if (workspacePath?.trim()) body.workspace_path = workspacePath.trim();

  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function indexWorkspace(
  workspacePath?: string,
  rebuild = true,
): Promise<IndexResponse> {
  const body: Record<string, unknown> = { rebuild };
  if (workspacePath?.trim()) body.workspace_path = workspacePath.trim();

  const res = await fetch("/api/v1/index-workspace", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchIndexStatus(workspacePath?: string): Promise<IndexStatus> {
  const qs = workspacePath?.trim()
    ? `?workspace_path=${encodeURIComponent(workspacePath.trim())}`
    : "";
  const res = await fetch(`/api/v1/index/status${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** Convert literal \\n sequences into real newlines for Markdown parsers. */
export function normalizeGuideMarkdown(text: string): string {
  if (!text) return "";
  let guide = String(text).trim();
  const realNewlines = (guide.match(/\n/g) || []).length;
  if (guide.includes("\\n") && realNewlines <= 1) {
    guide = guide
      .replace(/\\r\\n/g, "\n")
      .replace(/\\n/g, "\n")
      .replace(/\\t/g, "\t")
      .replace(/\\r/g, "");
  }
  return guide.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim() + "\n";
}
