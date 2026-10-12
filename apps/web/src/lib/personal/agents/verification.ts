/**
 * Verification & Risk Agent: checks the inputs for gaps and inconsistencies, compares document
 * figures with the profile, and challenges optimistic assumptions. It does NOT verify anything
 * against a bank, a government database or a document issuer — these are consistency checks on
 * the data FinPulse was given.
 */
import { formatINR } from "@/lib/format";

import type { PurchaseAnalysis } from "../finance/affordability";
import type { ScenarioResult } from "../finance/scenarios";
import type { ProfileValues, PurchaseRequest } from "../schemas";
import type { Assumption, Finding, ResolvedInputs } from "./types";

export type DocumentFact = {
  documentName: string;
  profileField: string;
  label: string;
  value: number;
};

export type VerificationInput = {
  profile: ProfileValues;
  request: PurchaseRequest;
  inputs: ResolvedInputs;
  analysis: PurchaseAnalysis;
  assumptions: Assumption[];
  documentFacts: DocumentFact[];
  researchLive: boolean;
};

export function verify(input: VerificationInput): Finding[] {
  const { profile: p, request: r, inputs, analysis: a } = input;
  const out: Finding[] = [];
  const add = (f: Omit<Finding, "id" | "agent">) =>
    out.push({ id: `f${out.length + 1}`, agent: "verification", ...f });
  const income = inputs.household.monthlyIncome;

  // Consistency of the supplied figures.
  if (inputs.household.monthlyExpenses + inputs.household.existingEmis > income) {
    add({
      severity: "critical",
      category: "inconsistent",
      message: "Expenses plus existing EMIs already exceed take-home income, before any new loan.",
      field: "monthlyExpenses",
      suggestion:
        "Re-check income and expenses; a household already in deficit should not add debt.",
    });
  }
  if (inputs.household.monthlyExpenses < income * 0.1) {
    add({
      severity: "warning",
      category: "inconsistent",
      message: `Living expenses of ${formatINR(inputs.household.monthlyExpenses)} are under 10% of income, which is unusually low.`,
      field: "monthlyExpenses",
      suggestion:
        "Make sure rent, groceries, utilities, school fees and transport are all included.",
    });
  }
  if (p.investments !== null && p.investments > 0) {
    add({
      severity: "info",
      category: "assumption",
      message: `Investments of ${formatINR(p.investments)} were not counted as liquid savings.`,
      suggestion:
        "Selling investments may take time, incur tax or crystallise losses; FinPulse leaves them out of the emergency buffer.",
    });
  }

  // Document cross-checks.
  for (const fact of input.documentFacts) {
    const profileValue = p[fact.profileField as keyof ProfileValues];
    if (typeof profileValue !== "number") continue;
    const diff = Math.abs(fact.value - profileValue) / Math.max(1, profileValue);
    if (diff > 0.05) {
      add({
        severity: "warning",
        category: "document",
        message: `${fact.label} on "${fact.documentName}" is ${formatINR(fact.value)}, but your profile says ${formatINR(profileValue)} (${Math.round(diff * 100)}% different).`,
        field: fact.profileField,
        suggestion:
          "Confirm which figure is right on the Documents page. This analysis used the profile value.",
      });
    }
  }

  // Assumptions that are not the user's own.
  for (const as of input.assumptions) {
    if (as.basis === "illustrative" || as.basis === "default") {
      add({
        severity: "info",
        category: "assumption",
        message: `${as.field}: ${as.value} is ${as.basis === "illustrative" ? "an illustrative assumption" : "a default"}, not your figure.`,
        suggestion: as.note,
      });
    }
  }
  if (r.interestRate === null && !input.researchLive) {
    add({
      severity: "warning",
      category: "assumption",
      message: "The interest rate is an illustrative assumption (live research is not configured).",
      suggestion:
        "Get written quotes from at least three lenders and re-run the analysis with the actual rate.",
    });
  }

  // Challenges to optimistic assumptions.
  if (r.type === "house" && inputs.purchase.downPaymentPct < 20 && r.price > 3_000_000) {
    add({
      severity: "warning",
      category: "risk",
      message: `A ${inputs.purchase.downPaymentPct}% down payment may be below what lenders allow on a ${formatINR(r.price, { compact: true })} home.`,
      suggestion:
        "RBI guidance caps home-loan loan-to-value at 80% for ₹30–75 lakh and 75% above ₹75 lakh (general guideline; confirm with the lender).",
    });
  }
  if (p.incomeVariability === "variable") {
    add({
      severity: "warning",
      category: "risk",
      message: "Your income is variable, but the analysis uses a single monthly figure.",
      suggestion: "Use a conservative (low-month) income and keep a larger emergency buffer.",
    });
  }
  if ((p.dependents ?? 0) > 0 && (a.after.emergencyMonths ?? 99) < 6) {
    add({
      severity: "warning",
      category: "risk",
      message: `With ${p.dependents} dependent${p.dependents === 1 ? "" : "s"}, ${a.after.emergencyMonths?.toFixed(1)} months of emergency cover is thin.`,
      suggestion:
        "Consider term life and health insurance and a 6+ month buffer before committing.",
    });
  }
  const preferred = p.emergencyBufferMonths;
  if (
    preferred !== null &&
    a.after.emergencyMonths !== null &&
    a.after.emergencyMonths < preferred
  ) {
    add({
      severity: "warning",
      category: "risk",
      message: `Post-purchase emergency cover (${a.after.emergencyMonths.toFixed(1)} months) is below your preferred ${preferred} months.`,
      field: "emergencyBufferMonths",
    });
  }
  if (p.upcomingExpenses !== null && p.upcomingExpenses > Math.max(0, a.postPurchaseSavings)) {
    add({
      severity: "critical",
      category: "risk",
      message: `Planned expenses of ${formatINR(p.upcomingExpenses)} in the next year exceed the ${formatINR(a.postPurchaseSavings)} left after the purchase.`,
      field: "upcomingExpenses",
    });
  }
  if (r.monthlyOwnershipCost === null && (r.type === "house" || r.type === "car")) {
    add({
      severity: "warning",
      category: "missing",
      message: `No running costs were entered for the ${r.type}.`,
      field: "monthlyOwnershipCost",
      suggestion:
        r.type === "house"
          ? "Add maintenance/society charges and home insurance."
          : "Add fuel, insurance and servicing.",
    });
  }
  if (a.loanAmount > 0) {
    add({
      severity: "info",
      category: "risk",
      message:
        "Most retail loans in India are floating-rate: the EMI or tenure can rise when the lender's benchmark rate rises.",
      suggestion: "See the +1.5 percentage-point scenario.",
    });
  }

  return out;
}

/** Risk findings from the stress scenarios: every scenario that breaches a safety rule. */
export function riskFindings(scenarios: ScenarioResult[]): Finding[] {
  return scenarios
    .filter((s) => !s.isBaseline && s.label !== "comfortable")
    .map((s, i) => ({
      id: `r${i + 1}`,
      agent: "risk" as const,
      severity: s.label === "high_strain" ? ("warning" as const) : ("info" as const),
      category: "risk" as const,
      message:
        s.monthExhausted !== null
          ? `${s.params.name}: savings run out in month ${s.monthExhausted}.`
          : s.breaches.length
            ? `${s.params.name}: breaches ${s.breaches.join(", ").toLowerCase()}.`
            : `${s.params.name}: buffer becomes thin (${s.emergencyMonths?.toFixed(1) ?? "—"} months of cover).`,
    }));
}
