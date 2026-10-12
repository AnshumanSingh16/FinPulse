import { describe, expect, it } from "vitest";

import { interpretGoal } from "./goal";

describe("interpretGoal", () => {
  it("reads a plain goal", () => {
    const g = interpretGoal("I want to buy a ₹75 lakh house.");
    expect(g).toMatchObject({
      type: "house",
      price: 7_500_000,
      label: "₹75 lakh house",
      downPaymentPct: null,
    });
    expect(g.unknown).toEqual([]);
  });
  it("reads stated loan terms without mistaking them for the price", () => {
    const g = interpretGoal("Buy a 20L car with 30% down over 5 years at 9.5%");
    expect(g).toMatchObject({
      type: "car",
      price: 2_000_000,
      downPaymentPct: 30,
      tenureMonths: 60,
      interestRate: 9.5,
    });
  });
  it("says what it could not understand instead of guessing", () => {
    const g = interpretGoal("Should I do an MBA?");
    expect(g.type).toBe("education");
    expect(g.price).toBeNull();
    expect(g.unknown).toContain("the price");
  });
});
