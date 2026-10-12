/**
 * Financial engine tests. Expected values were computed independently (Python, closed-form
 * formulas) rather than by calling the code under test.
 */
import { describe, expect, it } from "vitest";

import {
  analysePurchase,
  DEFAULT_RULES,
  evaluateRules,
  findComfortablePrice,
} from "./affordability";
import { FinanceInputError } from "./errors";
import {
  debtToIncomeRatio,
  emergencyFundCoverageMonths,
  monthlySavingsRequired,
  monthsToReachGoal,
  postPurchaseLiquidSavings,
  summariseCashFlow,
} from "./health";
import {
  calculateDownPayment,
  calculateEMI,
  calculateLoanAmount,
  calculateTotalInterest,
  calculateTotalRepayment,
  generateAmortizationSchedule,
  principalForEMI,
  summariseByYear,
} from "./loan";
import { findINRAmounts, parseINRAmount } from "./parse-inr";
import { runScenarioSet, STANDARD_SCENARIOS } from "./scenarios";

describe("calculateEMI", () => {
  it("matches the reducing-balance formula for a ₹60 lakh home loan", () => {
    // P=60,00,000, 8.5% p.a., 240 months → 52,069.394…
    expect(calculateEMI(6_000_000, 8.5, 240)).toBe(52069.39);
  });
  it("matches other independent examples", () => {
    expect(calculateEMI(1_000_000, 10, 60)).toBe(21247.04);
    expect(calculateEMI(100_000, 12, 12)).toBe(8884.88);
  });
  it("handles zero interest as principal / tenure", () => {
    expect(calculateEMI(120_000, 0, 12)).toBe(10000);
    expect(calculateEMI(100_000, 0, 3)).toBe(33333.33);
  });
  it("returns 0 for a zero principal", () => {
    expect(calculateEMI(0, 9, 120)).toBe(0);
  });
  it("handles a one-month loan", () => {
    expect(calculateEMI(100_000, 12, 1)).toBe(101000);
  });
  it("rejects invalid inputs", () => {
    expect(() => calculateEMI(-1, 8, 12)).toThrow(FinanceInputError);
    expect(() => calculateEMI(100, -1, 12)).toThrow(FinanceInputError);
    expect(() => calculateEMI(100, 8, 0)).toThrow(FinanceInputError);
    expect(() => calculateEMI(100, 8, 12.5)).toThrow(FinanceInputError);
    expect(() => calculateEMI(100, 80, 12)).toThrow(FinanceInputError);
    expect(() => calculateEMI(Number.NaN, 8, 12)).toThrow(FinanceInputError);
    expect(() => calculateEMI(100, 8, 601)).toThrow(FinanceInputError);
  });
});

describe("repayment and interest", () => {
  it("totals repayment and interest", () => {
    const total = calculateTotalRepayment(6_000_000, 52069.39, 240);
    expect(total).toBe(12496653.6);
    expect(calculateTotalInterest(6_000_000, total)).toBe(6496653.6);
  });
  it("rejects an EMI that cannot repay the principal", () => {
    expect(() => calculateTotalRepayment(1_000_000, 100, 12)).toThrow(FinanceInputError);
  });
  it("never reports negative interest", () => {
    expect(calculateTotalInterest(1000, 900)).toBe(0);
  });
});

describe("generateAmortizationSchedule", () => {
  const schedule = generateAmortizationSchedule(6_000_000, 8.5, 240);
  it("has one row per month and closes at exactly zero", () => {
    expect(schedule.rows).toHaveLength(240);
    expect(schedule.rows.at(-1)?.closingBalance).toBe(0);
  });
  it("repays exactly the principal", () => {
    const principal = schedule.rows.reduce((s, r) => s + r.principal, 0);
    expect(principal).toBeCloseTo(6_000_000, 1);
  });
  it("agrees with the closed-form total interest within rounding", () => {
    // closed form: 6,496,654.56; per-month paisa rounding may shift it by a few rupees
    expect(Math.abs(schedule.totalInterest - 6496654.56)).toBeLessThan(5);
  });
  it("starts interest-heavy: month 1 interest = 60,00,000 × 8.5%/12", () => {
    expect(schedule.rows[0]?.interest).toBe(42500);
  });
  it("summarises by year", () => {
    const years = summariseByYear(schedule);
    expect(years).toHaveLength(20);
    expect(years.at(-1)?.closingBalance).toBe(0);
  });
  it("works at zero interest", () => {
    const s = generateAmortizationSchedule(100_000, 0, 3);
    expect(s.totalInterest).toBe(0);
    expect(s.totalRepayment).toBeCloseTo(100_000, 2);
  });
});

describe("down payment and loan amount", () => {
  it("calculates the down payment", () => {
    expect(calculateDownPayment(7_500_000, 20)).toBe(1_500_000);
    expect(calculateDownPayment(7_500_000, 0)).toBe(0);
    expect(calculateDownPayment(7_500_000, 100)).toBe(7_500_000);
    expect(() => calculateDownPayment(7_500_000, 101)).toThrow(FinanceInputError);
  });
  it("calculates the loan, optionally financing costs", () => {
    expect(calculateLoanAmount(7_500_000, 1_500_000)).toBe(6_000_000);
    expect(calculateLoanAmount(7_500_000, 1_500_000, 50_000)).toBe(6_050_000);
    expect(() => calculateLoanAmount(100, 200)).toThrow(FinanceInputError);
  });
  it("inverts the EMI formula", () => {
    // 52,000/month at 9% for 20 years supports ≈ ₹57,79,537.61
    expect(principalForEMI(52_000, 9, 240)).toBeCloseTo(5779537.61, 1);
    expect(principalForEMI(10_000, 0, 12)).toBe(120_000);
  });
});

describe("health tools", () => {
  it("summarises cash flow", () => {
    const s = summariseCashFlow({
      monthlyIncome: 200_000,
      monthlyExpenses: 70_000,
      monthlyDebtPayments: 15_000,
    });
    expect(s.monthlySurplus).toBe(115_000);
    expect(s.savingsRate).toBeCloseTo(0.575);
  });
  it("reports a deficit as negative surplus", () => {
    expect(
      summariseCashFlow({ monthlyIncome: 50_000, monthlyExpenses: 60_000, monthlyDebtPayments: 0 })
        .monthlySurplus,
    ).toBe(-10_000);
  });
  it("computes DTI on take-home income, null for zero income", () => {
    expect(debtToIncomeRatio(67_069.39, 200_000)).toBeCloseTo(0.3353, 4);
    expect(debtToIncomeRatio(1000, 0)).toBeNull();
  });
  it("computes emergency cover, never negative", () => {
    expect(emergencyFundCoverageMonths(600_000, 100_000)).toBe(6);
    expect(emergencyFundCoverageMonths(-5, 100_000)).toBe(0);
    expect(emergencyFundCoverageMonths(5, 0)).toBeNull();
  });
  it("computes post-purchase savings (may be a shortfall)", () => {
    expect(postPurchaseLiquidSavings(2_500_000, 1_950_000)).toBe(550_000);
    expect(postPurchaseLiquidSavings(1_000_000, 1_950_000)).toBe(-950_000);
  });
  it("computes the monthly saving for a goal", () => {
    expect(monthlySavingsRequired(1_000_000, 200_000, 24)).toBe(33333.33);
    // with 6% p.a. compounded monthly: ≈ 30,456.49 (independent calc)
    expect(monthlySavingsRequired(1_000_000, 200_000, 24, 6)).toBeCloseTo(30456.49, 1);
    expect(monthlySavingsRequired(100, 200, 12)).toBe(0);
  });
  it("computes months to a goal", () => {
    expect(monthsToReachGoal(100_000, 30_000)).toBe(4);
    expect(monthsToReachGoal(0, 30_000)).toBe(0);
    expect(monthsToReachGoal(100, 0)).toBeNull();
  });
});

const DEMO_PURCHASE = {
  purchasePrice: 7_500_000,
  downPaymentPct: 20,
  upfrontCashCosts: 450_000,
  financedCosts: 0,
  annualInterestRate: 8.5,
  tenureMonths: 240,
  monthlyOwnershipCost: 0,
};
const DEMO_HOUSEHOLD = {
  monthlyIncome: 200_000,
  monthlyExpenses: 70_000,
  existingEmis: 15_000,
  otherMonthlyObligations: 0,
  liquidSavings: 2_500_000,
};

describe("analysePurchase (demo profile, ₹75 lakh house)", () => {
  const a = analysePurchase(DEMO_PURCHASE, DEMO_HOUSEHOLD);
  it("derives the loan figures", () => {
    expect(a.downPayment).toBe(1_500_000);
    expect(a.loanAmount).toBe(6_000_000);
    expect(a.emi).toBe(52069.39);
    expect(a.upfrontCash).toBe(1_950_000);
    expect(a.postPurchaseSavings).toBe(550_000);
  });
  it("derives cash flow after purchase", () => {
    expect(a.after.cashFlow.monthlySurplus).toBeCloseTo(62930.61, 2);
    expect(a.after.dti).toBeCloseTo(0.3353, 4);
    // 5,50,000 / (70,000 + 67,069.39) ≈ 4.01 months
    expect(a.after.emergencyMonths).toBeCloseTo(4.0126, 3);
  });
  it("classes it as manageable with a limited buffer (emergency cover < 6 months)", () => {
    expect(a.label).toBe("manageable_limited_buffer");
    expect(a.checks.find((c) => c.id === "emergency_cover")?.status).toBe("warn");
    expect(a.checks.find((c) => c.id === "debt_to_income")?.status).toBe("pass");
  });
  it("flags high strain when savings cannot cover the upfront cost", () => {
    const b = analysePurchase(DEMO_PURCHASE, { ...DEMO_HOUSEHOLD, liquidSavings: 1_000_000 });
    expect(b.label).toBe("high_strain");
    expect(b.checks.find((c) => c.id === "upfront_cash")?.status).toBe("fail");
  });
  it("handles an all-cash purchase (100% down)", () => {
    const c = analysePurchase(
      { ...DEMO_PURCHASE, purchasePrice: 1_000_000, downPaymentPct: 100, upfrontCashCosts: 0 },
      DEMO_HOUSEHOLD,
    );
    expect(c.loanAmount).toBe(0);
    expect(c.emi).toBe(0);
    expect(c.yearly).toHaveLength(0);
  });
  it("finds a comfortable price below the asked price", () => {
    const p = findComfortablePrice(DEMO_PURCHASE, DEMO_HOUSEHOLD);
    expect(p).not.toBeNull();
    expect(p!).toBeLessThan(7_500_000);
    const check = analysePurchase(
      { ...DEMO_PURCHASE, purchasePrice: p!, upfrontCashCosts: p! * 0.06 },
      DEMO_HOUSEHOLD,
    );
    expect(check.label).toBe("comfortable");
  });
});

describe("evaluateRules", () => {
  it("rejects inconsistent rules", () => {
    expect(() =>
      evaluateRules(
        { surplus: 1, income: 1, dti: 0, emergencyMonths: 1, postPurchaseSavings: 1 },
        { ...DEFAULT_RULES, dtiComfortableMax: 0.6, dtiStretchMax: 0.5 },
      ),
    ).toThrow(FinanceInputError);
  });
});

describe("scenarios", () => {
  const baseline = analysePurchase(DEMO_PURCHASE, DEMO_HOUSEHOLD);
  const results = runScenarioSet(DEMO_PURCHASE, DEMO_HOUSEHOLD, baseline);
  const byId = Object.fromEntries(results.map((r) => [r.params.id, r]));
  it("returns the baseline plus every standard scenario", () => {
    expect(results).toHaveLength(STANDARD_SCENARIOS.length + 1);
    expect(results[0]?.isBaseline).toBe(true);
    expect(results[0]?.delta.monthlySurplus).toBe(0);
  });
  it("income −20% cuts the surplus by ₹40,000", () => {
    expect(byId.income_down_20?.delta.monthlySurplus).toBeCloseTo(-40_000, 2);
  });
  it("6 months without income exhausts the post-purchase savings", () => {
    const r = byId.income_stops_6m!;
    // 5,50,000 − 1,37,069.39 × n < 0 at n = 5
    expect(r.monthExhausted).toBe(5);
    expect(r.monthlySurplus).toBeCloseTo(-137069.39, 2); // surplus while income has stopped
    expect(r.label).toBe("high_strain");
  });
  it("a rate rise recalculates the EMI", () => {
    const r = byId.rate_up_1_5!;
    expect(r.emi).toBe(calculateEMI(6_000_000, 10, 240));
    expect(r.emi).toBeGreaterThan(baseline.emi);
  });
  it("a ₹2 lakh shock reduces starting savings", () => {
    expect(byId.shock_2l?.startingSavings).toBe(350_000);
  });
  it("rejects out-of-range parameters", () => {
    expect(() =>
      runScenarioSet(DEMO_PURCHASE, DEMO_HOUSEHOLD, baseline, [
        { ...STANDARD_SCENARIOS[0]!, incomeChangePct: -150 },
      ]),
    ).toThrow(FinanceInputError);
  });
});

describe("parseINRAmount", () => {
  it.each([
    ["Can I afford a ₹75 lakh house?", 7_500_000],
    ["buy a 20L car", 2_000_000],
    ["MBA costing 30 lakhs", 3_000_000],
    ["a 1.2 crore flat", 12_000_000],
    ["₹15,00,000", 1_500_000],
    ["Rs. 2,00,000 shock", 200_000],
    ["save 50k a month", 50_000],
    ["no amount here", null],
  ])("%s → %s", (text, expected) => {
    expect(parseINRAmount(text)).toBe(expected);
  });
  it("finds several amounts in order", () => {
    expect(
      findINRAmounts("Compare a ₹15 lakh car with a ₹20 lakh car").map((a) => a.value),
    ).toEqual([1_500_000, 2_000_000]);
  });
});
