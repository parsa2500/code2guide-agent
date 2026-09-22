/**
 * Global brain (index + graph + vector) app config.
 *
 * - `GET /api/v1/brain-settings`
 * - `PUT /api/v1/brain-settings`
 *
 * Per-workspace folder indexing stays on the workspace Update tab.
 */

import { apiFetch, parseError } from "./client";

export interface BrainSettings {
  qdrant_url: string;
  embedding_provider: string;
  embedding_model: string;
}

export const EMBEDDING_PROVIDERS = ["google", "fastembed", "none"] as const;

export function emptyBrainSettings(): BrainSettings {
  return {
    qdrant_url: "",
    embedding_provider: "google",
    embedding_model: "",
  };
}

function normalize(raw: unknown): BrainSettings {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const empty = emptyBrainSettings();
  return {
    qdrant_url: typeof row.qdrant_url === "string" ? row.qdrant_url : empty.qdrant_url,
    embedding_provider:
      typeof row.embedding_provider === "string" && row.embedding_provider
        ? row.embedding_provider
        : empty.embedding_provider,
    embedding_model:
      typeof row.embedding_model === "string" ? row.embedding_model : empty.embedding_model,
  };
}

export async function getBrainSettings(): Promise<BrainSettings> {
  const res = await fetch("/api/v1/brain-settings");
  if (res.status === 404) return emptyBrainSettings();
  if (!res.ok) throw new Error(await parseError(res));
  return normalize(await res.json());
}

export async function putBrainSettings(settings: BrainSettings): Promise<BrainSettings> {
  const data = await apiFetch<unknown>("/api/v1/brain-settings", {
    method: "PUT",
    body: JSON.stringify({
      qdrant_url: settings.qdrant_url.trim(),
      embedding_provider: settings.embedding_provider.trim(),
      embedding_model: settings.embedding_model.trim(),
    }),
  });
  return normalize(data);
}
