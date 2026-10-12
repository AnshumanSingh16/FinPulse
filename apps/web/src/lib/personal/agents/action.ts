/**
 * Financial Action Agent: turns the recommendation into concrete, reviewable next steps. It only
 * prepares; nothing here contacts a lender, moves money or submits anything. Items that would need
 * an external integration are marked so the UI can never offer to "execute" them.
 */
import { formatINR } from "@/lib/format";

import type { PurchaseAnalysis } from "../finance/affordability";
import type { ProfileValues, PurchaseRequest, PurchaseType } from "../schemas";
import type { ActionPlan, ChecklistItem } from "../store";
import type { Alternative, Finding } from "./types";

const DOCUMENTS: Record<PurchaseType, string[]> = {
  house: [
    "PAN card and Aadhaar (identity and address proof)",
    "Salary slips for the last 3 months",
    "Bank statements for the last 6 months (salary account)",
    "Form 16 / income-tax returns for the last 2 years",
    "Property documents: sale agreement, title deed chain, approved building plan",
    "Builder/seller NOC and allotment letter (for under-construction property)",
    "Proof of own contribution (down-payment receipts)",
  ],
  car: [
    "PAN card and Aadhaar",
    "Salary slips for the last 3 months",
    "Bank statements for the last 6 months",
    "Proforma invoice / quotation from the dealer",
  ],
  education: [
    "Admission letter and fee schedule from the institution",
    "Student and co-applicant KYC (PAN, Aadhaar)",
    "Co-applicant income proof (salary slips / ITR)",
    "Academic records (mark sheets, entrance scores)",
    "Collateral documents, if the loan amount requires them",
  ],
  business: [
    "PAN, Aadhaar and business registration (GST, Udyam)",
    "Business bank statements for the last 12 months",
    "ITR and audited financials for the last 2–3 years",
    "Business plan / project report",
  ],
  custom: [
    "PAN card and Aadhaar",
    "Salary slips for the last 3 months",
    "Bank statements for the last 6 months",
  ],
};

export type ActionPlanInput = {
  runId: string;
  request: PurchaseRequest;
  profile: ProfileValues;
  analysis: PurchaseAnalysis;
  alternatives: Alternative[];
  findings: Finding[];
  researchLive: boolean;
};

export type ActionPlanDraft = Omit<ActionPlan, "id" | "createdAt" | "status" | "statusHistory">;

export function buildActionPlan(input: ActionPlanInput): ActionPlanDraft {
  const { request: r, analysis: a, profile: p } = input;
  const items: ChecklistItem[] = [];
  const add = (
    item: Omit<ChecklistItem, "id" | "done" | "requiresIntegration"> & {
      requiresIntegration?: boolean;
    },
  ) =>
    items.push({
      id: `item_${items.length + 1}`,
      done: false,
      requiresIntegration: false,
      ...item,
    });

  const saveFirst = input.alternatives.find((x) => x.id === "save_first");
  const months = saveFirst?.figures.find((f) => f.unit === "months")?.value;
  const monthly = saveFirst?.figures.find((f) => f.label.startsWith("Monthly"))?.value;
  const target = saveFirst?.figures.find((f) => f.label.startsWith("Additional"))?.value;
  const savingsPlan =
    saveFirst && months !== undefined && monthly !== undefined && target !== undefined
      ? {
          targetAmount: target,
          monthlySaving: monthly,
          months,
          rationale: saveFirst.description,
        }
      : null;

  if (savingsPlan) {
    add({
      category: "savings",
      title: `Build the buffer: save ${formatINR(savingsPlan.monthlySaving)}/month for ${savingsPlan.months} months`,
      detail: savingsPlan.rationale,
    });
  } else {
    add({
      category: "savings",
      title: "Keep the post-purchase emergency fund separate",
      detail: `Ring-fence the ${formatINR(a.postPurchaseSavings)} left after the purchase in a liquid account; don't spend it on furnishing or upgrades.`,
    });
  }
  if (a.loanAmount > 0) {
    add({
      category: "research",
      title: "Get written loan quotes from at least three lenders",
      detail: `Compare the rate, processing fee, prepayment terms and whether the rate is floating. ${input.researchLive ? "The research sources are starting points." : "The rates used so far are illustrative."}`,
    });
    add({
      category: "research",
      title: "Re-run this analysis with the quoted rate",
      detail:
        "Replace the assumed rate with the lowest written quote and confirm the result still holds.",
    });
    add({
      category: "application",
      title: "Check your credit report before applying",
      detail:
        "Download your free annual credit report and fix any errors; multiple hard enquiries in a short time can lower your score.",
    });
  }
  if (r.type === "house") {
    add({
      category: "research",
      title: "Have a lawyer verify the property title",
      detail:
        "Title chain, encumbrance certificate, approvals and (for new builds) RERA registration.",
    });
  }
  if ((p.dependents ?? 0) > 0 && a.loanAmount > 0) {
    add({
      category: "protection",
      title: "Review term life and health cover",
      detail: `Cover should at least clear the ${formatINR(a.loanAmount)} loan so dependents are not left with it.`,
    });
  }
  for (const f of input.findings.filter(
    (x) => x.category === "missing" || x.category === "document",
  )) {
    add({ category: "documents", title: `Resolve: ${f.message}`, detail: f.suggestion ?? "" });
  }
  add({
    category: "documents",
    title: "Gather the application documents",
    detail: "See the document list below. Lenders' requirements vary.",
  });
  if (a.loanAmount > 0) {
    add({
      category: "application",
      title: "Submit the loan application",
      detail:
        "FinPulse cannot submit applications: no lender integration is configured. Use the draft answers below on the lender's own form.",
      requiresIntegration: true,
    });
  }

  const draftAnswers: ActionPlan["draftAnswers"] = [];
  const answer = (question: string, value: number | null, source: string) => {
    if (value !== null) draftAnswers.push({ question, answer: formatINR(value), source });
  };
  answer("Net monthly income", p.monthlyIncome, "Financial profile");
  answer("Existing monthly EMIs", p.existingEmis, "Financial profile");
  answer("Loan amount requested", a.loanAmount || null, "FinPulse calculation");
  answer("Own contribution (down payment)", a.downPayment || null, "FinPulse calculation");
  draftAnswers.push({
    question: "Purpose of loan",
    answer: r.label,
    source: "Your purchase details",
  });

  return {
    runId: input.runId,
    title: `Next steps: ${r.label}`,
    items,
    savingsPlan,
    draftAnswers,
    documentsNeeded: a.loanAmount > 0 ? DOCUMENTS[r.type] : [],
  };
}
