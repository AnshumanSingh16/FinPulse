/**
 * Understanding a goal written in plain English: "I want to buy a ₹75 lakh house with 30% down
 * over 20 years". Rule-based and deterministic, so it behaves the same with or without AI; it
 * only extracts what the text actually says and leaves everything else unknown.
 */
import { findINRAmounts, inrWords } from "./finance/parse-inr";
import type { PurchaseType } from "./schemas";

export type GoalInterpretation = {
  type: PurchaseType | null;
  price: number | null;
  downPaymentPct: number | null;
  tenureMonths: number | null;
  interestRate: number | null;
  label: string | null;
  /** What was understood, in words, for the UI and the audit trail. */
  understood: string[];
  /** What the text did not say and must still be asked or assumed. */
  unknown: string[];
};

const NOUN: Record<PurchaseType, string> = {
  house: "house",
  car: "car",
  education: "education",
  business: "business",
  custom: "purchase",
};

export function detectPurchaseType(text: string): PurchaseType | null {
  const t = text.toLowerCase();
  if (/\b(house|home|flat|apartment|villa|property|plot|\d?bhk)\b/.test(t)) return "house";
  if (/\b(car|suv|sedan|hatchback|vehicle|bike|scooter|ev)\b/.test(t)) return "car";
  if (/\b(mba|education|college|degree|course|masters|ms|university|study|studies|fees)\b/.test(t))
    return "education";
  if (/\b(business|shop|startup|franchise|store|cafe|restaurant)\b/.test(t)) return "business";
  return null;
}

export function interpretGoal(text: string): GoalInterpretation {
  const t = text.toLowerCase();
  const type = detectPurchaseType(text);
  // The price is the first money-looking amount that is not part of "N% down" or a rate.
  const price =
    findINRAmounts(text).find(
      (a) => (a.hasCurrency || a.hasUnit || a.value >= 10_000) && !/%/.test(a.text),
    )?.value ?? null;
  const dp = t.match(/(\d{1,3}(?:\.\d+)?)\s*%\s*(?:down|down ?payment|upfront)/);
  const tenureYears = t.match(/(?:for|over)\s+(\d{1,2})\s*(?:years?|yrs?)/);
  const tenureMonths = t.match(/(?:for|over)\s+(\d{1,3})\s*months?/);
  const rate = t.match(/(?:at|@)\s*(\d{1,2}(?:\.\d+)?)\s*%/);

  const out: GoalInterpretation = {
    type,
    price,
    downPaymentPct: dp ? Math.min(100, Number(dp[1])) : null,
    tenureMonths: tenureYears
      ? Number(tenureYears[1]) * 12
      : tenureMonths
        ? Number(tenureMonths[1])
        : null,
    interestRate: rate ? Number(rate[1]) : null,
    label: price !== null ? `${inrWords(price)} ${NOUN[type ?? "custom"]}` : null,
    understood: [],
    unknown: [],
  };
  if (type) out.understood.push(`Purchase type: ${NOUN[type]}`);
  else out.unknown.push("what you want to buy");
  if (price !== null) out.understood.push(`Price: ${inrWords(price)}`);
  else out.unknown.push("the price");
  if (out.downPaymentPct !== null) out.understood.push(`Down payment: ${out.downPaymentPct}%`);
  if (out.tenureMonths !== null) out.understood.push(`Tenure: ${out.tenureMonths / 12} years`);
  if (out.interestRate !== null) out.understood.push(`Interest rate: ${out.interestRate}%`);
  return out;
}
