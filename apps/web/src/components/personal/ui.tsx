"use client";

/**
 * FinPulse's design system for the personal product. Light, quiet surfaces; dark type; one
 * emerald accent; amber and red only for real warnings. Every page reuses these so spacing, type
 * and interaction patterns stay consistent.
 */
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Info,
  OctagonAlert,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { AffordabilityLabel, CheckStatus } from "@/lib/personal/finance/affordability";
import type { StateView } from "@/lib/personal/client";
import type { FieldSourceKind } from "@/lib/personal/schemas";
import type { ApprovalStatus } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- assessment & status

export type Tone = "good" | "warn" | "bad" | "neutral";

export const ASSESSMENT: Record<
  AffordabilityLabel,
  { text: string; short: string; tone: Tone; icon: typeof Info }
> = {
  comfortable: {
    text: "Comfortable under the stated assumptions",
    short: "Comfortable",
    tone: "good",
    icon: CheckCircle2,
  },
  manageable_limited_buffer: {
    text: "Potentially manageable, but with limited buffer",
    short: "Limited buffer",
    tone: "warn",
    icon: AlertTriangle,
  },
  high_strain: {
    text: "High financial strain under the stated assumptions",
    short: "High strain",
    tone: "bad",
    icon: OctagonAlert,
  },
  insufficient_information: {
    text: "Insufficient information for a reliable assessment",
    short: "Need more info",
    tone: "neutral",
    icon: Info,
  },
};

export const TONE_TEXT: Record<Tone, string> = {
  good: "text-brand-700",
  warn: "text-caution-text",
  bad: "text-danger-text",
  neutral: "text-ink-500",
};
export const TONE_SOFT: Record<Tone, string> = {
  good: "bg-brand-50 text-brand-700",
  warn: "bg-caution-50 text-caution-text",
  bad: "bg-danger-50 text-danger-text",
  neutral: "bg-surface-sunken text-ink-500",
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
        "inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap",
        TONE_SOFT[a.tone],
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
    pass: { t: "Pass", tone: "good", i: CheckCircle2 },
    warn: { t: "Watch", tone: "warn", i: AlertTriangle },
    fail: { t: "Breach", tone: "bad", i: OctagonAlert },
  } as const;
  const m = map[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
        TONE_SOFT[m.tone],
      )}
    >
      <m.i className="size-3" aria-hidden /> {m.t}
    </span>
  );
}

const SOURCE: Record<
  FieldSourceKind | "illustrative" | "default" | "research",
  { t: string; c: string }
> = {
  user: { t: "You entered", c: "bg-accent text-accent-foreground" },
  demo: { t: "Demo data", c: "bg-[#eaf1fb] text-[#1d5aa6]" },
  document: { t: "From document", c: "bg-[#e9f6f0] text-[#0b6e4c]" },
  derived: { t: "Calculated", c: "bg-surface-sunken text-ink-500" },
  illustrative: { t: "Estimate", c: "bg-caution-50 text-caution-text" },
  default: { t: "Assumed", c: "bg-caution-50 text-caution-text" },
  research: { t: "Researched", c: "bg-[#e9f6f0] text-[#0b6e4c]" },
};

export function SourceBadge({ kind }: { kind: keyof typeof SOURCE }) {
  const s = SOURCE[kind];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10.5px] font-medium",
        s.c,
      )}
    >
      {s.t}
    </span>
  );
}

export const APPROVAL: Record<ApprovalStatus, { t: string; tone: Tone }> = {
  draft: { t: "Draft", tone: "neutral" },
  awaiting_review: { t: "Waiting for your review", tone: "warn" },
  approved: { t: "Approved", tone: "good" },
  rejected: { t: "Rejected", tone: "bad" },
  completed: { t: "Completed", tone: "good" },
  failed: { t: "Failed", tone: "bad" },
};

export function ApprovalBadge({ status }: { status: ApprovalStatus }) {
  const s = APPROVAL[status];
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONE_SOFT[s.tone],
      )}
    >
      {s.t}
    </span>
  );
}

// ---------------------------------------------------------------- feedback

export function Notice({
  tone = "info",
  title,
  children,
  className,
  action,
}: {
  tone?: "info" | "warning" | "error" | "success";
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  const map = {
    info: { c: "bg-surface-sunken", i: Info, ic: "text-ink-500" },
    warning: { c: "bg-caution-50", i: AlertTriangle, ic: "text-caution-text" },
    error: { c: "bg-danger-50", i: ShieldAlert, ic: "text-danger-text" },
    success: { c: "bg-brand-50", i: CheckCircle2, ic: "text-brand-700" },
  }[tone];
  const Icon = map.i;
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className={cn("flex gap-3 rounded-xl p-3.5 text-sm", map.c, className)}
    >
      <Icon className={cn("mt-0.5 size-4 shrink-0", map.ic)} aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        {title ? <div className="font-medium text-foreground">{title}</div> : null}
        {children ? <div className="text-pretty text-ink-500">{children}</div> : null}
      </div>
      {action ? <div className="shrink-0 self-center">{action}</div> : null}
    </div>
  );
}

/** Which AI / research mode is active, stated quietly. */
export function ModeStrip({ status }: { status: StateView["status"] | undefined }) {
  if (!status) return null;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-500">
      <span className="inline-flex items-center gap-1">
        <Sparkles className={cn("size-3.5", status.ai.enabled && "text-brand-700")} aria-hidden />
        {status.ai.enabled ? "AI assistant on" : "AI off — calculations still work"}
      </span>
      <span aria-hidden>·</span>
      <span>
        {status.research.mode === "live"
          ? "Live rate research"
          : "Rates are illustrative estimates"}
      </span>
    </p>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className="h-7 w-56 animate-pulse rounded-md bg-surface-sunken" />
      <div className="h-4 w-80 max-w-full animate-pulse rounded bg-surface-sunken" />
      <div className="mt-2 grid grid-cols-2 gap-4 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-xl bg-surface-sunken" />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  icon: Icon = Info,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: typeof Info;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-10 text-center">
      <span className="flex size-11 items-center justify-center rounded-xl bg-surface-sunken text-ink-500">
        <Icon className="size-5" aria-hidden />
      </span>
      <p className="text-[15px] font-semibold">{title}</p>
      {children ? <div className="max-w-md text-sm text-ink-500">{children}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------- layout

export function PageTitle({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex min-w-0 flex-col gap-1">
        {eyebrow ? <div className="text-[13px] font-semibold text-brand-700">{eyebrow}</div> : null}
        <h1 className="text-[26px] leading-tight font-extrabold tracking-tight text-balance sm:text-[30px]">
          {title}
        </h1>
        {description ? (
          <p className="max-w-2xl text-[14.5px] text-pretty text-ink-500">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** A titled block. `card` gives it a white surface with a hairline border; otherwise it's flat. */
export function Section({
  title,
  description,
  actions,
  children,
  className,
  card = true,
  id,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  card?: boolean;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={cn(
        "flex scroll-mt-20 flex-col gap-4",
        card && "rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6",
        className,
      )}
    >
      {title || actions ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-col gap-1">
            {title ? <h2 className="text-[17px] font-bold">{title}</h2> : null}
            {description ? <p className="text-sm text-pretty text-ink-500">{description}</p> : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
          ) : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** A financial figure: small grey label, large value, optional caption. No box. */
export function Stat({
  label,
  value,
  sub,
  tone,
  size = "md",
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "good" | "warn" | "bad";
  size?: "md" | "lg";
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-xs text-ink-500">{label}</span>
      <span
        className={cn(
          "tabular truncate font-display font-bold tracking-tight",
          size === "lg" ? "text-2xl sm:text-[28px]" : "text-lg",
          tone && TONE_TEXT[tone],
        )}
      >
        {value}
      </span>
      {sub ? <span className="text-xs text-ink-500">{sub}</span> : null}
    </div>
  );
}

/** Label–value rows separated by hairlines: the clearest way to read a few figures. */
export function StatRows({
  rows,
}: {
  rows: {
    label: ReactNode;
    value: ReactNode;
    hint?: ReactNode;
    tone?: "good" | "warn" | "bad";
    strong?: boolean;
  }[];
}) {
  return (
    <dl className="flex flex-col divide-y">
      {rows.map((r, i) => (
        <div key={i} className="flex items-baseline justify-between gap-4 py-2.5">
          <dt className="min-w-0 text-sm text-ink-500">
            {r.label}
            {r.hint ? <span className="block text-xs">{r.hint}</span> : null}
          </dt>
          <dd
            className={cn(
              "tabular shrink-0 text-right text-sm",
              r.strong ? "text-base font-semibold" : "font-medium",
              r.tone && TONE_TEXT[r.tone],
            )}
          >
            {r.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** Progressive disclosure: a quiet row that expands to the detail. */
export function Disclosure({
  title,
  hint,
  children,
  defaultOpen = false,
  className,
}: {
  title: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  return (
    <details
      className={cn("group rounded-2xl border border-line bg-surface shadow-xs", className)}
      open={defaultOpen}
    >
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 rounded-2xl px-4 py-3 select-none hover:bg-surface-sunken/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 flex-col">
          <span className="text-sm font-medium">{title}</span>
          {hint ? <span className="text-xs text-ink-500">{hint}</span> : null}
        </span>
        <ChevronDown
          className="size-4 shrink-0 text-ink-500 transition group-open:rotate-180"
          aria-hidden
        />
      </summary>
      <div className="border-t px-4 py-4">{children}</div>
    </details>
  );
}

// ---------------------------------------------------------------- dialog

/** Accessible confirmation dialog (native <dialog>: focus trap, Esc to close). */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "default",
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto w-[min(92vw,440px)] rounded-2xl border bg-card p-0 text-foreground shadow-xl backdrop:bg-black/40"
    >
      <div className="flex flex-col gap-3 p-5">
        <h2 id={titleId} className="text-lg font-semibold">
          {title}
        </h2>
        {children ? <div className="text-sm text-pretty text-ink-500">{children}</div> : null}
        <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            onClick={onConfirm}
            disabled={busy}
            className={cn(tone === "danger" && "bg-destructive text-white hover:bg-destructive/90")}
          >
            {busy ? "Working…" : confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}

export const inputClass =
  "h-11 w-full rounded-xl border border-input bg-background px-3.5 text-[15px] tabular outline-none transition placeholder:text-ink-500/70 hover:border-foreground/25 focus-visible:border-primary focus-visible:ring-3 focus-visible:ring-primary/15 disabled:opacity-60";
