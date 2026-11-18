import { useCallback, useEffect, useState } from "react";
import { ApiError, cached, getJson } from "../api/client";

export type ApiState<T> =
  | { status: "loading"; data?: undefined; error?: undefined }
  | { status: "error"; data?: undefined; error: ApiError }
  | { status: "ready"; data: T; error?: undefined };

/** Fetch an API path (null = don't fetch yet). Cancels the request if the path changes. */
export function useApi<T>(url: string | null): ApiState<T> & { retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<ApiState<T>>(() => {
    const hit = url ? cached<T>(url) : undefined;
    return hit !== undefined ? { status: "ready", data: hit } : { status: "loading" };
  });

  useEffect(() => {
    if (!url) return;
    const hit = cached<T>(url);
    if (hit !== undefined) {
      setState({ status: "ready", data: hit });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading" });
    getJson<T>(url, controller.signal).then(
      (data) => setState({ status: "ready", data }),
      (err: Error) => {
        if (err.name === "AbortError") return;
        setState({ status: "error", error: err instanceof ApiError ? err : new ApiError(0, err.message) });
      },
    );
    return () => controller.abort();
  }, [url, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, retry };
}
