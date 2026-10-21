"use client";

import { CheckCircle2, FileText, Landmark, Printer, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { CatIcon } from "@/components/cat";
import { Button, Card, cx, Loading, Pill, Segmented, SectionTitle } from "@/components/ui";
import { useApi } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";

interface Monthly {
  status: string;
  message?: string;
  business: string;
  label: string;
  period: string[];
  summary: { revenue: number; operating_expenses: number; estimated_operating_profit: number; estimated_margin_pct: number | null; total_inflows: number; total_outflows: number; net_cash_movement: number };
  other_flows: Record<string, number>;
  expenses_by_category: Record<string, number>;
  opening_balance: number | null;
  closing_balance: number | null;
  top_customers: { name: string; amount: number }[];
  top_suppliers: { name: string; amount: number }[];
  receivables: { pending_not_due: number; overdue: number; overdue_by_age: Record<string, number> } | null;
  payables: { pending_not_due: number; overdue: number } | null;
  gst: { output_gst: number; input_credit: number; estimated_payable: number; gst_paid_in_period: number; sales_incl_gst: number; purchases_incl_gst: number };
  transactions: number;
}
interface Loan {
  status: string;
  message?: string;
  business: string;
  period: string[];
  avg_monthly_sales: number;
  avg_monthly_profit: number;
  avg_monthly_emi: number;
  avg_month_end_balance: number | null;
  sales_growth_pct: number | null;
  checks: { key: string; label: string; value: number | null; ok: boolean; target: string }[];
  passed: number;
  level: "strong" | "fair" | "weak";
  monthly: { label: string; sales: number; profit: number }[];
  documents: string[];
}

export default function ReportsPage() {
  const { t } = useT();
  const [kind, setKind] = useState<"monthly" | "loan">("monthly");
  const months = useApi<{ key: string; label: string }[]>("/api/reports/months");
  const [month, setMonth] = useState("");
  useEffect(() => {
    if (!month && months.data?.length) setMonth(months.data[0].key);
  }, [months.data, month]);
  return (
    <div className="space-y-5">
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl">{t("Reports")}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            value={kind}
            onChange={setKind}
            options={[
              { value: "monthly", label: "Monthly report (CA)" },
              { value: "loan", label: "Loan readiness (bank)" },
            ]}
          />
          {kind === "monthly" && (
            <select value={month} onChange={(e) => setMonth(e.target.value)} className="h-10 rounded-full border border-line bg-surface px-4 text-sm" aria-label="Month">
              {months.data?.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          )}
          <Button onClick={() => window.print()}>
            <Printer className="size-4" /> Print / Save PDF
          </Button>
        </div>
      </div>
      <p className="no-print text-sm text-muted">Tip: in the print dialog choose “Save as PDF” to share it on WhatsApp or email.</p>
      {kind === "monthly" ? month && <MonthlyReport month={month} /> : <LoanReport />}
    </div>
  );
}

function Row({ label, value, strong, tone }: { label: string; value: string; strong?: boolean; tone?: "good" | "bad" }) {
  return (
    <div className={cx("flex justify-between py-2 text-sm", strong && "font-semibold")}>
      <span className="text-ink-2">{label}</span>
      <span className={cx("num", tone === "good" && "text-good", tone === "bad" && "text-bad")}>{value}</span>
    </div>
  );
}

function Header({ title, sub, business, I }: { title: string; sub: string; business: string; I: React.ElementType }) {
  return (
    <div className="grad-hero print-page flex items-center justify-between gap-4 rounded-[1.5rem] p-6">
      <div>
        <p className="text-sm text-white/80">{business.replace(" (fictional)", "")}</p>
        <h2 className="text-2xl font-bold">{title}</h2>
        <p className="text-sm text-white/80">{sub}</p>
      </div>
      <span className="glass grid size-14 place-items-center rounded-2xl">
        <I className="size-7" />
      </span>
    </div>
  );
}

function MonthlyReport({ month }: { month: string }) {
  const { data } = useApi<Monthly>(`/api/reports/monthly?month=${month}`);
  if (!data) return <Loading />;
  if (data.status !== "ok") return <Card className="text-ink-2">{data.message}</Card>;
  const s = data.summary;
  const cats = Object.entries(data.expenses_by_category).sort((a, b) => b[1] - a[1]);
  return (
    <div className="space-y-4">
      <Header title={`Monthly report · ${data.label}`} sub={`${data.period[0]} to ${data.period[1]} · ${data.transactions} transactions`} business={data.business} I={FileText} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="print-page">
          <SectionTitle>Profit and loss (cash basis, estimate)</SectionTitle>
          <Row label="Sales received" value={inr(s.revenue)} />
          <Row label="Running costs paid" value={inr(s.operating_expenses)} />
          <div className="my-1 h-px bg-line" />
          <Row label="Net operating cash difference (not accounting profit)" value={inr(s.estimated_operating_profit)} strong tone={s.estimated_operating_profit < 0 ? "bad" : "good"} />
          {s.estimated_margin_pct != null && <Row label="Margin" value={`${s.estimated_margin_pct.toFixed(1)}%`} />}
        </Card>
        <Card className="print-page">
          <SectionTitle>Bank & cash</SectionTitle>
          <Row label="Opening balance" value={data.opening_balance != null ? inr(data.opening_balance) : "—"} />
          <Row label="All money in" value={inr(s.total_inflows)} />
          <Row label="All money out" value={inr(s.total_outflows)} />
          <div className="my-1 h-px bg-line" />
          <Row label="Closing balance" value={data.closing_balance != null ? inr(data.closing_balance) : "—"} strong />
          <p className="mt-1 text-xs text-muted">
            Not running costs: assets {inr(data.other_flows.capex)}, loan EMIs {inr(data.other_flows.loan_repayments)}, drawings {inr(data.other_flows.owner_drawings)}, GST/TDS {inr(data.other_flows.tax_remitted)}
          </p>
        </Card>
        <Card className="print-page">
          <SectionTitle>Costs by category</SectionTitle>
          <ul className="space-y-2">
            {cats.map(([c, v]) => (
              <li key={c} className="flex items-center gap-3 text-sm">
                <CatIcon category={c} size="sm" />
                <span className="flex-1">{c}</span>
                <span className="num font-medium">{inr(v)}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="print-page">
          <SectionTitle>GST estimate (to set aside)</SectionTitle>
          <Row label="Sales incl. GST" value={inr(data.gst.sales_incl_gst)} />
          <Row label="Output GST" value={inr(data.gst.output_gst)} />
          <Row label="Input credit (purchases)" value={inr(data.gst.input_credit)} />
          <div className="my-1 h-px bg-line" />
          <Row label="Estimated GST payable" value={inr(data.gst.estimated_payable)} strong />
          <Row label="GST actually paid this month" value={inr(data.gst.gst_paid_in_period)} />
          <p className="mt-1 text-xs text-muted">An estimate at one rate — not a return. Your CA&apos;s figures take precedence.</p>
        </Card>
        <Card className="print-page">
          <SectionTitle>Top customers</SectionTitle>
          {data.top_customers.map((c) => (
            <Row key={c.name} label={c.name} value={inr(c.amount)} />
          ))}
        </Card>
        <Card className="print-page">
          <SectionTitle>Owed at month end</SectionTitle>
          {data.receivables ? (
            <>
              <Row label="Customers owe (not yet due)" value={inr(data.receivables.pending_not_due)} />
              <Row label="Customers owe (overdue)" value={inr(data.receivables.overdue)} tone={data.receivables.overdue ? "bad" : undefined} />
              <Row label="You owe suppliers" value={inr((data.payables?.pending_not_due ?? 0) + (data.payables?.overdue ?? 0))} />
            </>
          ) : (
            <p className="text-sm text-muted">No invoices recorded.</p>
          )}
        </Card>
      </div>
      <p className="text-xs text-muted">Prepared with FinPilot from the owner&apos;s own records on a cash basis. Not audited. Profit excludes depreciation, accruals and the interest inside loan EMIs.</p>
    </div>
  );
}

function LoanReport() {
  const { data } = useApi<Loan>("/api/reports/loan");
  if (!data) return <Loading />;
  if (data.status !== "ok") return <Card className="text-ink-2">{data.message}</Card>;
  const grad = data.level === "strong" ? "grad-mint" : data.level === "fair" ? "grad-sunset" : "grad-hero-bad";
  const max = Math.max(...data.monthly.map((m) => m.sales), 1);
  return (
    <div className="space-y-4">
      <Header title="Loan readiness summary" sub={`${data.period[0]} to ${data.period[1]}`} business={data.business} I={Landmark} />
      <div className={cx("print-page rounded-[1.5rem] p-6", grad)}>
        <p className="text-sm text-white/85">Readiness</p>
        <p className="text-3xl font-bold capitalize">
          {data.level} · {data.passed}/6 checks
        </p>
        <p className="mt-1 text-sm text-white/85">An indicative self-check, not a credit decision. Lenders use their own criteria.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        {[
          ["Avg monthly sales", short(data.avg_monthly_sales)],
          ["Avg monthly profit (est.)", short(data.avg_monthly_profit)],
          ["Existing EMIs / month", short(data.avg_monthly_emi)],
          ["Avg month-end balance", data.avg_month_end_balance != null ? short(data.avg_month_end_balance) : "—"],
        ].map(([l, v]) => (
          <Card key={l} className="print-page p-4">
            <p className="text-sm text-ink-2">{l}</p>
            <p className="num text-xl font-bold">{v}</p>
          </Card>
        ))}
      </div>
      <Card className="print-page">
        <SectionTitle>Checks a lender looks at</SectionTitle>
        <ul className="divide-y divide-line">
          {data.checks.map((c) => (
            <li key={c.key} className="flex items-center gap-3 py-3">
              {c.ok ? <CheckCircle2 className="size-5 shrink-0 text-good" /> : <XCircle className="size-5 shrink-0 text-bad" />}
              <div className="flex-1">
                <p className="text-sm font-medium">{c.label}</p>
                <p className="text-xs text-muted">Target: {c.target}</p>
              </div>
              <Pill tone={c.ok ? "good" : "bad"}>
                {c.value == null ? "—" : c.key === "profit" || c.key === "balance" ? short(c.value) : c.key === "history" ? `${c.value} months` : c.key === "cover" ? `${c.value}×` : `${c.value}%`}
              </Pill>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="print-page">
        <SectionTitle>Sales and profit by month</SectionTitle>
        <ul className="space-y-2">
          {data.monthly.map((m) => (
            <li key={m.label} className="grid grid-cols-[4rem_1fr_6rem] items-center gap-3 text-sm">
              <span>{m.label}</span>
              <div className="h-2.5 rounded-full bg-in" style={{ width: `${(m.sales / max) * 100}%` }} />
              <span className={cx("num text-right", m.profit < 0 && "text-bad")}>{short(m.profit)}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="print-page">
        <SectionTitle>Documents to keep ready</SectionTitle>
        <ul className="grid gap-2 sm:grid-cols-2">
          {data.documents.map((d) => (
            <li key={d} className="flex items-center gap-2 text-sm">
              <span className="size-1.5 rounded-full bg-brand" /> {d}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
