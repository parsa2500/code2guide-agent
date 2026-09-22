/**
 * Global brain (index + graph + vector) app config.
 *
 * - `GET /api/v1/brain-settings`
 * - `PUT /api/v1/brain-settings`
 *
 * Backend may return/accept extra fields (`qdrant_location`, `embedding_dim`,
 * `persistence`). The form only edits the three primary fields; get/put
 * round-trips known extras so PUT does not wipe them.
 *
 * Per-workspace folder indexing stays on the workspace Update tab.
 */

import { apiFetch, parseError } from "./client";

export interface BrainSettings {
  qdrant_url: string;
  embedding_provider: string;
  embedding_model: string;
  qdrant_location?: string | null;
  embedding_dim?: number | null;
  persistence?: string | null;
}

export const EMBEDDING_PROVIDERS = ["google", "fastembed", "none"] as const;

export function emptyBrainSettings(): BrainSettings {
  return {
    qdrant_url: "",
    embedding_provider: "google",
    embedding_model: "",
  };
}

function optionalString(value: unknown): string | null | undefined {
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof value === "string") return value;
  return String(value);
}

function optionalNumber(value: unknown): number | null | undefined {
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return undefined;
}

function normalize(raw: unknown): BrainSettings {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const empty = emptyBrainSettings();
  const qdrant =
    row.qdrant_url === null || row.qdrant_url === undefined
      ? ""
      : typeof row.qdrant_url === "string"
        ? row.qdrant_url
        : empty.qdrant_url;
  const out: BrainSettings = {
    qdrant_url: qdrant,
    embedding_provider:
      typeof row.embedding_provider === "string" && row.embedding_provider
        ? row.embedding_provider
        : empty.embedding_provider,
    embedding_model:
      typeof row.embedding_model === "string" ? row.embedding_model : empty.embedding_model,
  };
  if ("qdrant_location" in row) out.qdrant_location = optionalString(row.qdrant_location) ?? null;
  if ("embedding_dim" in row) {
    const dim = optionalNumber(row.embedding_dim);
    if (dim !== undefined) out.embedding_dim = dim;
  }
  if ("persistence" in row) out.persistence = optionalString(row.persistence) ?? null;
  return out;
}

export async function getBrainSettings(): Promise<BrainSettings> {
  const res = await fetch("/api/v1/brain-settings");
  if (res.status === 404) return emptyBrainSettings();
  if (!res.ok) throw new Error(await parseError(res));
  return normalize(await res.json());
}

export async function putBrainSettings(settings: BrainSettings): Promise<BrainSettings> {
  const body: Record<string, unknown> = {
    qdrant_url: settings.qdrant_url.trim() || null,
    embedding_provider: settings.embedding_provider.trim(),
    embedding_model: settings.embedding_model.trim(),
  };
  if (settings.qdrant_location !== undefined) {
    body.qdrant_location = settings.qdrant_location;
  }
  if (settings.embedding_dim !== undefined && settings.embedding_dim !== null) {
    body.embedding_dim = settings.embedding_dim;
  }
  const data = await apiFetch<unknown>("/api/v1/brain-settings", {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return normalize(data);
}
