/**
 * Loan tools. Pure, deterministic functions: no AI ever produces these numbers.
 *
 * EMI uses the standard reducing-balance formula
 *   EMI = P × r × (1 + r)^n / ((1 + r)^n − 1)
 * where P is the principal, r the monthly rate (annual % / 12 / 100) and n the tenure in months.
 * At 0% interest the formula is undefined, so the EMI is simply P / n.
 */
import { FinanceInputError, requireFinite, requireNonNegative, roundPaise } from "./errors";

export const MAX_ANNUAL_RATE = 50; // %; anything higher is almost certainly a typo
export const MAX_TENURE_MONTHS = 600; // 50 years

function validateLoan(principal: number, annualInterestRate: number, tenureMonths: number) {
  requireNonNegative("principal", principal);
  requireNonNegative("annualInterestRate", annualInterestRate);
  if (annualInterestRate > MAX_ANNUAL_RATE) {
    throw new FinanceInputError(`annualInterestRate above ${MAX_ANNUAL_RATE}% is not supported`);
  }
  requireFinite("tenureMonths", tenureMonths);
  if (!Number.isInteger(tenureMonths) || tenureMonths < 1 || tenureMonths > MAX_TENURE_MONTHS) {
    throw new FinanceInputError(
      `tenureMonths must be a whole number between 1 and ${MAX_TENURE_MONTHS}`,
    );
  }
}

/** Monthly instalment, rounded to the paisa. */
export function calculateEMI(
  principal: number,
  annualInterestRate: number,
  tenureMonths: number,
): number {
  validateLoan(principal, annualInterestRate, tenureMonths);
  if (principal === 0) return 0;
  const r = annualInterestRate / 12 / 100;
  if (r === 0) return roundPaise(principal / tenureMonths);
  const growth = Math.pow(1 + r, tenureMonths);
  return roundPaise((principal * r * growth) / (growth - 1));
}

/**
 * Total paid over the loan's life. Uses the amortization schedule, so the final instalment's
 * rounding adjustment is included rather than assuming every payment equals the EMI exactly.
 */
export function calculateTotalRepayment(
  principal: number,
  monthlyEMI: number,
  tenureMonths: number,
): number {
  requireNonNegative("principal", principal);
  requireNonNegative("monthlyEMI", monthlyEMI);
  requireFinite("tenureMonths", tenureMonths);
  if (!Number.isInteger(tenureMonths) || tenureMonths < 1) {
    throw new FinanceInputError("tenureMonths must be a positive whole number");
  }
  const total = monthlyEMI * tenureMonths;
  if (total + 0.01 * tenureMonths < principal) {
    throw new FinanceInputError("monthlyEMI × tenureMonths is less than the principal");
  }
  return roundPaise(total);
}

export function calculateTotalInterest(principal: number, totalRepayment: number): number {
  requireNonNegative("principal", principal);
  requireNonNegative("totalRepayment", totalRepayment);
  return roundPaise(Math.max(0, totalRepayment - principal));
}

export type AmortizationRow = {
  month: number;
  openingBalance: number;
  emi: number;
  interest: number;
  principal: number;
  closingBalance: number;
};

export type AmortizationSchedule = {
  emi: number;
  rows: AmortizationRow[];
  totalInterest: number;
  totalRepayment: number;
};

/**
 * Month-by-month schedule. Each month's interest is the opening balance × r, rounded to the
 * paisa; the last instalment absorbs the accumulated rounding so the balance closes at exactly 0.
 */
export function generateAmortizationSchedule(
  principal: number,
  annualInterestRate: number,
  tenureMonths: number,
): AmortizationSchedule {
  const emi = calculateEMI(principal, annualInterestRate, tenureMonths);
  const r = annualInterestRate / 12 / 100;
  const rows: AmortizationRow[] = [];
  let balance = principal;
  let totalInterest = 0;
  let totalRepayment = 0;
  for (let month = 1; month <= tenureMonths; month++) {
    const interest = roundPaise(balance * r);
    const isLast = month === tenureMonths;
    const principalPart = isLast ? balance : roundPaise(Math.min(emi - interest, balance));
    const payment = roundPaise(principalPart + interest);
    const closing = roundPaise(balance - principalPart);
    rows.push({
      month,
      openingBalance: roundPaise(balance),
      emi: payment,
      interest,
      principal: roundPaise(principalPart),
      closingBalance: closing,
    });
    totalInterest += interest;
    totalRepayment += payment;
    balance = closing;
  }
  return {
    emi,
    rows,
    totalInterest: roundPaise(totalInterest),
    totalRepayment: roundPaise(totalRepayment),
  };
}

export type YearlyAmortization = {
  year: number;
  principalPaid: number;
  interestPaid: number;
  closingBalance: number;
};

/** The schedule summarised by loan year (for charts). */
export function summariseByYear(schedule: AmortizationSchedule): YearlyAmortization[] {
  const years: YearlyAmortization[] = [];
  for (const row of schedule.rows) {
    const year = Math.ceil(row.month / 12);
    let entry = years[year - 1];
    if (!entry) {
      entry = { year, principalPaid: 0, interestPaid: 0, closingBalance: 0 };
      years.push(entry);
    }
    entry.principalPaid = roundPaise(entry.principalPaid + row.principal);
    entry.interestPaid = roundPaise(entry.interestPaid + row.interest);
    entry.closingBalance = row.closingBalance;
  }
  return years;
}

export function calculateDownPayment(purchasePrice: number, downPaymentPercentage: number): number {
  requireNonNegative("purchasePrice", purchasePrice);
  requireNonNegative("downPaymentPercentage", downPaymentPercentage);
  if (downPaymentPercentage > 100) {
    throw new FinanceInputError("downPaymentPercentage cannot exceed 100");
  }
  return roundPaise((purchasePrice * downPaymentPercentage) / 100);
}

/**
 * Amount to borrow: price − down payment, plus any additional costs the buyer chooses to finance
 * (pass 0 when costs such as stamp duty are paid in cash, which is the usual case for home loans).
 */
export function calculateLoanAmount(
  purchasePrice: number,
  downPayment: number,
  financedAdditionalCosts = 0,
): number {
  requireNonNegative("purchasePrice", purchasePrice);
  requireNonNegative("downPayment", downPayment);
  requireNonNegative("financedAdditionalCosts", financedAdditionalCosts);
  if (downPayment > purchasePrice) {
    throw new FinanceInputError("downPayment cannot exceed purchasePrice");
  }
  return roundPaise(purchasePrice - downPayment + financedAdditionalCosts);
}

/** Largest principal a given EMI can service at a rate and tenure (inverse of calculateEMI). */
export function principalForEMI(
  monthlyEMI: number,
  annualInterestRate: number,
  tenureMonths: number,
): number {
  requireNonNegative("monthlyEMI", monthlyEMI);
  validateLoan(0, annualInterestRate, tenureMonths);
  const r = annualInterestRate / 12 / 100;
  if (r === 0) return roundPaise(monthlyEMI * tenureMonths);
  const growth = Math.pow(1 + r, tenureMonths);
  return roundPaise((monthlyEMI * (growth - 1)) / (r * growth));
}
