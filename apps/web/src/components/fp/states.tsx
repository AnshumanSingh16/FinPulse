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

export function ApiErrorPanel({ error, what }: { error: unknown; what: string }) {
  const e = error instanceof ApiError ? error : null;
  return (
    <div
      role="alert"
      className="flex gap-3 rounded-xl border border-status-critical/40 bg-status-critical/5 p-4 text-sm"
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-status-critical" aria-hidden />
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-medium">Could not load {what}.</p>
        <p className="text-muted-foreground">
          {e ? (e.detail ?? e.title) : error instanceof Error ? error.message : "Unknown error."}
        </p>
        {e ? (
          <p className="text-xs text-muted-foreground">
            {e.code}
            {e.status ? ` · HTTP ${e.status}` : ""}
            {e.requestId ? ` · request ${e.requestId}` : ""}
          </p>
        ) : null}
      </div>
    </div>
  );
}
