/**
 * Financial-health tools: cash flow, debt load, emergency cover, savings targets. Pure functions.
 */
import { FinanceInputError, requireFinite, requireNonNegative, roundPaise } from "./errors";

export type CashFlowSummary = {
  monthlyIncome: number;
  monthlyExpenses: number;
  monthlyDebtPayments: number;
  monthlyOtherObligations: number;
  totalMonthlyOutflow: number;
  monthlySurplus: number; // negative = deficit
  savingsRate: number | null; // surplus / income
};

export function summariseCashFlow(input: {
  monthlyIncome: number;
  monthlyExpenses: number;
  monthlyDebtPayments: number;
  monthlyOtherObligations?: number;
}): CashFlowSummary {
  requireNonNegative("monthlyIncome", input.monthlyIncome);
  requireNonNegative("monthlyExpenses", input.monthlyExpenses);
  requireNonNegative("monthlyDebtPayments", input.monthlyDebtPayments);
  const other = input.monthlyOtherObligations ?? 0;
  requireNonNegative("monthlyOtherObligations", other);
  const outflow = input.monthlyExpenses + input.monthlyDebtPayments + other;
  const surplus = input.monthlyIncome - outflow;
  return {
    monthlyIncome: roundPaise(input.monthlyIncome),
    monthlyExpenses: roundPaise(input.monthlyExpenses),
    monthlyDebtPayments: roundPaise(input.monthlyDebtPayments),
    monthlyOtherObligations: roundPaise(other),
    totalMonthlyOutflow: roundPaise(outflow),
    monthlySurplus: roundPaise(surplus),
    savingsRate: input.monthlyIncome > 0 ? surplus / input.monthlyIncome : null,
  };
}

/**
 * Debt-to-income ratio = total monthly debt repayments ÷ monthly TAKE-HOME income.
 *
 * Denominator note: Indian lenders usually assess a "FOIR" (fixed obligations to income ratio)
 * on net monthly income, which is what this uses. Ratios on gross income come out lower, so this
 * figure is deliberately the more conservative of the two. Returns null when income is 0.
 */
export function debtToIncomeRatio(monthlyDebtPayments: number, monthlyTakeHome: number) {
  requireNonNegative("monthlyDebtPayments", monthlyDebtPayments);
  requireNonNegative("monthlyTakeHome", monthlyTakeHome);
  if (monthlyTakeHome === 0) return null;
  return monthlyDebtPayments / monthlyTakeHome;
}

/**
 * Months the liquid savings would cover essential monthly outflows (living expenses + debt
 * repayments + other fixed obligations) with no income. Null when there are no outflows.
 */
export function emergencyFundCoverageMonths(
  liquidSavings: number,
  monthlyEssentialOutflow: number,
) {
  requireFinite("liquidSavings", liquidSavings);
  requireNonNegative("monthlyEssentialOutflow", monthlyEssentialOutflow);
  if (monthlyEssentialOutflow === 0) return null;
  return Math.max(0, liquidSavings) / monthlyEssentialOutflow;
}

/** Cash paid at purchase: down payment + upfront costs that are not financed. */
export function totalUpfrontCost(downPayment: number, upfrontCashCosts: number): number {
  requireNonNegative("downPayment", downPayment);
  requireNonNegative("upfrontCashCosts", upfrontCashCosts);
  return roundPaise(downPayment + upfrontCashCosts);
}

/** Liquid savings left after paying the upfront cash cost. Can be negative (a shortfall). */
export function postPurchaseLiquidSavings(liquidSavings: number, upfrontCash: number): number {
  requireNonNegative("liquidSavings", liquidSavings);
  requireNonNegative("upfrontCash", upfrontCash);
  return roundPaise(liquidSavings - upfrontCash);
}

/**
 * Monthly saving needed to grow `currentSavings` to `targetAmount` in `months`, with an optional
 * annual return compounded monthly (default 0%: no growth assumed). Returns 0 if already met.
 */
export function monthlySavingsRequired(
  targetAmount: number,
  currentSavings: number,
  months: number,
  annualReturnPercent = 0,
): number {
  requireNonNegative("targetAmount", targetAmount);
  requireNonNegative("currentSavings", currentSavings);
  requireNonNegative("annualReturnPercent", annualReturnPercent);
  if (!Number.isInteger(months) || months < 1 || months > 600) {
    throw new FinanceInputError("months must be a whole number between 1 and 600");
  }
  const r = annualReturnPercent / 12 / 100;
  const grownCurrent = currentSavings * Math.pow(1 + r, months);
  const gap = targetAmount - grownCurrent;
  if (gap <= 0) return 0;
  const annuityFactor = r === 0 ? months : (Math.pow(1 + r, months) - 1) / r;
  return roundPaise(gap / annuityFactor);
}

/** Months needed to close a savings gap at a fixed monthly saving (no returns). Null if never. */
export function monthsToReachGoal(gap: number, monthlySaving: number): number | null {
  requireFinite("gap", gap);
  requireFinite("monthlySaving", monthlySaving);
  if (gap <= 0) return 0;
  if (monthlySaving <= 0) return null;
  return Math.ceil(gap / monthlySaving);
}

/** Recurring cost of owning the purchase (maintenance, insurance, fuel, society charges…). */
export function monthlyOwnershipCost(items: { label: string; monthlyAmount: number }[]): number {
  let total = 0;
  for (const item of items) {
    requireNonNegative(`ownership cost "${item.label}"`, item.monthlyAmount);
    total += item.monthlyAmount;
  }
  return roundPaise(total);
}
