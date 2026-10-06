"use client";

import type { InvestigationProgress } from "@finpulse/contracts";
import { AlertCircle, Bot, CheckCircle2, Loader2, Play } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Panel } from "@/components/fp/layout";
import { ApiErrorPanel } from "@/components/fp/states";
import { getBrowserApiClient } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { Pipeline, stepsFromProgress } from "./pipeline";

const POLL_MS = 900;

/** Starts a background investigation and follows its real progress until it finishes. */
export function InvestigationRunner({ entityId, asOf }: { entityId: string; asOf?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const [progress, setProgress] = useState<InvestigationProgress | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [starting, setStarting] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  /** Follows the run until it leaves "running"; every state shown comes from the API. */
  const follow = useCallback(
    async (id: string) => {
      for (;;) {
        await new Promise((r) => setTimeout(r, POLL_MS));
        if (!alive.current) return;
        const p = await unwrap(
          getBrowserApiClient().GET("/api/v1/investigations/{investigation_id}/progress", {
            params: { path: { investigation_id: id } },
          }),
        );
        if (!alive.current) return;
        if (p.status === "completed") {
          setProgress(null);
          setDone(id);
          const next = new URLSearchParams(search.toString());
          next.set("investigation", id);
          router.push(`${pathname}?${next.toString()}`);
          router.refresh();
          return;
        }
        setProgress(p);
        if (p.status !== "running") return;
      }
    },
    [pathname, router, search],
  );

  const start = async () => {
    setStarting(true);
    setError(null);
    setProgress(null);
    setDone(null);
    try {
      const p = await unwrap(
        getBrowserApiClient().POST("/api/v1/entities/{entity_id}/investigations", {
          params: { path: { entity_id: entityId } },
          body: asOf ? { as_of: asOf } : {},
        }),
      );
      setProgress(p);
      if (p.status === "running") await follow(p.investigation_id);
    } catch (e) {
      setError(e);
    } finally {
      setStarting(false);
    }
  };

  const running = starting || progress?.status === "running";
  const view = progress ? stepsFromProgress(progress) : null;
  const unavailable = progress?.error?.code === "llm_unavailable";

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          <Bot className="size-4 text-primary" aria-hidden />
          Run a new investigation
        </span>
      }
      description={`Deterministic engines first, then seven AI agents that may only cite verified evidence${asOf ? ` · as of ${formatDate(asOf)}` : " · latest data"}.`}
      actions={
        <button
          type="button"
          onClick={start}
          disabled={running}
          className={cn(
            "flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground shadow-sm",
            "hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-70",
          )}
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Play className="size-4" aria-hidden />
          )}
          {running ? "Investigating…" : progress || done ? "Run again" : "Run investigation"}
        </button>
      }
    >
      {error ? <ApiErrorPanel error={error} what="the investigation" /> : null}
      {done && !progress ? (
        <p className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="size-4 text-text-good" aria-hidden />
          Investigation complete. The report below is the one just produced.
        </p>
      ) : null}
      {!progress && !error && !done ? (
        <p className="text-sm text-muted-foreground">
          Each step below is reported live by the API as it happens: nothing on this panel is
          simulated.
        </p>
      ) : null}
      {progress && view ? (
        <div className="flex flex-col gap-4" aria-live="polite">
          {progress.status === "failed" ? (
            <div
              role="alert"
              className="flex gap-3 rounded-lg border border-status-critical/40 bg-status-critical/5 p-3 text-sm"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-status-critical" aria-hidden />
              <div className="flex flex-col gap-1">
                <p className="font-medium">
                  {unavailable
                    ? "The AI layer is not configured on this API."
                    : "The investigation stopped."}
                </p>
                <p className="text-muted-foreground">
                  {unavailable
                    ? "The deterministic engines ran (✓ below), but the agents need ANTHROPIC_API_KEY set on the API server. Stored investigations remain viewable."
                    : progress.error?.message}
                </p>
                {progress.error ? (
                  <p className="font-mono text-xs text-muted-foreground">{progress.error.code}</p>
                ) : null}
              </div>
            </div>
          ) : null}
          <Pipeline steps={view.steps} agents={view.agents} />
          <details className="group rounded-lg border">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
              Event log · {progress.events.length} events
            </summary>
            <ol className="max-h-64 overflow-auto border-t px-3 py-2 font-mono text-[11px]">
              {progress.events.map((e, i) => (
                <li
                  key={i}
                  className={cn(
                    "flex gap-2 py-0.5",
                    e.level === "error" && "text-status-critical",
                    e.level === "warning" && "text-foreground",
                  )}
                >
                  <span className="shrink-0 text-muted-foreground">{e.at.slice(11, 19)}</span>
                  <span className="min-w-0 break-words">{e.message}</span>
                </li>
              ))}
            </ol>
          </details>
        </div>
      ) : null}
    </Panel>
  );
}
