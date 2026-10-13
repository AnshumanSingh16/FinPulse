"use client";

/**
 * FinPulse UI kit, part 2: agent identity, tabs, meters, chips and deltas. Everything uses the
 * design tokens in globals.css.
 */
import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  Calculator,
  Compass,
  Crosshair,
  ListChecks,
  MessagesSquare,
  Minus,
  Search,
  ShieldHalf,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useRef, type KeyboardEvent, type ReactNode } from "react";

import type { AgentName } from "@/lib/personal/agents/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- agent identity

export const AGENT_META: Record<AgentName, { label: string; role: string; icon: LucideIcon }> = {
  orchestrator: { label: "Orchestrator", role: "Plans and coordinates the work", icon: Workflow },
  planner: { label: "Planner", role: "Understands the goal and what's needed", icon: Compass },
  research: { label: "Research", role: "Finds financing options and sources", icon: Search },
  analysis: { label: "Analysis", role: "Runs the financial calculations", icon: Calculator },
  risk: { label: "Risk", role: "Stress-tests the plan", icon: ShieldHalf },
  verification: { label: "Verification", role: "Checks inputs and assumptions", icon: BadgeCheck },
  action: { label: "Action", role: "Prepares next steps for approval", icon: ListChecks },
  copilot: { label: "Copilot", role: "Answers your questions with tools", icon: MessagesSquare },
  strategist: {
    label: "Strategist",
    role: "Searches for changes that make the plan more likely to work",
    icon: Crosshair,
  },
};

export function AgentGlyph({
  agent,
  size = "md",
  className,
}: {
  agent: AgentName;
  size?: "sm" | "md";
  className?: string;
}) {
  const Icon = AGENT_META[agent].icon;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg bg-agent-50 text-agent-700",
        size === "sm" ? "size-6" : "size-8",
        className,
      )}
      title={`${AGENT_META[agent].label} agent`}
      aria-hidden
    >
      <Icon className={size === "sm" ? "size-3.5" : "size-4"} />
    </span>
  );
}

/** FinPulse's mark: a pulse line. It pulses only while real work is running. */
export function PulseMark({
  active = false,
  size = "md",
}: {
  active?: boolean;
  size?: "sm" | "md" | "lg";
}) {
  const dim = size === "lg" ? "size-11" : size === "sm" ? "size-7" : "size-9";
  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center rounded-xl bg-ink-900 text-white",
        dim,
        active && "fp-pulse",
      )}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" className={size === "lg" ? "size-6" : "size-[18px]"} fill="none">
        <path
          d="M2 12h4l2.5-6 4 12 3-8 1.5 2H22"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="20.5" cy="12" r="1.6" fill="var(--brand-500)" />
      </svg>
    </span>
  );
}

// ---------------------------------------------------------------- tabs

export type TabItem = { id: string; label: string; badge?: ReactNode };

/** Accessible tabs (arrow keys move between tabs). Render panels with `id={`panel-${id}`}`. */
export function Tabs({
  items,
  value,
  onChange,
  label,
  className,
  size = "md",
}: {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  className?: string;
  size?: "sm" | "md";
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    const dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = (i + dir + items.length) % items.length;
    onChange(items[next]!.id);
    refs.current[next]?.focus();
  };
  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn(
        "flex [scrollbar-width:none] gap-1 overflow-x-auto rounded-xl bg-surface-sunken p-1",
        className,
      )}
    >
      {items.map((t, i) => {
        const on = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            type="button"
            id={`tab-${t.id}`}
            aria-selected={on}
            aria-controls={`panel-${t.id}`}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(t.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              size === "sm" ? "h-8 px-3 text-[13px]" : "h-9 px-3.5 text-sm",
              on ? "bg-surface text-ink-900 shadow-xs" : "text-ink-500 hover:text-ink-900",
            )}
          >
            {t.label}
            {t.badge}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- chips, deltas

export function Chip({
  selected = false,
  onClick,
  children,
  icon: Icon,
  className,
}: {
  selected?: boolean;
  onClick?: () => void;
  children: ReactNode;
  icon?: LucideIcon;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3.5 text-[13px] transition-colors duration-150",
        selected
          ? "border-brand-600 bg-brand-50 font-medium text-brand-700"
          : "border-line bg-surface text-ink-700 hover:border-line-strong hover:bg-surface-sunken",
        className,
      )}
    >
      {Icon ? <Icon className="size-3.5" aria-hidden /> : null}
      {children}
    </button>
  );
}

/** A signed change. `goodWhen` says which direction is good for this figure. */
export function Delta({
  value,
  format,
  goodWhen = "up",
  suffix,
}: {
  value: number;
  format: (n: number) => string;
  goodWhen?: "up" | "down";
  suffix?: string;
}) {
  if (Math.abs(value) < 0.5) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-ink-500">
        <Minus className="size-3" aria-hidden /> no change
      </span>
    );
  }
  const up = value > 0;
  const good = goodWhen === "up" ? up : !up;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-0.5 text-xs font-medium whitespace-nowrap",
        good ? "text-brand-700" : "text-caution-text",
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {format(Math.abs(value))}
      {suffix ? <span className="font-normal text-ink-500">&nbsp;{suffix}</span> : null}
    </span>
  );
}

// ---------------------------------------------------------------- meter

export type MeterZone = { to: number; tone: "bad" | "warn" | "good" };

const ZONE_BG = { bad: "bg-danger-500/25", warn: "bg-caution-500/30", good: "bg-brand-500/25" };
const ZONE_FILL = { bad: "bg-danger-500", warn: "bg-caution-500", good: "bg-brand-600" };

/**
 * A value against explicit thresholds: tinted zones from the rule thresholds, a filled bar to the
 * value and labelled markers. Thresholds come from the rules engine, never from the UI.
 */
export function Meter({
  value,
  max,
  zones,
  markers = [],
  label,
  valueText,
}: {
  value: number;
  max: number;
  zones: MeterZone[];
  markers?: { at: number; label: string }[];
  label: string;
  valueText: string;
}) {
  const pct = (n: number) => `${Math.max(0, Math.min(100, (n / max) * 100))}%`;
  const zone = zones.find((z) => value <= z.to) ?? zones[zones.length - 1]!;
  const starts = zones.map((_, i) => (i === 0 ? 0 : zones[i - 1]!.to));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={Math.round(value * 10) / 10}
      aria-valuetext={valueText}
      className="flex flex-col gap-1.5"
    >
      <div className="relative h-2.5 overflow-hidden rounded-full bg-surface-sunken">
        {zones.map((z, i) => {
          const left = pct(starts[i]!);
          const width = `calc(${pct(Math.min(z.to, max))} - ${left})`;
          return (
            <span
              key={i}
              className={cn("absolute inset-y-0", ZONE_BG[z.tone])}
              style={{ left, width }}
            />
          );
        })}
        <span
          className={cn("fp-grow absolute inset-y-0 left-0 rounded-full", ZONE_FILL[zone.tone])}
          style={{ width: pct(value) }}
        />
      </div>
      {markers.length ? (
        <div className="relative h-4 text-[11px] text-ink-500">
          {markers.map((m) => (
            <span
              key={m.label}
              className="tabular absolute -translate-x-1/2 whitespace-nowrap before:absolute before:-top-2 before:left-1/2 before:h-1.5 before:w-px before:bg-ink-400"
              style={{ left: pct(m.at) }}
            >
              {m.label}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function Kicker({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn("text-[12px] font-semibold tracking-wide text-ink-500 uppercase", className)}
    >
      {children}
    </div>
  );
}
