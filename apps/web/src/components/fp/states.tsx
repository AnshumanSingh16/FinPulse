import { AlertCircle, Inbox } from "lucide-react";
import type * as React from "react";

import { ApiError } from "@/lib/api/errors";

export function EmptyState({
  title,
  children,
  icon: Icon = Inbox,
}: {
  title: string;
  children?: React.ReactNode;
  icon?: typeof Inbox;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center">
      <Icon className="size-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="max-w-md text-sm text-muted-foreground">{children}</div> : null}
    </div>
  );
}

/** Plain, serialisable description of a failure (never pass Error objects as props: in dev,
 * React serialises props for debugging and some low-level network errors break that). */
export type ErrorInfo = {
  message: string;
  code: string | null;
  status: number | null;
  requestId: string | null;
};

export function toErrorInfo(error: unknown): ErrorInfo {
  if (error instanceof ApiError)
    return {
      message: error.detail ?? error.title,
      code: error.code,
      status: error.status || null,
      requestId: error.requestId,
    };
  return {
    message: error instanceof Error ? error.message : "Unknown error.",
    code: null,
    status: null,
    requestId: null,
  };
}

export function ApiErrorPanel({ error, what }: { error: ErrorInfo; what: string }) {
  const unreachable = error.code === "network_error" || error.code === "timeout";
  return (
    <div
      role="alert"
      className="flex gap-3 rounded-xl border border-status-critical/40 bg-status-critical/5 p-4 text-sm"
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-status-critical" aria-hidden />
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-medium">Could not load {what}.</p>
        <p className="text-muted-foreground">
          {unreachable
            ? "The business-risk module needs its Python API, which isn't running. Start everything with `npm run demo` (needs uv and Docker or PostgreSQL). The personal-finance product works without it."
            : error.message}
        </p>
        {error.code ? (
          <p className="text-xs text-muted-foreground">
            {error.code}
            {error.status ? ` · HTTP ${error.status}` : ""}
            {error.requestId ? ` · request ${error.requestId}` : ""}
          </p>
        ) : null}
      </div>
    </div>
  );
}
