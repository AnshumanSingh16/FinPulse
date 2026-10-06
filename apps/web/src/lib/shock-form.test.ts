import { describe, expect, it } from "vitest";

import { fieldsOf, initialInputs, missing, shockPayload } from "./shock-form";

// The shape served by GET /api/v1/meta/stress-scenarios for revenue_decline.
const SCHEMA = {
  properties: {
    type: { const: "revenue_decline", type: "string" },
    start_month: { default: 1, minimum: 1, maximum: 24, title: "Start Month", type: "integer" },
    duration_months: {
      anyOf: [{ type: "integer", minimum: 1 }, { type: "null" }],
      default: null,
      title: "Duration Months",
    },
    decline_pct: {
      anyOf: [{ type: "number" }, { type: "string" }],
      title: "Decline Pct",
      description: "0.2 = 20%",
    },
    costs_follow_revenue: { default: true, type: "boolean", title: "Costs Follow Revenue" },
    customer_id: { anyOf: [{ type: "string", format: "uuid" }, { type: "null" }], default: null },
  },
  required: ["type", "decline_pct"],
};

describe("shock form", () => {
  const fields = fieldsOf(SCHEMA);

  it("derives field kinds from the schema", () => {
    expect(fields.map((f) => [f.key, f.kind, f.required])).toEqual([
      ["start_month", "integer", false],
      ["duration_months", "integer", false],
      ["decline_pct", "percent", true],
      ["costs_follow_revenue", "boolean", false],
      ["customer_id", "uuid", false],
    ]);
    expect(fields[2]!.label).toBe("Decline");
  });

  it("round-trips preset parameters through the form", () => {
    const inputs = initialInputs(fields, { decline_pct: "0.20" });
    expect(inputs.decline_pct).toBe("20");
    expect(inputs.start_month).toBe("1");
    expect(inputs.duration_months).toBe("");
    expect(shockPayload("revenue_decline", fields, { ...inputs, decline_pct: "35" })).toEqual({
      type: "revenue_decline",
      start_month: 1,
      decline_pct: "0.35",
      costs_follow_revenue: true,
    });
  });

  it("reports missing required values", () => {
    expect(missing(fields, initialInputs(fields))).toEqual(["Decline"]);
  });
});
