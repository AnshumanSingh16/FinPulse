"use client";

import type { DemoResetResult } from "@finpulse/contracts";
import { CheckCircle2, Loader2, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiErrorPanel, toErrorInfo } from "@/components/fp/states";
import { getBrowserApiClient } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/** Restores the exact demo state: re-seeds every synthetic entity, clears investigations. */
export function DemoResetButton({ className }: { className?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DemoResetResult | null>(null);
  const [error, setError] = useState<unknown>(null);

  const reset = async () => {
    if (
      !window.confirm(
        "Reset the demo? This re-seeds every synthetic entity and clears all investigations.",
      )
    )
      return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await unwrap(
        getBrowserApiClient().POST("/api/v1/demo/reset", { body: { seed: true } }),
      );
      setResult(r);
      router.refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={cn("flex flex-col items-start gap-2", className)}>
      <button
        type="button"
        onClick={reset}
        disabled={busy}
        className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm font-medium shadow-xs hover:bg-muted disabled:opacity-70"
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <RotateCcw className="size-4" aria-hidden />
        )}
        {busy ? "Resetting…" : "Reset demo"}
      </button>
      {result ? (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
          <CheckCircle2 className="size-3.5 text-text-good" aria-hidden />
          Restored: {result.seeded.length} entities re-seeded, {result.investigations_cleared}{" "}
          investigation
          {result.investigations_cleared === 1 ? "" : "s"} cleared.
        </p>
      ) : null}
      {error ? <ApiErrorPanel error={toErrorInfo(error)} what="the demo reset" /> : null}
    </div>
  );
}
