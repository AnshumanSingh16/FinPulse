/**
 * Two decisions that come up again and again for Indian households, answered with transparent
 * month-by-month simulations rather than rules of thumb. Every rate is an input the person sees;
 * tax is modelled only where stated.
 */
import { FinanceInputError, requireNonNegative, roundRupees } from "./errors";
import { calculateEMI } from "./loan";

const monthly = (annualPct: number) => Math.pow(1 + annualPct / 100, 1 / 12) - 1;

/** Find x in [lo, hi] where f(x) = 0, assuming f changes sign once. Null if it doesn't. */
function solve(f: (x: number) => number, lo: number, hi: number): number | null {
  let flo = f(lo);
  const fhi = f(hi);
  if (flo === 0) return lo;
  if (Math.sign(flo) === Math.sign(fhi)) return null;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    const fm = f(mid);
    if (Math.sign(fm) === Math.sign(flo)) {
      lo = mid;
      flo = fm;
    } else hi = mid;
  }
  return Math.round(((lo + hi) / 2) * 100) / 100;
}

// ---------------------------------------------------------------- rent vs buy

export type RentVsBuyInput = {
  price: number;
  downPaymentPct: number;
  /** Stamp duty, registration and other one-time costs, % of the price. */
  upfrontCostPct: number;
  loanRatePct: number;
  tenureMonths: number;
  /** Rent for a comparable home today. */
  monthlyRent: number;
  rentGrowthPct: number;
  /** Yearly change in the home's value. */
  appreciationPct: number;
  /** Maintenance, society charges, property tax and repairs per year, % of the home's value. */
  ownershipCostPct: number;
  /** Return on money the renter (or the buyer, when owning is cheaper) invests instead. */
  investReturnPct: number;
  years: number;
};

export type RentVsBuyYear = {
  year: number;
  buyerWealth: number;
  renterWealth: number;
  homeValue: number;
  loanBalance: number;
  rent: number;
  ownerMonthlyCost: number;
};

export type RentVsBuyResult = {
  emi: number;
  upfrontCash: number;
  years: RentVsBuyYear[];
  winner: "buy" | "rent" | "even";
  /** Buyer wealth minus renter wealth at the horizon. */
  difference: number;
  /** First year in which buying is ahead and stays ahead to the horizon; null if never. */
  breakevenYear: number | null;
  /** Yearly appreciation at which both come out level at the horizon; null if outside 0–20%. */
  breakevenAppreciationPct: number | null;
  totalRentPaid: number;
  totalInterestPaid: number;
};

function simulateRentVsBuy(i: RentVsBuyInput) {
  const months = Math.round(i.years * 12);
  const loan0 = i.price * (1 - i.downPaymentPct / 100);
  const emi = loan0 > 0 ? calculateEMI(loan0, i.loanRatePct, i.tenureMonths) : 0;
  const upfrontCash = (i.price * (i.downPaymentPct + i.upfrontCostPct)) / 100;
  const r = monthly(i.investReturnPct);
  const rl = i.loanRatePct / 12 / 100;
  let balance = loan0;
  let renterPortfolio = upfrontCash; // the renter invests what the buyer spends on day one
  let buyerPortfolio = 0;
  let totalRent = 0;
  let totalInterest = 0;
  const years: RentVsBuyYear[] = [];
  for (let m = 1; m <= months; m++) {
    const yr = Math.floor((m - 1) / 12);
    const value = i.price * Math.pow(1 + i.appreciationPct / 100, m / 12);
    const rent = i.monthlyRent * Math.pow(1 + i.rentGrowthPct / 100, yr);
    let pay = 0;
    if (balance > 0) {
      const interest = balance * rl;
      pay = Math.min(emi, balance + interest);
      balance = Math.max(0, balance + interest - pay);
      totalInterest += interest;
    }
    const ownerCost = pay + (value * i.ownershipCostPct) / 100 / 12;
    totalRent += rent;
    renterPortfolio *= 1 + r;
    buyerPortfolio *= 1 + r;
    const diff = ownerCost - rent;
    if (diff > 0) renterPortfolio += diff;
    else buyerPortfolio -= diff;
    if (m % 12 === 0 || m === months) {
      years.push({
        year: Math.ceil(m / 12),
        buyerWealth: roundRupees(value - balance + buyerPortfolio),
        renterWealth: roundRupees(renterPortfolio),
        homeValue: roundRupees(value),
        loanBalance: roundRupees(balance),
        rent: roundRupees(rent),
        ownerMonthlyCost: roundRupees(ownerCost),
      });
    }
  }
  return { emi, upfrontCash, years, totalRent, totalInterest };
}

export function rentVsBuy(input: RentVsBuyInput): RentVsBuyResult {
  for (const [k, v] of Object.entries(input)) requireNonNegative(k, v);
  if (input.years < 1 || input.years > 40) throw new FinanceInputError("years must be 1–40");
  if (input.downPaymentPct > 100) throw new FinanceInputError("downPaymentPct must be ≤ 100");
  const sim = simulateRentVsBuy(input);
  const last = sim.years[sim.years.length - 1]!;
  const difference = last.buyerWealth - last.renterWealth;
  let breakevenYear: number | null = null;
  for (let k = sim.years.length - 1; k >= 0; k--) {
    if (sim.years[k]!.buyerWealth >= sim.years[k]!.renterWealth) breakevenYear = sim.years[k]!.year;
    else break;
  }
  const atHorizon = (appreciationPct: number) => {
    const y = simulateRentVsBuy({ ...input, appreciationPct }).years;
    const l = y[y.length - 1]!;
    return l.buyerWealth - l.renterWealth;
  };
  return {
    emi: sim.emi,
    upfrontCash: roundRupees(sim.upfrontCash),
    years: sim.years,
    winner: Math.abs(difference) < input.price * 0.01 ? "even" : difference > 0 ? "buy" : "rent",
    difference: roundRupees(difference),
    breakevenYear,
    breakevenAppreciationPct: solve(atHorizon, 0, 20),
    totalRentPaid: roundRupees(sim.totalRent),
    totalInterestPaid: roundRupees(sim.totalInterest),
  };
}

// ---------------------------------------------------------------- prepay vs invest

export type PrepayVsInvestInput = {
  outstanding: number;
  loanRatePct: number;
  remainingMonths: number;
  /** One-time amount available today. */
  lumpSum: number;
  investReturnPct: number;
  /** Tax on investment gains when withdrawn, %. */
  taxOnGainsPct: number;
};

export type PrepayVsInvestResult = {
  emi: number;
  /** Prepay and keep the EMI: the loan ends sooner, then the freed EMI is invested. */
  prepay: {
    monthsToClose: number;
    monthsSaved: number;
    interestSaved: number;
    corpusAtOriginalEnd: number;
  };
  /** Keep the loan as it is and invest the lump sum. */
  invest: { corpusAtOriginalEnd: number; gainsTax: number };
  winner: "prepay" | "invest" | "even";
  difference: number;
  /** After-tax return the investment must beat for investing to win; null if outside 0–30%. */
  breakevenReturnPct: number | null;
};

function interestAndMonths(balance: number, emi: number, rl: number, limit: number) {
  let interest = 0;
  let n = 0;
  while (balance > 0.5 && n < limit) {
    const i = balance * rl;
    interest += i;
    balance = balance + i - Math.min(emi, balance + i);
    n++;
  }
  return { interest, months: n };
}

function compare(i: PrepayVsInvestInput, investReturnPct: number) {
  const n = i.remainingMonths;
  const emi = calculateEMI(i.outstanding, i.loanRatePct, n);
  const rl = i.loanRatePct / 12 / 100;
  const r = monthly(investReturnPct);
  const tax = i.taxOnGainsPct / 100;
  const base = interestAndMonths(i.outstanding, emi, rl, n + 1);
  const prepay = Math.min(i.lumpSum, i.outstanding);
  const after = interestAndMonths(i.outstanding - prepay, emi, rl, n + 1);
  // Prepay: the EMI stops `monthsSaved` months early and is invested until the original end.
  const excess = i.lumpSum - prepay; // anything beyond the balance is invested from day one
  let emiStream = 0;
  for (let m = after.months + 1; m <= n; m++) emiStream = emiStream * (1 + r) + emi;
  const grossA = excess * Math.pow(1 + r, n) + emiStream;
  const paidInA = excess + emi * (n - after.months);
  const corpusA = grossA - Math.max(0, grossA - paidInA) * tax;
  const grossB = i.lumpSum * Math.pow(1 + r, n);
  const taxB = Math.max(0, grossB - i.lumpSum) * tax;
  return {
    emi,
    monthsToClose: after.months,
    monthsSaved: n - after.months,
    interestSaved: base.interest - after.interest,
    corpusA,
    corpusB: grossB - taxB,
    taxB,
  };
}

export function prepayVsInvest(input: PrepayVsInvestInput): PrepayVsInvestResult {
  for (const [k, v] of Object.entries(input)) requireNonNegative(k, v);
  if (input.outstanding <= 0) throw new FinanceInputError("outstanding must be more than 0");
  if (!Number.isInteger(input.remainingMonths) || input.remainingMonths < 1)
    throw new FinanceInputError("remainingMonths must be a whole number of months");
  if (input.taxOnGainsPct > 100) throw new FinanceInputError("taxOnGainsPct must be ≤ 100");
  const c = compare(input, input.investReturnPct);
  const difference = c.corpusA - c.corpusB;
  return {
    emi: c.emi,
    prepay: {
      monthsToClose: c.monthsToClose,
      monthsSaved: c.monthsSaved,
      interestSaved: roundRupees(c.interestSaved),
      corpusAtOriginalEnd: roundRupees(c.corpusA),
    },
    invest: { corpusAtOriginalEnd: roundRupees(c.corpusB), gainsTax: roundRupees(c.taxB) },
    winner:
      Math.abs(difference) < input.lumpSum * 0.01 ? "even" : difference > 0 ? "prepay" : "invest",
    difference: roundRupees(difference),
    breakevenReturnPct: solve(
      (x) => {
        const k = compare(input, x);
        return k.corpusB - k.corpusA;
      },
      0,
      30,
    ),
  };
}
