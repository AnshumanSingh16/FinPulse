import { describe, expect, it } from "vitest";

import {
  formatAxis,
  formatDate,
  formatINR,
  formatMetric,
  formatMonthShort,
  formatPercent,
  toNumber,
} from "./format";

describe("format", () => {
  it("parses decimal strings", () => {
    expect(toNumber("689747.00")).toBe(689747);
    expect(toNumber(null)).toBeNull();
    expect(toNumber("x")).toBeNull();
  });

  it("formats rupees with Indian grouping and compact lakh/crore", () => {
    expect(formatINR("1097992.00")).toBe("₹10,97,992");
    expect(formatINR("-168038")).toBe("−₹1,68,038");
    expect(formatINR(689747, { compact: true })).toBe("₹6.9L");
    expect(formatINR(12_000_000, { compact: true })).toBe("₹1.2Cr");
    expect(formatINR(48_000, { compact: true })).toBe("₹48K");
    expect(formatINR(1200, { signed: true })).toBe("+₹1,200");
    expect(formatINR(undefined)).toBe("—");
  });

  it("formats ratios, multiples and units", () => {
    expect(formatPercent("0.5919")).toBe("59.2%");
    expect(formatPercent("-0.2", { digits: 0, signed: true })).toBe("−20%");
    expect(formatMetric("0.4264", "ratio", { code: "liquidity.ratio" })).toBe("0.43×");
    expect(formatMetric("0.4264", "ratio")).toBe("42.6%");
    expect(formatMetric("47.8", "days")).toBe("47.8 days");
    expect(formatMetric("0.4", "months")).toBe("0.4 mo");
    expect(formatMetric("2", "count")).toBe("2");
    expect(formatAxis(0.25, "ratio")).toBe("25%");
  });

  it("formats dates without time-zone drift", () => {
    expect(formatDate("2026-09-30")).toBe("30 Sep 2026");
    expect(formatMonthShort("2026-01-31")).toBe("Jan ’26");
  });
});
