/**
 * How backend categories are shown: labels, status tones and icons. Presentation only — the
 * categories themselves (severities, risk levels, statement types) come from the API.
 */
import {
  AlertOctagon,
  AlertTriangle,
  BadgeCheck,
  Calculator,
  CircleDot,
  FileText,
  Lightbulb,
  Info,
  ShieldAlert,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export type Tone = "good" | "info" | "warning" | "serious" | "critical" | "neutral";

export const TONE_CLASSES: Record<Tone, { dot: string; badge: string; text: string; bar: string }> =
  {
    good: {
      dot: "bg-status-good",
      badge: "border-status-good/40 bg-status-good/10 text-text-good",
      text: "text-text-good",
      bar: "bg-status-good",
    },
    info: {
      dot: "bg-status-info",
      badge: "border-status-info/40 bg-status-info/10 text-foreground",
      text: "text-muted-foreground",
      bar: "bg-status-info",
    },
    warning: {
      dot: "bg-status-warning",
      badge: "border-status-warning/50 bg-status-warning/15 text-foreground",
      text: "text-foreground",
      bar: "bg-status-warning",
    },
    serious: {
      dot: "bg-status-serious",
      badge: "border-status-serious/50 bg-status-serious/15 text-foreground",
      text: "text-foreground",
      bar: "bg-status-serious",
    },
    critical: {
      dot: "bg-status-critical",
      badge: "border-status-critical/50 bg-status-critical/12 text-foreground",
      text: "text-status-critical",
      bar: "bg-status-critical",
    },
    neutral: {
      dot: "bg-muted-foreground/50",
      badge: "border-border bg-muted text-muted-foreground",
      text: "text-muted-foreground",
      bar: "bg-muted-foreground/40",
    },
  };

export const TONE_ICON: Record<Tone, LucideIcon> = {
  good: BadgeCheck,
  info: Info,
  warning: AlertTriangle,
  serious: AlertTriangle,
  critical: AlertOctagon,
  neutral: CircleDot,
};

/** Early-warning severity (low/medium/high/critical). */
export function severityTone(severity: string): Tone {
  return (
    ({ low: "info", medium: "warning", high: "serious", critical: "critical" } as const)[
      severity as "low"
    ] ?? "neutral"
  );
}

/** Early-warning risk level (none/low/medium/high/critical). */
export function riskTone(level: string): Tone {
  return level === "none" ? "good" : severityTone(level);
}

/** Stress-test risk level (low/elevated/high/critical). */
export function stressRiskTone(level: string): Tone {
  return (
    ({ low: "good", elevated: "warning", high: "serious", critical: "critical" } as const)[
      level as "low"
    ] ?? "neutral"
  );
}

/** Agent risk stance (low … severe). */
export function stanceTone(stance: string): Tone {
  return (
    (
      {
        low: "good",
        moderate: "info",
        elevated: "warning",
        high: "serious",
        severe: "critical",
      } as const
    )[stance as "low"] ?? "neutral"
  );
}

/** Passport band codes, best first. Unknown codes are neutral. */
export function bandTone(band: string | null | undefined): Tone {
  switch ((band ?? "").toLowerCase()) {
    case "strong":
    case "sound":
      return "good";
    case "watch":
      return "warning";
    case "strained":
      return "serious";
    case "critical":
      return "critical";
    default:
      return "neutral";
  }
}

export const LEVEL_LABEL: Record<string, string> = {
  none: "None",
  low: "Low",
  medium: "Medium",
  elevated: "Elevated",
  high: "High",
  critical: "Critical",
  moderate: "Moderate",
  severe: "Severe",
};

export const label = (code: string) =>
  LEVEL_LABEL[code] ?? code.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const STATEMENT_TYPES = {
  FACT: { label: "Fact", icon: FileText, className: "border-sky-500/40 bg-sky-500/10" },
  CALCULATED_METRIC: {
    label: "Calculated metric",
    icon: Calculator,
    className: "border-indigo-500/40 bg-indigo-500/10",
  },
  FORECAST: {
    label: "Forecast",
    icon: TrendingUp,
    className: "border-amber-500/40 bg-amber-500/10",
  },
  ASSUMPTION: {
    label: "Assumption",
    icon: ShieldAlert,
    className: "border-stone-500/40 bg-stone-500/10",
  },
  AI_INTERPRETATION: {
    label: "AI interpretation",
    icon: Lightbulb,
    className: "border-violet-500/40 bg-violet-500/10",
  },
} as const;

export type StatementType = keyof typeof STATEMENT_TYPES;

/** For metric deltas: is an increase good, bad, or neither? Presentation semantics only. */
const HIGHER_IS_BETTER: Record<string, boolean> = {
  "revenue.monthly": true,
  "revenue.growth": true,
  "cashflow.net_monthly": true,
  "cash.balance": true,
  "cash.runway": true,
  "buffer.months": true,
  "liquidity.ratio": true,
  "income.stability": true,
  "payments.consistency": true,
  "transactions.consistency": true,
  "cashflow.positive_months": true,
  "cashflow.net_margin": true,
  "expenses.monthly": false,
  "expenses.growth": false,
  "revenue.volatility": false,
  "receivables.outstanding": false,
  "receivables.days": false,
  "debt.outstanding": false,
  "debt.service_burden": false,
  "debt.leverage": false,
  "debt.new_loans_6m": false,
  "liquidity.overdraft_utilisation": false,
  "customers.concentration": false,
  "suppliers.concentration": false,
};

export function deltaTone(code: string, delta: number | null): Tone {
  if (delta === null || delta === 0 || !(code in HIGHER_IS_BETTER)) return "neutral";
  return delta > 0 === HIGHER_IS_BETTER[code] ? "good" : "critical";
}
