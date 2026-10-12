/**
 * Document intelligence. Uploaded documents are UNTRUSTED input:
 *  - text and CSV files are parsed by deterministic rules (no AI), so instructions hidden in a
 *    document cannot influence anything;
 *  - PDFs are only read when the AI provider is configured, inside an <untrusted_data> wrapper,
 *    with structured output;
 *  - instruction-like text is flagged for the user;
 *  - extracted values are proposals: nothing reaches the profile until the user confirms it.
 */
import { findINRAmounts } from "../finance/parse-inr";
import type { DocumentRecord, ExtractedField } from "../store";

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
export const ACCEPTED_TYPES: Record<string, "text" | "csv" | "pdf"> = {
  "text/plain": "text",
  "text/csv": "csv",
  "application/vnd.ms-excel": "csv",
  "application/pdf": "pdf",
};

export function kindFor(name: string, mime: string): "text" | "csv" | "pdf" | null {
  const ext = name.toLowerCase().split(".").pop();
  if (ext === "txt") return "text";
  if (ext === "csv") return "csv";
  if (ext === "pdf") return "pdf";
  return ACCEPTED_TYPES[mime] ?? null;
}

const INJECTION_RE =
  /(ignore (all |any )?(previous|prior|above) (instructions|prompts)|disregard (the )?(system|previous)|you are now|system prompt|act as (an? )?(assistant|ai)|approve (this|the) (loan|application)|mark (this|the) (document )?as verified)/i;

export function injectionFlags(text: string): DocumentRecord["flags"] {
  return INJECTION_RE.test(text)
    ? [{ severity: "warning", message: "This document contains instruction-like text (e.g. \"ignore previous instructions\"). It was treated as data only and has no effect on FinPulse." }]
    : [];
}

export function classify(text: string): DocumentRecord["docType"] {
  const t = text.toLowerCase();
  if (/(salary slip|pay ?slip|net pay|gross earnings|take home)/.test(t)) return "salary_slip";
  if (/(loan (offer|quotation|sanction)|rate of interest|processing fee|sanction letter)/.test(t)) return "loan_quote";
  if (/(statement of account|bank statement|closing balance|opening balance)/.test(t) || /date,.*(debit|credit|withdrawal|deposit)/.test(t)) return "bank_statement";
  if (/(expense summary|monthly expenses|household budget)/.test(t)) return "expense_summary";
  return "unknown";
}

/** First rupee amount on the first line matching the label pattern. */
function amountAfter(text: string, label: RegExp): { value: number; line: string } | null {
  for (const line of text.split(/\r?\n/)) {
    if (!label.test(line)) continue;
    const afterLabel = line.slice(line.search(label));
    const amt = findINRAmounts(afterLabel).find((a) => a.value >= 100);
    if (amt) return { value: amt.value, line: line.trim().slice(0, 160) };
  }
  return null;
}

function numberAfter(text: string, label: RegExp): { value: number; line: string } | null {
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(label);
    if (m?.[1]) return { value: Number(m[1]), line: line.trim().slice(0, 160) };
  }
  return null;
}

function fromText(text: string, docType: DocumentRecord["docType"]): ExtractedField[] {
  const fields: ExtractedField[] = [];
  const push = (key: string, label: string, hit: { value: number; line: string } | null, profileField?: string, confidence: ExtractedField["confidence"] = "high") => {
    if (hit) fields.push({ key, label, value: hit.value, confidence, evidence: hit.line, profileField });
  };
  if (docType === "salary_slip") {
    push("net_pay", "Net monthly pay", amountAfter(text, /net (pay|salary)|take[- ]home/i), "monthlyIncome");
    push("gross_pay", "Gross monthly earnings", amountAfter(text, /gross (earnings|pay|salary)/i));
    push("tds", "Income tax deducted (TDS)", amountAfter(text, /\b(tds|income tax)\b/i), undefined, "medium");
    const employer = text.match(/(?:employer|company)\s*[:\-]\s*(.+)/i);
    if (employer?.[1]) fields.push({ key: "employer", label: "Employer", value: employer[1].trim().slice(0, 80), confidence: "high", evidence: employer[0].trim().slice(0, 160) });
  } else if (docType === "loan_quote") {
    push("loan_amount", "Loan amount offered", amountAfter(text, /loan amount|sanctioned amount/i));
    push("rate", "Interest rate (% p.a.)", numberAfter(text, /(?:rate of interest|interest rate|roi)[^\d]*(\d{1,2}(?:\.\d+)?)\s*%/i));
    push("tenure", "Tenure (months)", numberAfter(text, /tenure[^\d]*(\d{1,3})\s*months/i));
    push("processing_fee", "Processing fee", amountAfter(text, /processing fee/i), undefined, "medium");
    push("emi", "Quoted EMI", amountAfter(text, /\bemi\b/i), undefined, "medium");
  } else if (docType === "expense_summary") {
    push("monthly_expenses", "Total monthly expenses", amountAfter(text, /total (monthly )?expenses|total spend/i), "monthlyExpenses");
  }
  return fields;
}

/** Bank statement CSV: average monthly credits and debits, last balance. */
function fromCsv(text: string): { fields: ExtractedField[]; docType: DocumentRecord["docType"]; note: string } {
  const rows = text.split(/\r?\n/).map((l) => l.split(",").map((c) => c.trim().replace(/^"|"$/g, ""))).filter((r) => r.length > 1);
  const header = rows[0]?.map((h) => h.toLowerCase()) ?? [];
  const col = (re: RegExp) => header.findIndex((h) => re.test(h));
  const iDate = col(/date/);
  const iDebit = col(/debit|withdrawal/);
  const iCredit = col(/credit|deposit/);
  const iBal = col(/balance/);
  if (iDate < 0 || (iDebit < 0 && iCredit < 0)) {
    return { fields: [], docType: "unknown", note: "CSV columns not recognised (need Date and Debit/Credit columns)." };
  }
  const num = (s: string | undefined) => {
    const n = Number((s ?? "").replace(/[₹,\s]/g, ""));
    return Number.isFinite(n) ? n : 0;
  };
  const months = new Map<string, { credit: number; debit: number }>();
  let lastBalance: number | null = null;
  for (const r of rows.slice(1)) {
    const d = r[iDate] ?? "";
    const m = d.match(/(\d{4})-(\d{2})/) ?? d.match(/\d{1,2}[/-](\d{1,2})[/-](\d{4})/);
    const key = m ? (m[0].includes("-") && m[1]!.length === 4 ? `${m[1]}-${m[2]}` : `${m[2]}-${m[1]!.padStart(2, "0")}`) : "unknown";
    const e = months.get(key) ?? { credit: 0, debit: 0 };
    e.credit += iCredit >= 0 ? num(r[iCredit]) : 0;
    e.debit += iDebit >= 0 ? num(r[iDebit]) : 0;
    months.set(key, e);
    if (iBal >= 0 && r[iBal]) lastBalance = num(r[iBal]);
  }
  const n = Math.max(1, months.size);
  const credits = [...months.values()].reduce((s, x) => s + x.credit, 0) / n;
  const debits = [...months.values()].reduce((s, x) => s + x.debit, 0) / n;
  const fields: ExtractedField[] = [
    { key: "avg_credits", label: "Average monthly credits", value: Math.round(credits), confidence: "medium", evidence: `${rows.length - 1} transactions over ${months.size} month(s)`, profileField: "monthlyIncome" },
    { key: "avg_debits", label: "Average monthly debits (all outflows, incl. EMIs)", value: Math.round(debits), confidence: "low", evidence: "Includes transfers and EMIs, so not the same as living expenses" },
  ];
  if (lastBalance !== null) fields.push({ key: "closing_balance", label: "Closing balance", value: Math.round(lastBalance), confidence: "high", evidence: "Last row's balance", profileField: "liquidSavings" });
  return { fields, docType: "bank_statement", note: `Parsed ${rows.length - 1} rows across ${months.size} month(s).` };
}

export function extractFromText(name: string, kind: "text" | "csv", text: string): Pick<DocumentRecord, "docType" | "extraction" | "flags"> {
  const flags = injectionFlags(text);
  if (kind === "csv") {
    const r = fromCsv(text);
    return {
      docType: r.docType,
      flags,
      extraction: { status: r.fields.length ? "extracted" : "not_extracted", method: "rule_based_text", note: r.note, fields: r.fields },
    };
  }
  const docType = classify(text);
  const fields = fromText(text, docType);
  return {
    docType,
    flags,
    extraction: {
      status: fields.length === 0 ? "not_extracted" : "extracted",
      method: "rule_based_text",
      note:
        docType === "unknown"
          ? `Could not tell what kind of document "${name}" is; no fields extracted. Enter the figures manually on the profile page.`
          : `Recognised as a ${docType.replace("_", " ")}; ${fields.length} field(s) found by rule-based parsing.`,
      fields,
    },
  };
}
