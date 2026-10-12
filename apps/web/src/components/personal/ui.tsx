"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Info,
  OctagonAlert,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import type * as React from "react";

import type { AffordabilityLabel, CheckStatus } from "@/lib/personal/finance/affordability";
import type { StateView } from "@/lib/personal/client";
import type { FieldSourceKind } from "@/lib/personal/schemas";
import type { ApprovalStatus } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

export const ASSESSMENT: Record<
  AffordabilityLabel,
  { text: string; short: string; className: string; icon: typeof Info }
> = {
  comfortable: {
    text: "Comfortable under the stated assumptions",
    short: "Comfortable",
    className: "border-status-good/40 bg-status-good/10 text-text-good",
    icon: CheckCircle2,
  },
  manageable_limited_buffer: {
    text: "Potentially manageable, but with limited buffer",
    short: "Limited buffer",
    className: "border-status-warning/40 bg-status-warning/10 text-status-warning",
    icon: AlertTriangle,
  },
  high_strain: {
    text: "High financial strain under the stated assumptions",
    short: "High strain",
    className: "border-status-critical/50 bg-status-critical/10 text-chart-negative",
    icon: OctagonAlert,
  },
  insufficient_information: {
    text: "Insufficient information for a reliable assessment",
    short: "Need more info",
    className: "border-border bg-muted text-muted-foreground",
    icon: Info,
  },
};

export function AssessmentBadge({
  label,
  long = false,
  className,
}: {
  label: AffordabilityLabel;
  long?: boolean;
  className?: string;
}) {
  const a = ASSESSMENT[label];
  const Icon = a.icon;
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        a.className,
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {long ? a.text : a.short}
    </span>
  );
}

export function CheckBadge({ status }: { status: CheckStatus }) {
  const map = {
    pass: { t: "Pass", c: "text-text-good bg-status-good/10", i: CheckCircle2 },
    warn: { t: "Watch", c: "text-status-warning bg-status-warning/10", i: AlertTriangle },
    fail: { t: "Breach", c: "text-chart-negative bg-status-critical/10", i: OctagonAlert },
  }[status];
  const Icon = map.i;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium",
        map.c,
      )}
    >
      <Icon className="size-3" aria-hidden /> {map.t}
    </span>
  );
}

const SOURCE: Record<
  FieldSourceKind | "illustrative" | "default" | "research",
  { t: string; c: string }
> = {
  user: { t: "You entered", c: "bg-primary/10 text-primary" },
  demo: { t: "Demo data", c: "bg-chart-1/15 text-[#8fb8ee]" },
  document: { t: "From document", c: "bg-chart-3/15 text-[#6fd3ad]" },
  derived: { t: "Calculated", c: "bg-muted text-muted-foreground" },
  illustrative: { t: "Illustrative", c: "bg-status-warning/10 text-status-warning" },
  default: { t: "Default assumption", c: "bg-status-warning/10 text-status-warning" },
  research: { t: "Researched", c: "bg-chart-3/15 text-[#6fd3ad]" },
};

export function SourceBadge({ kind }: { kind: keyof typeof SOURCE }) {
  const s = SOURCE[kind];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide uppercase",
        s.c,
      )}
    >
      {s.t}
    </span>
  );
}

export const APPROVAL: Record<ApprovalStatus, { t: string; c: string }> = {
  draft: { t: "Draft", c: "bg-muted text-muted-foreground" },
  awaiting_review: { t: "Awaiting your review", c: "bg-status-warning/10 text-status-warning" },
  approved: { t: "Approved", c: "bg-primary/15 text-primary" },
  rejected: { t: "Rejected", c: "bg-status-critical/10 text-chart-negative" },
  completed: { t: "Completed", c: "bg-status-good/10 text-text-good" },
  failed: { t: "Failed", c: "bg-status-critical/10 text-chart-negative" },
};

export function ApprovalBadge({ status }: { status: ApprovalStatus }) {
  const s = APPROVAL[status];
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center rounded-md px-2 py-0.5 text-xs font-medium",
        s.c,
      )}
    >
      {s.t}
    </span>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: "info" | "warning" | "error" | "success";
  title?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}) {
  const map = {
    info: { c: "border-border bg-muted/50", i: Info, ic: "text-muted-foreground" },
    warning: {
      c: "border-status-warning/40 bg-status-warning/5",
      i: AlertTriangle,
      ic: "text-status-warning",
    },
    error: {
      c: "border-status-critical/50 bg-status-critical/5",
      i: ShieldAlert,
      ic: "text-chart-negative",
    },
    success: { c: "border-status-good/40 bg-status-good/5", i: CheckCircle2, ic: "text-text-good" },
  }[tone];
  const Icon = map.i;
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className={cn("flex gap-3 rounded-xl border p-3.5 text-sm", map.c, className)}
    >
      <Icon className={cn("mt-0.5 size-4 shrink-0", map.ic)} aria-hidden />
      <div className="flex min-w-0 flex-col gap-1">
        {title ? <div className="font-medium">{title}</div> : null}
        {children ? <div className="text-muted-foreground">{children}</div> : null}
      </div>
    </div>
  );
}

/** Which AI / research mode is active — shown wherever results are produced. */
export function ModeStrip({ status }: { status: StateView["status"] | undefined }) {
  if (!status) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
          status.ai.enabled ? "border-primary/40 text-primary" : "text-muted-foreground",
        )}
      >
        <Sparkles className="size-3.5" aria-hidden />
        {status.ai.enabled ? `AI: ${status.ai.model}` : "AI not configured — deterministic mode"}
      </span>
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
          status.research.mode === "live"
            ? "border-primary/40 text-primary"
            : "text-muted-foreground",
        )}
      >
        Research: {status.research.mode === "live" ? "live web search" : "illustrative assumptions"}
      </span>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card p-6 text-sm text-muted-foreground">
      <span
        className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent"
        aria-hidden
      />
      {label}
    </div>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "flex flex-col gap-4 rounded-xl border bg-card p-4 shadow-sm sm:p-5",
        className,
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="text-base font-semibold">{title}</h2>
          {description ? (
            <p className="text-sm text-pretty text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "good" | "bad" | "warn";
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-lg border bg-background/40 p-3">
      <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
      <span
        className={cn(
          "tabular truncate text-lg leading-tight font-semibold",
          tone === "bad" && "text-chart-negative",
          tone === "good" && "text-text-good",
          tone === "warn" && "text-status-warning",
        )}
      >
        {value}
      </span>
      {sub ? <span className="text-[11px] text-muted-foreground">{sub}</span> : null}
    </div>
  );
}

export const inputClass =
  "h-9 w-full rounded-md border bg-background/60 px-3 text-sm tabular shadow-xs outline-none placeholder:text-muted-foreground/60 focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";
