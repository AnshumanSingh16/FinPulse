/**
 * Parse Indian-style rupee amounts written by people: "₹75 lakh", "75L", "1.2 crore", "20 lakhs",
 * "₹15,00,000", "50k", "Rs. 2,00,000". Returns null when no amount is recognised.
 */
const UNIT: Record<string, number> = {
  k: 1e3,
  thousand: 1e3,
  l: 1e5,
  lac: 1e5,
  lacs: 1e5,
  lakh: 1e5,
  lakhs: 1e5,
  cr: 1e7,
  crore: 1e7,
  crores: 1e7,
};

const AMOUNT_RE =
  /(?:₹|rs\.?|inr)?\s*(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|l|crores?|cr)?\b/gi;

export type ParsedAmount = { value: number; text: string; index: number; hasCurrency: boolean; hasUnit: boolean };

export function findINRAmounts(text: string): ParsedAmount[] {
  const out: ParsedAmount[] = [];
  for (const m of text.matchAll(AMOUNT_RE)) {
    const raw = m[1];
    if (!raw) continue;
    const base = Number(raw.replace(/,/g, ""));
    if (!Number.isFinite(base)) continue;
    const unit = m[2]?.toLowerCase();
    const value = unit ? base * (UNIT[unit] ?? 1) : base;
    out.push({
      value: Math.round(value),
      text: m[0].trim(),
      index: m.index ?? 0,
      hasCurrency: /₹|rs|inr/i.test(m[0]),
      hasUnit: Boolean(unit),
    });
  }
  return out;
}

/** The first amount that looks like money (has ₹/Rs, a unit, or ≥ 1,000). */
export function parseINRAmount(text: string): number | null {
  const hit = findINRAmounts(text).find((a) => a.hasCurrency || a.hasUnit || a.value >= 1000);
  return hit ? hit.value : null;
}
