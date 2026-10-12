import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { extractFromText, kindFor } from "./extract";

const sample = (name: string) => readFileSync(path.resolve(__dirname, "../../../../public/samples", name), "utf8");

describe("document extraction (rule-based)", () => {
  it("reads a salary slip and flags embedded instructions", () => {
    const r = extractFromText("slip.txt", "text", sample("salary-slip-demo.txt"));
    expect(r.docType).toBe("salary_slip");
    const net = r.extraction.fields.find((f) => f.key === "net_pay");
    expect(net?.value).toBe(185_000);
    expect(net?.profileField).toBe("monthlyIncome");
    expect(r.extraction.fields.find((f) => f.key === "gross_pay")?.value).toBe(226_500);
    expect(r.flags).toHaveLength(1);
  });
  it("reads a bank statement CSV", () => {
    const r = extractFromText("stmt.csv", "csv", sample("bank-statement-demo.csv"));
    expect(r.docType).toBe("bank_statement");
    expect(r.extraction.fields.find((f) => f.key === "avg_credits")?.value).toBe(185_000);
    expect(r.extraction.fields.find((f) => f.key === "closing_balance")?.value).toBe(2_500_000);
  });
  it("reads a loan quotation", () => {
    const r = extractFromText("quote.txt", "text", sample("loan-quote-demo.txt"));
    expect(r.docType).toBe("loan_quote");
    expect(r.extraction.fields.find((f) => f.key === "rate")?.value).toBe(8.75);
    expect(r.extraction.fields.find((f) => f.key === "tenure")?.value).toBe(240);
    expect(r.extraction.fields.find((f) => f.key === "loan_amount")?.value).toBe(6_000_000);
  });
  it("does not invent fields for unknown documents", () => {
    const r = extractFromText("x.txt", "text", "Hello there. Nothing financial here.");
    expect(r.docType).toBe("unknown");
    expect(r.extraction.status).toBe("not_extracted");
    expect(r.extraction.fields).toEqual([]);
  });
  it("accepts only supported file kinds", () => {
    expect(kindFor("a.pdf", "application/pdf")).toBe("pdf");
    expect(kindFor("a.exe", "application/octet-stream")).toBeNull();
  });
});
