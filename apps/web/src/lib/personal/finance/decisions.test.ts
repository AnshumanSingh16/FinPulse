import { describe, expect, it } from "vitest";

import { prepayVsInvest, rentVsBuy, type RentVsBuyInput } from "./decisions";
import { calculateEMI } from "./loan";

describe("prepayVsInvest", () => {
  const base = {
    outstanding: 4_000_000,
    loanRatePct: 8.5,
    remainingMonths: 180,
    lumpSum: 500_000,
    taxOnGainsPct: 0,
  };

  it("prepaying wins when investments earn nothing", () => {
    const r = prepayVsInvest({ ...base, investReturnPct: 0 });
    expect(r.emi).toBe(calculateEMI(4_000_000, 8.5, 180));
    expect(r.winner).toBe("prepay");
    expect(r.prepay.monthsSaved).toBeGreaterThan(0);
    expect(r.prepay.interestSaved).toBeGreaterThan(0);
    expect(r.invest.corpusAtOriginalEnd).toBe(500_000);
  });

  it("investing wins when returns are well above the loan rate", () => {
    expect(prepayVsInvest({ ...base, investReturnPct: 14 }).winner).toBe("invest");
  });

  it("breaks even near the loan rate when gains are untaxed", () => {
    const r = prepayVsInvest({ ...base, investReturnPct: 10 });
    expect(r.breakevenReturnPct).not.toBeNull();
    expect(Math.abs(r.breakevenReturnPct! - 8.5)).toBeLessThan(0.6);
  });

  it("tax on gains raises the return investing needs", () => {
    const untaxed = prepayVsInvest({ ...base, investReturnPct: 10 }).breakevenReturnPct!;
    const taxed = prepayVsInvest({
      ...base,
      investReturnPct: 10,
      taxOnGainsPct: 12.5,
    }).breakevenReturnPct!;
    expect(taxed).toBeGreaterThan(untaxed);
  });

  it("a lump sum bigger than the balance closes the loan", () => {
    const r = prepayVsInvest({ ...base, lumpSum: 5_000_000, investReturnPct: 8 });
    expect(r.prepay.monthsToClose).toBe(0);
    expect(r.prepay.monthsSaved).toBe(180);
  });

  it("rejects bad input", () => {
    expect(() => prepayVsInvest({ ...base, outstanding: 0, investReturnPct: 8 })).toThrow();
    expect(() => prepayVsInvest({ ...base, remainingMonths: 1.5, investReturnPct: 8 })).toThrow();
  });
});

describe("rentVsBuy", () => {
  const base: RentVsBuyInput = {
    price: 7_500_000,
    downPaymentPct: 20,
    upfrontCostPct: 7,
    loanRatePct: 8.5,
    tenureMonths: 240,
    monthlyRent: 22_000,
    rentGrowthPct: 5,
    appreciationPct: 5,
    ownershipCostPct: 0.5,
    investReturnPct: 10,
    years: 15,
  };

  it("returns a year-by-year comparison with the EMI and day-one cash", () => {
    const r = rentVsBuy(base);
    expect(r.years).toHaveLength(15);
    expect(r.emi).toBe(calculateEMI(6_000_000, 8.5, 240));
    expect(r.upfrontCash).toBe(2_025_000);
    expect(r.difference).toBe(r.years[14]!.buyerWealth - r.years[14]!.renterWealth);
  });

  it("buying wins when prices rise fast and rent is high", () => {
    expect(rentVsBuy({ ...base, appreciationPct: 12, monthlyRent: 45_000 }).winner).toBe("buy");
  });

  it("renting wins when rent is cheap and prices are flat", () => {
    const r = rentVsBuy({ ...base, appreciationPct: 0, monthlyRent: 12_000 });
    expect(r.winner).toBe("rent");
    expect(r.breakevenYear).toBeNull();
  });

  it("the break-even appreciation levels the two at the horizon", () => {
    const r = rentVsBuy(base);
    expect(r.breakevenAppreciationPct).not.toBeNull();
    const level = rentVsBuy({ ...base, appreciationPct: r.breakevenAppreciationPct! });
    expect(Math.abs(level.difference)).toBeLessThan(base.price * 0.01);
  });
});
