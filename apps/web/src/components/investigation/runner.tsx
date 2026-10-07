"use client";

import type { InvestigationProgress } from "@finpulse/contracts";
import { AlertCircle, CheckCircle2, Loader2, Play, Radio } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiErrorPanel } from "@/components/fp/states";
import { getBrowserApiClient } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { TimelineView, timelineCounts } from "./timeline";

const POLL_MS = 900;

function useElapsed(since: string | null, active: boolean): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  if (!since) return null;
  const s = Math.max(0, Math.floor((now - Date.parse(since)) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Starts a background investigation and follows its real progress until it finishes. */
export function InvestigationRunner({
  entityId,
  entityName,
  asOf,
}: {
  entityId: string;
  entityName: string;
  asOf?: string;
}) {
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
          router.push(`${pathname}?${next.toString()}`, { scroll: false });
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
  const elapsed = useElapsed(progress?.started_at ?? null, progress?.status === "running");
  const unavailable = progress?.error?.code === "llm_unavailable";
  const latest = progress?.events.at(-1);
  const counts = progress ? timelineCounts(progress.timeline) : null;

  return (
    <section className="overflow-hidden rounded-xl border bg-card shadow-xs">
      <div className="flex flex-col gap-4 bg-sidebar px-5 py-5 text-sidebar-foreground sm:flex-row sm:items-center sm:px-6">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-[11px] font-semibold tracking-wider text-sidebar-muted uppercase">
            Financial investigation · {asOf ? `as of ${formatDate(asOf)}` : "latest data"}
          </span>
          <h2 className="text-lg font-semibold text-balance">Investigate {entityName}</h2>
          <p className="text-xs text-pretty text-sidebar-muted">
            Deterministic engines collect the evidence. Specialist agents investigate it, a red team
            challenges them, a verifier audits every claim, and a senior agent writes the
            assessment.
          </p>
        </div>
        <button
          type="button"
          onClick={start}
          disabled={running}
          className={cn(
            "flex shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm",
            "hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-80",
          )}
        >
          {running ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Play className="size-4" aria-hidden />
          )}
          {running
            ? "Investigating…"
            : progress || done
              ? "Run a new investigation"
              : "Start investigation"}
        </button>
      </div>

      {progress ? (
        <div
          className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b bg-muted/40 px-5 py-2.5 text-xs sm:px-6"
          aria-live="polite"
        >
          {progress.status === "running" ? (
            <span className="flex items-center gap-1.5 font-semibold text-primary">
              <Radio className="size-3.5 animate-pulse" aria-hidden /> Live
            </span>
          ) : null}
          {counts ? (
            <span className="tabular">
              {counts.done} of {counts.total} steps complete
            </span>
          ) : null}
          {elapsed && progress.status === "running" ? (
            <span className="tabular text-muted-foreground">Elapsed {elapsed}</span>
          ) : null}
          {latest && progress.status === "running" ? (
            <span className="min-w-0 flex-1 truncate text-muted-foreground">
              Latest event: {latest.message}
            </span>
          ) : null}
          <span className="ml-auto text-[11px] text-muted-foreground">
            Every state is reported by the API as it happens. Nothing is simulated.
          </span>
        </div>
      ) : null}

      <div className="flex flex-col gap-4 p-5 sm:p-6">
        {error ? <ApiErrorPanel error={error} what="the investigation" /> : null}
        {done && !progress ? (
          <p className="flex items-center gap-2 text-sm">
            <CheckCircle2 className="size-4 text-text-good" aria-hidden />
            Investigation complete. Its timeline and report are below.
          </p>
        ) : null}
        {!progress && !error && !done ? (
          <p className="text-sm text-muted-foreground">
            Start an investigation to watch each step live. The most recent completed investigation
            is shown below.
          </p>
        ) : null}
        {progress?.status === "failed" ? (
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
                  ? "Step 1 ran on the deterministic engines, but the agents need ANTHROPIC_API_KEY set on the API server, so steps 2–8 could not run. Stored investigations remain viewable."
                  : progress.error?.message}
              </p>
              {progress.error ? (
                <p className="font-mono text-xs text-muted-foreground">{progress.error.code}</p>
              ) : null}
            </div>
          </div>
        ) : null}
        {progress ? (
          <>
            <TimelineView timeline={progress.timeline} ctx={{ entityId, asOf }} />
            <details className="rounded-lg border">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
                Raw event log · {progress.events.length} events
              </summary>
              <ol className="max-h-64 overflow-auto border-t px-3 py-2 font-mono text-[11px]">
                {progress.events.map((e, i) => (
                  <li
                    key={i}
                    className={cn(
                      "flex gap-2 py-0.5",
                      e.level === "error" && "text-status-critical",
                    )}
                  >
                    <span className="shrink-0 text-muted-foreground">{e.at.slice(11, 19)}</span>
                    <span className="min-w-0 break-words">{e.message}</span>
                  </li>
                ))}
              </ol>
            </details>
          </>
        ) : null}
      </div>
    </section>
  );
}
