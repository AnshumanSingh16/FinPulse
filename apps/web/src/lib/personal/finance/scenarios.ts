/**
 * Stress scenarios: "what if" simulations, not predictions. Each scenario changes stated
 * assumptions and replays the next `horizonMonths` month by month, starting from the savings left
 * after the purchase.
 *
 * Simplification (stated to the user): a rate rise is applied from month 1 by recalculating the
 * EMI on the full loan for the same tenure. Indian lenders often extend the tenure instead, which
 * keeps the EMI flat but raises total interest.
 */
import {
  DEFAULT_RULES,
  evaluateRules,
  type AffordabilityLabel,
  type AffordabilityRules,
  type HouseholdInputs,
  type PurchaseAnalysis,
  type PurchaseInputs,
  type RuleCheck,
} from "./affordability";
import { FinanceInputError, roundPaise } from "./errors";
import { debtToIncomeRatio, emergencyFundCoverageMonths } from "./health";
import { calculateEMI, MAX_ANNUAL_RATE } from "./loan";

export type ScenarioParams = {
  id: string;
  name: string;
  /** e.g. −20 for a 20% fall in take-home income. */
  incomeChangePct: number;
  /** Months (from month 1) with no income at all. */
  incomeStopMonths: number;
  /** e.g. 15 for living expenses rising 15%. */
  expenseChangePct: number;
  /** Percentage points added to the loan rate. */
  rateChangePp: number;
  /** One-off unexpected expense in month 1. */
  oneOffExpense: number;
};

export const STANDARD_SCENARIOS: ScenarioParams[] = [
  {
    id: "income_down_20",
    name: "Income falls 20%",
    incomeChangePct: -20,
    incomeStopMonths: 0,
    expenseChangePct: 0,
    rateChangePp: 0,
    oneOffExpense: 0,
  },
  {
    id: "income_stops_6m",
    name: "Income stops for 6 months",
    incomeChangePct: 0,
    incomeStopMonths: 6,
    expenseChangePct: 0,
    rateChangePp: 0,
    oneOffExpense: 0,
  },
  {
    id: "expenses_up_15",
    name: "Living expenses rise 15%",
    incomeChangePct: 0,
    incomeStopMonths: 0,
    expenseChangePct: 15,
    rateChangePp: 0,
    oneOffExpense: 0,
  },
  {
    id: "rate_up_1_5",
    name: "Interest rate +1.5 pp",
    incomeChangePct: 0,
    incomeStopMonths: 0,
    expenseChangePct: 0,
    rateChangePp: 1.5,
    oneOffExpense: 0,
  },
  {
    id: "shock_2l",
    name: "Unexpected ₹2 lakh expense",
    incomeChangePct: 0,
    incomeStopMonths: 0,
    expenseChangePct: 0,
    rateChangePp: 0,
    oneOffExpense: 200_000,
  },
  {
    id: "combined",
    name: "Combined: income −20%, expenses +15%, rate +1.5 pp",
    incomeChangePct: -20,
    incomeStopMonths: 0,
    expenseChangePct: 15,
    rateChangePp: 1.5,
    oneOffExpense: 0,
  },
];

export type ScenarioResult = {
  params: ScenarioParams;
  isBaseline: boolean;
  changedAssumptions: string[];
  monthlyIncome: number;
  monthlyExpenses: number;
  emi: number;
  monthlyDebt: number;
  /** Monthly surplus during the stress period (while income has stopped, if it does). */
  monthlySurplus: number;
  dti: number | null;
  startingSavings: number;
  lowestSavings: number;
  savingsAfterHorizon: number;
  monthExhausted: number | null;
  emergencyMonths: number | null;
  checks: RuleCheck[];
  breaches: string[];
  label: AffordabilityLabel;
  delta: { monthlySurplus: number; savingsAfterHorizon: number; emergencyMonths: number | null };
  trajectory: { month: number; savings: number }[];
};

function validate(p: ScenarioParams) {
  const bad =
    !Number.isFinite(p.incomeChangePct) ||
    p.incomeChangePct < -100 ||
    p.incomeChangePct > 200 ||
    !Number.isInteger(p.incomeStopMonths) ||
    p.incomeStopMonths < 0 ||
    p.incomeStopMonths > 36 ||
    !Number.isFinite(p.expenseChangePct) ||
    p.expenseChangePct < -90 ||
    p.expenseChangePct > 300 ||
    !Number.isFinite(p.rateChangePp) ||
    p.rateChangePp < -10 ||
    p.rateChangePp > 20 ||
    !Number.isFinite(p.oneOffExpense) ||
    p.oneOffExpense < 0;
  if (bad) throw new FinanceInputError(`Scenario "${p.name}" has out-of-range parameters`);
}

export function describeChanges(p: ScenarioParams): string[] {
  const out: string[] = [];
  if (p.incomeChangePct)
    out.push(`Take-home income ${p.incomeChangePct > 0 ? "+" : ""}${p.incomeChangePct}%`);
  if (p.incomeStopMonths) out.push(`No income for the first ${p.incomeStopMonths} months`);
  if (p.expenseChangePct)
    out.push(`Living expenses ${p.expenseChangePct > 0 ? "+" : ""}${p.expenseChangePct}%`);
  if (p.rateChangePp)
    out.push(
      `Loan rate ${p.rateChangePp > 0 ? "+" : ""}${p.rateChangePp} percentage points (EMI recalculated, same tenure)`,
    );
  if (p.oneOffExpense)
    out.push(
      `One-off expense of ₹${Math.round(p.oneOffExpense).toLocaleString("en-IN")} in month 1`,
    );
  return out;
}

export function runScenario(
  purchase: PurchaseInputs,
  household: HouseholdInputs,
  baseline: PurchaseAnalysis,
  params: ScenarioParams,
  rules: AffordabilityRules = DEFAULT_RULES,
  horizonMonths = 12,
): Omit<ScenarioResult, "delta" | "isBaseline"> {
  validate(params);
  const income = household.monthlyIncome * (1 + params.incomeChangePct / 100);
  const expenses =
    household.monthlyExpenses * (1 + params.expenseChangePct / 100) + purchase.monthlyOwnershipCost;
  const rate = Math.min(
    MAX_ANNUAL_RATE,
    Math.max(0, purchase.annualInterestRate + params.rateChangePp),
  );
  const emi =
    params.rateChangePp === 0 || baseline.loanAmount === 0
      ? baseline.emi
      : calculateEMI(baseline.loanAmount, rate, purchase.tenureMonths);
  const monthlyDebt = household.existingEmis + emi;
  const outflow = expenses + monthlyDebt + household.otherMonthlyObligations;
  // The surplus that matters is the one while the stress lasts: with no income, that is −outflow.
  const surplus = params.incomeStopMonths > 0 ? -outflow : income - outflow;

  const startingSavings = baseline.postPurchaseSavings - params.oneOffExpense;
  let savings = startingSavings;
  let lowest = savings;
  let exhausted: number | null = savings < 0 ? 0 : null;
  const trajectory = [{ month: 0, savings: roundPaise(savings) }];
  for (let month = 1; month <= horizonMonths; month++) {
    const monthIncome = month <= params.incomeStopMonths ? 0 : income;
    savings += monthIncome - outflow;
    trajectory.push({ month, savings: roundPaise(savings) });
    if (savings < lowest) lowest = savings;
    if (exhausted === null && savings < 0) exhausted = month;
  }
  const dti = debtToIncomeRatio(monthlyDebt, Math.max(0, income));
  const emergencyMonths = emergencyFundCoverageMonths(lowest, outflow);
  const { checks, label } = evaluateRules(
    { surplus, income, dti, emergencyMonths, postPurchaseSavings: lowest },
    rules,
  );
  return {
    params,
    changedAssumptions: describeChanges(params),
    monthlyIncome: roundPaise(income),
    monthlyExpenses: roundPaise(expenses),
    emi,
    monthlyDebt: roundPaise(monthlyDebt),
    monthlySurplus: roundPaise(surplus),
    dti,
    startingSavings: roundPaise(startingSavings),
    lowestSavings: roundPaise(lowest),
    savingsAfterHorizon: roundPaise(savings),
    monthExhausted: exhausted,
    emergencyMonths,
    checks,
    breaches: checks.filter((c) => c.status === "fail").map((c) => c.label),
    label,
    trajectory,
  };
}

const BASELINE: ScenarioParams = {
  id: "baseline",
  name: "Baseline",
  incomeChangePct: 0,
  incomeStopMonths: 0,
  expenseChangePct: 0,
  rateChangePp: 0,
  oneOffExpense: 0,
};

/** Baseline plus each scenario, every result carrying its difference from the baseline. */
export function runScenarioSet(
  purchase: PurchaseInputs,
  household: HouseholdInputs,
  baseline: PurchaseAnalysis,
  scenarios: ScenarioParams[] = STANDARD_SCENARIOS,
  rules: AffordabilityRules = DEFAULT_RULES,
  horizonMonths = 12,
): ScenarioResult[] {
  const base = runScenario(purchase, household, baseline, BASELINE, rules, horizonMonths);
  const withDelta = (r: typeof base, isBaseline: boolean): ScenarioResult => ({
    ...r,
    isBaseline,
    delta: {
      monthlySurplus: roundPaise(r.monthlySurplus - base.monthlySurplus),
      savingsAfterHorizon: roundPaise(r.savingsAfterHorizon - base.savingsAfterHorizon),
      emergencyMonths:
        r.emergencyMonths !== null && base.emergencyMonths !== null
          ? r.emergencyMonths - base.emergencyMonths
          : null,
    },
  });
  return [
    withDelta(base, true),
    ...scenarios.map((s) =>
      withDelta(runScenario(purchase, household, baseline, s, rules, horizonMonths), false),
    ),
  ];
}
