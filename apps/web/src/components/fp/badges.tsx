import type { LucideIcon } from "lucide-react";

import {
  STATEMENT_TYPES,
  TONE_CLASSES,
  TONE_ICON,
  bandTone,
  label,
  riskTone,
  severityTone,
  stanceTone,
  stressRiskTone,
  type StatementType,
  type Tone,
} from "@/lib/presentation";
import { cn } from "@/lib/utils";

/** A status chip: icon + label + tone. Colour never carries the meaning alone. */
export function ToneBadge({
  tone,
  children,
  icon,
  className,
  size = "sm",
}: {
  tone: Tone;
  children: React.ReactNode;
  icon?: LucideIcon | null;
  className?: string;
  size?: "sm" | "md";
}) {
  const Icon = icon === null ? null : (icon ?? TONE_ICON[tone]);
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 self-start rounded-md border font-medium whitespace-nowrap",
        size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm",
        TONE_CLASSES[tone].badge,
        className,
      )}
    >
      {Icon ? (
        <Icon
          className={cn(size === "sm" ? "size-3" : "size-3.5", tone !== "neutral" && "opacity-90")}
          aria-hidden
          style={tone === "neutral" ? undefined : { color: `var(--status-${toneVar(tone)})` }}
        />
      ) : null}
      {children}
    </span>
  );
}

function toneVar(tone: Tone): string {
  return tone === "neutral" ? "info" : tone;
}

export function SeverityBadge({ severity, size }: { severity: string; size?: "sm" | "md" }) {
  return (
    <ToneBadge tone={severityTone(severity)} size={size}>
      {label(severity)}
    </ToneBadge>
  );
}

export function RiskBadge({
  level,
  size,
  prefix,
}: {
  level: string;
  size?: "sm" | "md";
  prefix?: string;
}) {
  return (
    <ToneBadge tone={riskTone(level)} size={size}>
      {prefix ? `${prefix} ` : ""}
      {label(level)}
    </ToneBadge>
  );
}

export function StressRiskBadge({ level, size }: { level: string; size?: "sm" | "md" }) {
  return (
    <ToneBadge tone={stressRiskTone(level)} size={size}>
      {label(level)}
    </ToneBadge>
  );
}

export function StanceBadge({ stance }: { stance: string }) {
  return <ToneBadge tone={stanceTone(stance)}>{label(stance)} risk</ToneBadge>;
}

export function BandBadge({ band, size }: { band: string | null | undefined; size?: "sm" | "md" }) {
  if (!band) return null;
  return (
    <ToneBadge tone={bandTone(band)} size={size} icon={null}>
      {band}
    </ToneBadge>
  );
}

export function StatementTypeBadge({ type }: { type: string }) {
  const meta = STATEMENT_TYPES[type as StatementType];
  if (!meta) return null;
  const Icon = meta.icon;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold tracking-wide whitespace-nowrap text-foreground uppercase",
        meta.className,
      )}
    >
      <Icon className="size-3" aria-hidden />
      {meta.label}
    </span>
  );
}

export function SyntheticBadge() {
  return (
    <span className="inline-flex items-center rounded-md border border-dashed px-1.5 py-0.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
      Synthetic data
    </span>
  );
}
