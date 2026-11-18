import type { ReactNode } from "react";
import type { ApiError } from "../api/client";
import { EmptyIcon, OfflineIcon } from "./icons";

/** A grey block with a scan-line shimmer, standing in for content while it loads. */
export function Skeleton({ width = "100%", height = 14, style }: { width?: number | string; height?: number; style?: React.CSSProperties }) {
  return <span className="skeleton" style={{ display: "block", width, height, ...style }} aria-hidden="true" />;
}

/** Skeleton rows, announced to screen readers as loading. */
export function LoadingRows({ rows = 8, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" style={{ display: "grid", gap: 12, padding: 18 }}>
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Skeleton width={36} height={36} style={{ borderRadius: "50%" }} />
          <div style={{ flex: 1, display: "grid", gap: 6 }}>
            <Skeleton width={`${50 + ((i * 17) % 35)}%`} />
            <Skeleton width="30%" height={10} />
          </div>
          <Skeleton width={56} height={22} />
        </div>
      ))}
    </div>
  );
}

export function LoadingPanel({ height = 240, label = "Loading" }: { height?: number; label?: string }) {
  return (
    <div className="panel" role="status" aria-live="polite">
      <span className="sr-only">{label}…</span>
      <Skeleton width="40%" height={18} />
      <Skeleton height={height} style={{ marginTop: 14 }} />
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <EmptyIcon size={34} />
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const title = error.status === 404 ? "Not found" : error.status === 0 ? "Can't reach the API" : "Something went wrong";
  return (
    <div className="state state--error" role="alert">
      <OfflineIcon size={34} />
      <h2>{title}</h2>
      <p>{error.message}</p>
      {onRetry && error.status !== 404 && error.status !== 400 && (
        <button type="button" className="button button--ghost" onClick={onRetry}>Try again</button>
      )}
    </div>
  );
}
