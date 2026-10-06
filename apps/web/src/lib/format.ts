/**
 * Display formatting for values that arrive from the API as decimal strings. Formatting only:
 * nothing here calculates a financial figure.
 */

export type Unit = "INR" | "ratio" | "days" | "months" | "score" | "count";
type Num = string | number | null | undefined;

export function toNumber(value: Num): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

const DASH = "—";
const MINUS = "−";

function sign(n: number, text: string, signed: boolean): string {
  if (n < 0) return `${MINUS}${text}`;
  return signed && n > 0 ? `+${text}` : text;
}

const inrFull = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹6,89,747 (Indian digit grouping), or compact: ₹6.9L, ₹1.2Cr, ₹48K. */
export function formatINR(value: Num, opts: { compact?: boolean; signed?: boolean } = {}): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const abs = Math.abs(n);
  let text: string;
  if (opts.compact && abs >= 1e7) text = `₹${trim(abs / 1e7)}Cr`;
  else if (opts.compact && abs >= 1e5) text = `₹${trim(abs / 1e5)}L`;
  else if (opts.compact && abs >= 1e3) text = `₹${trim(abs / 1e3)}K`;
  else text = `₹${inrFull.format(Math.round(abs))}`;
  return sign(n, text, opts.signed ?? false);
}

function trim(n: number): string {
  return n >= 100 ? Math.round(n).toString() : n.toFixed(1).replace(/\.0$/, "");
}

/** A ratio (0.2 = 20%) as a percentage. */
export function formatPercent(
  value: Num,
  opts: { digits?: number; signed?: boolean } = {},
): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const text = `${Math.abs(n * 100).toFixed(opts.digits ?? 1)}%`;
  return sign(n, text, opts.signed ?? false);
}

export function formatNumber(value: Num, digits = 1, signed = false): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  return sign(n, Math.abs(n).toFixed(digits), signed);
}

/** Ratios that are multiples rather than shares (liquidity): 0.43×. */
export function formatMultiple(value: Num): string {
  const n = toNumber(value);
  return n === null ? DASH : `${n.toFixed(2)}×`;
}

// Ratios better read as multiples than percentages.
const MULTIPLE_METRICS = new Set(["liquidity.ratio"]);

export function formatMetric(
  value: Num,
  unit: string,
  opts: { code?: string; compact?: boolean; signed?: boolean } = {},
): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  switch (unit as Unit) {
    case "INR":
      return formatINR(n, opts);
    case "ratio":
      return opts.code && MULTIPLE_METRICS.has(opts.code)
        ? formatMultiple(n)
        : formatPercent(n, { signed: opts.signed });
    case "days":
      return `${formatNumber(n, 1, opts.signed)} days`;
    case "months":
      return `${formatNumber(n, 1, opts.signed)} mo`;
    case "score":
      return formatNumber(n, 1, opts.signed);
    case "count":
      return formatNumber(n, 0, opts.signed);
    default:
      return formatNumber(n, 2, opts.signed);
  }
}

/** Short value for chart axes. */
export function formatAxis(value: number, unit: string, code?: string): string {
  if (unit === "INR") return formatINR(value, { compact: true });
  if (unit === "ratio")
    return code && MULTIPLE_METRICS.has(code)
      ? `${value.toFixed(1)}×`
      : `${Math.round(value * 100)}%`;
  return Number.isInteger(value) ? value.toString() : value.toFixed(1);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parts(iso: string): [number, number, number] {
  const [y = 1970, m = 1, d = 1] = iso.slice(0, 10).split("-").map(Number);
  return [y, m, d];
}

/** 30 Sep 2026 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const [y, m, d] = parts(iso);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** Sep 2026 */
export function formatMonth(iso: string): string {
  const [y, m] = parts(iso);
  return `${MONTHS[m - 1]} ${y}`;
}

/** Sep ’26 — for chart axes */
export function formatMonthShort(iso: string): string {
  const [y, m] = parts(iso);
  return `${MONTHS[m - 1]} ’${String(y).slice(2)}`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${formatDate(iso)} ${d.toISOString().slice(11, 19)} UTC`;
}

export function titleCase(text: string): string {
  return text.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
