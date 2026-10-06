"use client";

import { AlertCircle, RotateCcw } from "lucide-react";

/** Unexpected render failures in a section; API errors are handled inline by each page. */
export default function SectionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-xl border border-status-critical/40 bg-status-critical/5 p-5"
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        <AlertCircle className="size-4 text-status-critical" aria-hidden />
        This section could not be displayed.
      </div>
      <p className="text-sm text-muted-foreground">
        {error.message || "Unexpected error."}
        {error.digest ? <span className="ml-1 font-mono text-xs">({error.digest})</span> : null}
      </p>
      <button
        type="button"
        onClick={reset}
        className="flex items-center gap-1.5 rounded-md border bg-card px-3 py-1.5 text-sm hover:bg-muted"
      >
        <RotateCcw className="size-3.5" aria-hidden /> Try again
      </button>
    </div>
  );
}
