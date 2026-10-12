/**
 * Purchase affordability: combines the loan and health tools and classifies the result against
 * explicit, configurable rules. The rules are decision-support heuristics, not universal truths:
 * every check carries its threshold and an explanation of its limits.
 */
import { FinanceInputError, roundPaise } from "./errors";
import {
  debtToIncomeRatio,
  emergencyFundCoverageMonths,
  postPurchaseLiquidSavings,
  summariseCashFlow,
  totalUpfrontCost,
  type CashFlowSummary,
} from "./health";
import {
  calculateDownPayment,
  calculateLoanAmount,
  calculateTotalInterest,
  generateAmortizationSchedule,
  summariseByYear,
  type YearlyAmortization,
} from "./loan";

export type AffordabilityRules = {
  /** Debt repayments ÷ take-home income at or below this is comfortable. */
  dtiComfortableMax: number;
  /** Above this the debt load is classed as high strain. */
  dtiStretchMax: number;
  /** Months of essential outflows the post-purchase savings should cover. */
  emergencyComfortableMonths: number;
  emergencyMinimumMonths: number;
  /** Share of income left over each month (after EMI) for a comfortable buffer. */
  surplusComfortableShare: number;
};

export const DEFAULT_RULES: AffordabilityRules = {
  dtiComfortableMax: 0.35,
  dtiStretchMax: 0.5,
  emergencyComfortableMonths: 6,
  emergencyMinimumMonths: 3,
  surplusComfortableShare: 0.1,
};

export const RULE_NOTES = {
  dti: "Debt-to-income here is total EMIs ÷ monthly take-home pay (FOIR-style). Many Indian lenders cap FOIR somewhere around 40–60% depending on income and lender; FinPulse's thresholds are configurable heuristics, not a lender's rule.",
  emergency:
    "Emergency cover = liquid savings after the purchase ÷ (living expenses + all EMIs + other fixed obligations). 3–6 months is a common rule of thumb; people with variable income or dependents may want more.",
  surplus:
    "Monthly surplus = take-home income − living expenses − all EMIs − other obligations − ownership costs. A positive surplus is required; a 10% buffer is a heuristic for absorbing surprises.",
};

export type AffordabilityLabel =
  "comfortable" | "manageable_limited_buffer" | "high_strain" | "insufficient_information";

export const LABEL_TEXT: Record<AffordabilityLabel, string> = {
  comfortable: "Comfortable under the stated assumptions",
  manageable_limited_buffer: "Potentially manageable, but with limited buffer",
  high_strain: "High financial strain under the stated assumptions",
  insufficient_information: "Insufficient information for a reliable assessment",
};

export type CheckStatus = "pass" | "warn" | "fail";

export type RuleCheck = {
  id: "upfront_cash" | "monthly_surplus" | "debt_to_income" | "emergency_cover" | "surplus_buffer";
  label: string;
  value: number | null;
  displayThreshold: string;
  status: CheckStatus;
  explanation: string;
};

export type PurchaseInputs = {
  purchasePrice: number;
  downPaymentPct: number;
  /** Upfront costs paid in cash (stamp duty, registration, insurance, fees…). */
  upfrontCashCosts: number;
  /** Upfront costs rolled into the loan. */
  financedCosts: number;
  annualInterestRate: number;
  tenureMonths: number;
  monthlyOwnershipCost: number;
};

export type HouseholdInputs = {
  monthlyIncome: number;
  monthlyExpenses: number;
  existingEmis: number;
  otherMonthlyObligations: number;
  liquidSavings: number;
};

export type PurchaseAnalysis = {
  downPayment: number;
  loanAmount: number;
  emi: number;
  totalRepayment: number;
  totalInterest: number;
  upfrontCash: number;
  postPurchaseSavings: number;
  newMonthlyDebt: number;
  before: { cashFlow: CashFlowSummary; dti: number | null; emergencyMonths: number | null };
  after: { cashFlow: CashFlowSummary; dti: number | null; emergencyMonths: number | null };
  yearly: YearlyAmortization[];
  checks: RuleCheck[];
  label: AffordabilityLabel;
};

export type HealthMetrics = {
  surplus: number;
  income: number;
  dti: number | null;
  emergencyMonths: number | null;
  postPurchaseSavings: number;
};

/** Apply the rules to a set of metrics. Shared by the baseline and every stress scenario. */
export function evaluateRules(m: HealthMetrics, rules: AffordabilityRules = DEFAULT_RULES) {
  validateRules(rules);
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  const checks: RuleCheck[] = [];
  checks.push({
    id: "upfront_cash",
    label: "Savings cover the upfront cost",
    value: m.postPurchaseSavings,
    displayThreshold: "≥ ₹0 left after paying",
    status: m.postPurchaseSavings >= 0 ? "pass" : "fail",
    explanation:
      m.postPurchaseSavings >= 0
        ? "Liquid savings can pay the down payment and upfront costs."
        : "Liquid savings are not enough to pay the down payment and upfront costs.",
  });
  checks.push({
    id: "monthly_surplus",
    label: "Positive monthly cash flow",
    value: m.surplus,
    displayThreshold: "> ₹0 per month",
    status: m.surplus > 0 ? "pass" : "fail",
    explanation:
      m.surplus > 0
        ? "Income covers expenses, all EMIs and ownership costs."
        : "Monthly outflows would exceed take-home income.",
  });
  checks.push({
    id: "debt_to_income",
    label: "Debt-to-income (EMIs ÷ take-home)",
    value: m.dti,
    displayThreshold: `≤ ${pct(rules.dtiComfortableMax)} comfortable, > ${pct(rules.dtiStretchMax)} high`,
    status:
      m.dti === null
        ? "fail"
        : m.dti <= rules.dtiComfortableMax
          ? "pass"
          : m.dti <= rules.dtiStretchMax
            ? "warn"
            : "fail",
    explanation: RULE_NOTES.dti,
  });
  checks.push({
    id: "emergency_cover",
    label: "Emergency cover after purchase",
    value: m.emergencyMonths,
    displayThreshold: `≥ ${rules.emergencyComfortableMonths} months comfortable, < ${rules.emergencyMinimumMonths} high`,
    status:
      m.emergencyMonths === null
        ? "pass"
        : m.emergencyMonths >= rules.emergencyComfortableMonths
          ? "pass"
          : m.emergencyMonths >= rules.emergencyMinimumMonths
            ? "warn"
            : "fail",
    explanation: RULE_NOTES.emergency,
  });
  const share = m.income > 0 ? m.surplus / m.income : null;
  checks.push({
    id: "surplus_buffer",
    label: "Monthly buffer (surplus ÷ income)",
    value: share,
    displayThreshold: `≥ ${pct(rules.surplusComfortableShare)}`,
    status: share !== null && share >= rules.surplusComfortableShare ? "pass" : "warn",
    explanation: RULE_NOTES.surplus,
  });
  return { checks, label: labelFromChecks(checks) };
}

export function labelFromChecks(checks: RuleCheck[]): AffordabilityLabel {
  if (checks.some((c) => c.status === "fail")) return "high_strain";
  if (checks.some((c) => c.status === "warn")) return "manageable_limited_buffer";
  return "comfortable";
}

function validateRules(rules: AffordabilityRules) {
  const ok =
    rules.dtiComfortableMax > 0 &&
    rules.dtiComfortableMax <= rules.dtiStretchMax &&
    rules.emergencyMinimumMonths >= 0 &&
    rules.emergencyMinimumMonths <= rules.emergencyComfortableMonths &&
    rules.surplusComfortableShare >= 0;
  if (!ok) throw new FinanceInputError("Affordability rules are inconsistent");
}

export function analysePurchase(
  purchase: PurchaseInputs,
  household: HouseholdInputs,
  rules: AffordabilityRules = DEFAULT_RULES,
): PurchaseAnalysis {
  const downPayment = calculateDownPayment(purchase.purchasePrice, purchase.downPaymentPct);
  const loanAmount = calculateLoanAmount(
    purchase.purchasePrice,
    downPayment,
    purchase.financedCosts,
  );
  const schedule =
    loanAmount > 0
      ? generateAmortizationSchedule(loanAmount, purchase.annualInterestRate, purchase.tenureMonths)
      : { emi: 0, rows: [], totalInterest: 0, totalRepayment: 0 };
  const upfrontCash = totalUpfrontCost(downPayment, purchase.upfrontCashCosts);
  const postPurchaseSavings = postPurchaseLiquidSavings(household.liquidSavings, upfrontCash);

  const beforeFlow = summariseCashFlow({
    monthlyIncome: household.monthlyIncome,
    monthlyExpenses: household.monthlyExpenses,
    monthlyDebtPayments: household.existingEmis,
    monthlyOtherObligations: household.otherMonthlyObligations,
  });
  const newMonthlyDebt = roundPaise(household.existingEmis + schedule.emi);
  const afterFlow = summariseCashFlow({
    monthlyIncome: household.monthlyIncome,
    monthlyExpenses: household.monthlyExpenses + purchase.monthlyOwnershipCost,
    monthlyDebtPayments: newMonthlyDebt,
    monthlyOtherObligations: household.otherMonthlyObligations,
  });
  const before = {
    cashFlow: beforeFlow,
    dti: debtToIncomeRatio(household.existingEmis, household.monthlyIncome),
    emergencyMonths: emergencyFundCoverageMonths(
      household.liquidSavings,
      beforeFlow.totalMonthlyOutflow,
    ),
  };
  const after = {
    cashFlow: afterFlow,
    dti: debtToIncomeRatio(newMonthlyDebt, household.monthlyIncome),
    emergencyMonths: emergencyFundCoverageMonths(
      postPurchaseSavings,
      afterFlow.totalMonthlyOutflow,
    ),
  };
  const { checks, label } = evaluateRules(
    {
      surplus: afterFlow.monthlySurplus,
      income: household.monthlyIncome,
      dti: after.dti,
      emergencyMonths: after.emergencyMonths,
      postPurchaseSavings,
    },
    rules,
  );
  return {
    downPayment,
    loanAmount,
    emi: schedule.emi,
    totalRepayment: schedule.totalRepayment,
    totalInterest: calculateTotalInterest(loanAmount, schedule.totalRepayment),
    upfrontCash,
    postPurchaseSavings,
    newMonthlyDebt,
    before,
    after,
    yearly: "rows" in schedule && schedule.rows.length ? summariseByYear(schedule) : [],
    checks,
    label,
  };
}

/**
 * Highest purchase price (to the nearest ₹10,000) that is classed "comfortable", keeping the
 * down-payment %, rate, tenure and the upfront-cost ratio fixed. Null if none is.
 */
export function findComfortablePrice(
  purchase: PurchaseInputs,
  household: HouseholdInputs,
  rules: AffordabilityRules = DEFAULT_RULES,
): number | null {
  const costRatio =
    purchase.purchasePrice > 0 ? purchase.upfrontCashCosts / purchase.purchasePrice : 0;
  const financedRatio =
    purchase.purchasePrice > 0 ? purchase.financedCosts / purchase.purchasePrice : 0;
  const isComfortable = (price: number) =>
    analysePurchase(
      {
        ...purchase,
        purchasePrice: price,
        upfrontCashCosts: price * costRatio,
        financedCosts: price * financedRatio,
      },
      household,
      rules,
    ).label === "comfortable";
  const step = 10_000;
  if (!isComfortable(step)) return null;
  let lo = step;
  let hi = Math.max(purchase.purchasePrice, step) * 4;
  if (isComfortable(hi)) return hi;
  while (hi - lo > step) {
    const mid = Math.floor((lo + hi) / 2 / step) * step;
    if (mid <= lo) break;
    if (isComfortable(mid)) lo = mid;
    else hi = mid;
  }
  return lo;
}
