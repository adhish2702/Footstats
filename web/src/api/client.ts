import type { ApiErrorBody } from "./types";

/** Base URL of the API: the deployed one in production, the dev proxy locally. */
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "/api";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

// Responses only change when the pipeline reloads the database, so a page
// visit can reuse what it has already fetched.
const cache = new Map<string, unknown>();

/** Build "/players?a=1&b=2", leaving out empty values. */
export function path(base: string, params: Record<string, string | number | undefined | null> = {}): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `${base}?${qs}` : base;
}

export function cached<T>(url: string): T | undefined {
  return cache.get(url) as T | undefined;
}

export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const hit = cache.get(url);
  if (hit !== undefined) return hit as T;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${url}`, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "Can't reach the FootStats API. Check that it is running.");
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as ApiErrorBody;
      message = body.error.details?.length
        ? `${body.error.message}: ${body.error.details.map((d) => `${d.param} ${d.message}`).join("; ")}`
        : body.error.message;
    } catch {
      // not JSON; keep the generic message
    }
    throw new ApiError(res.status, message);
  }
  const body = (await res.json()) as T;
  cache.set(url, body);
  return body;
}
