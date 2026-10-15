"use client";

import { ArrowDownLeft, ArrowUpRight, Check, MessageCircle, Plus, Search, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { EvidenceButton } from "@/components/evidence";
import { ReminderSheet } from "@/components/reminder";
import { Button, Card, cx, ErrorNote, Loading, Pill, Segmented, SectionTitle } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { inr, short } from "@/lib/format";
import type { Evidence, OwedGroup, Txn } from "@/lib/types";

type Tab = "activity" | "owed" | "bills" | "profit";

export default function MoneyPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Money />
    </Suspense>
  );
}

function Money() {
  const params = useSearchParams();
  const router = useRouter();
  const initial = (params.get("tab") as Tab) || "activity";
  const [tab, setTab] = useState<Tab>(initial);
  useEffect(() => setTab((params.get("tab") as Tab) || "activity"), [params]);
  const change = (t: Tab) => {
    setTab(t);
    router.replace(t === "activity" ? "/money/" : `/money/?tab=${t}`, { scroll: false });
  };
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Money</h1>
      <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <Segmented<Tab>
          value={tab}
          onChange={change}
          options={[
            { value: "activity", label: "Transactions" },
            { value: "owed", label: "Who owes you" },
            { value: "bills", label: "Bills to pay" },
            { value: "profit", label: "Profit by month" },
          ]}
        />
      </div>
      {tab === "activity" && <Activity ids={params.get("ids") ?? ""} dir={params.get("dir") ?? ""} />}
      {tab === "owed" && <Owed side="customers" />}
      {tab === "bills" && <Owed side="suppliers" />}
      {tab === "profit" && <Profit />}
    </div>
  );
}

interface TxnPage {
  total: number;
  money_in: number;
  money_out: number;
  categories: string[];
  rows: Txn[];
}

function Activity({ ids, dir: initialDir }: { ids: string; dir: string }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [dir, setDir] = useState<"" | "in" | "out">((initialDir as "in" | "out") || "");
  const [cat, setCat] = useState("");
  const [limit, setLimit] = useState(60);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 250);
    return () => clearTimeout(t);
  }, [q]);
  const path = `/api/transactions?${new URLSearchParams({ q: query, direction: dir, category: cat, ids, limit: String(limit) })}`;
  const { data, error, loading, reload } = useApi<TxnPage>(path);

  const groups = useMemo(() => {
    const g: { day: string; rows: Txn[] }[] = [];
    for (const r of data?.rows ?? []) {
      const last = g[g.length - 1];
      if (last && last.day === r.day) last.rows.push(r);
      else g.push({ day: r.day, rows: [r] });
    }
    return g;
  }, [data]);

  if (error) return <ErrorNote message={error} retry={reload} />;
  return (
    <div className="space-y-4">
      {ids && (
        <div className="flex items-center justify-between gap-3 rounded-2xl bg-caution-50 px-4 py-3 text-sm">
          <span>Showing the {ids.split(",").length} payments to review. Compare them with your bank statement or ask the supplier.</span>
          <Button size="sm" variant="secondary" onClick={() => router.replace("/money/")}>
            Show all
          </Button>
        </div>
      )}
      {!ids && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-full border border-line bg-surface px-4 focus-within:border-brand sm:max-w-xs">
            <Search className="size-4 text-muted" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, item…" className="w-full bg-transparent text-sm outline-none" aria-label="Search transactions" />
            {q && (
              <button onClick={() => setQ("")} aria-label="Clear search">
                <X className="size-4 text-muted" />
              </button>
            )}
          </div>
          <Segmented<"" | "in" | "out">
            value={dir}
            onChange={setDir}
            options={[
              { value: "", label: "All" },
              { value: "in", label: "Money in" },
              { value: "out", label: "Money out" },
            ]}
          />
          <select value={cat} onChange={(e) => setCat(e.target.value)} className="h-10 rounded-full border border-line bg-surface px-4 text-sm" aria-label="Category">
            <option value="">All categories</option>
            {data?.categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
      )}
      {data && (
        <div className="grid grid-cols-3 gap-3">
          <Card className="p-4">
            <p className="text-xs text-ink-2">Money in</p>
            <p className="num text-lg font-semibold text-good">{short(data.money_in)}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs text-ink-2">Money out</p>
            <p className="num text-lg font-semibold">{short(data.money_out)}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs text-ink-2">Transactions</p>
            <p className="num text-lg font-semibold">{data.total.toLocaleString("en-IN")}</p>
          </Card>
        </div>
      )}
      {loading && !data ? (
        <Loading />
      ) : groups.length === 0 ? (
        <Card className="text-center text-ink-2">No transactions match.</Card>
      ) : (
        <Card className="p-0">
          {groups.map((g) => (
            <div key={g.day}>
              <p className="sticky top-14 z-10 bg-surface/95 px-5 pt-4 pb-1 text-xs font-semibold tracking-wide text-muted uppercase backdrop-blur lg:top-0">{g.day}</p>
              <ul>
                {g.rows.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-5 py-2.5">
                    <span className={cx("grid size-9 shrink-0 place-items-center rounded-full", r.direction === "in" ? "bg-good-50 text-good" : "bg-canvas text-ink-2")}>
                      {r.direction === "in" ? <ArrowDownLeft className="size-4" /> : <ArrowUpRight className="size-4" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{r.party !== "Unknown" ? r.party : r.description}</p>
                      <p className="truncate text-xs text-muted">
                        {r.category} · {r.description}
                      </p>
                    </div>
                    <span className={cx("num shrink-0 font-medium", r.direction === "in" && "text-good")}>
                      {r.direction === "in" ? "+" : "−"}
                      {inr(r.amount)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {data && data.total > data.rows.length && (
            <div className="p-4 text-center">
              <Button variant="secondary" onClick={() => setLimit((l) => l + 100)}>
                Show more ({data.total - data.rows.length} left)
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

interface OwedResp {
  status: string;
  message?: string;
  customers: { total: number; overdue: number; groups: OwedGroup[] };
  suppliers: { total: number; overdue: number; groups: OwedGroup[] };
  evidence: Evidence;
}

function Owed({ side }: { side: "customers" | "suppliers" }) {
  const { data, error, loading, reload } = useApi<OwedResp>("/api/owed");
  const [remind, setRemind] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  if (error) return <ErrorNote message={error} retry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  if (data.status !== "ok")
    return (
      <Card className="text-ink-2">
        {data.message}{" "}
        <a href="/data/" className="font-medium text-brand">
          Add invoices →
        </a>
      </Card>
    );
  const part = data[side];
  const customers = side === "customers";
  const addTodo = async (g: OwedGroup) => {
    await post("/api/todos", { text: `Pay ${g.name} ${inr(g.overdue || g.total)}`, reason: `${g.items.length} bill(s)` });
    setAdded((a) => ({ ...a, [g.name]: true }));
  };
  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-ink-2">{customers ? "Customers owe you" : "You owe suppliers"}</p>
          <p className="num text-3xl font-semibold tracking-tight">{short(part.total)}</p>
        </div>
        {part.overdue > 0 ? (
          <Pill tone={customers ? "bad" : "caution"} className="text-sm">
            {short(part.overdue)} overdue
          </Pill>
        ) : (
          <Pill tone="good" className="text-sm">
            Nothing overdue
          </Pill>
        )}
      </Card>
      {part.groups.length === 0 && <Card className="text-ink-2">Nothing pending.</Card>}
      {part.groups.map((g) => (
        <Card key={g.name}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-[1.05rem] font-semibold">{g.name}</p>
              <p className="text-sm text-ink-2">
                <span className="num font-medium text-ink">{inr(g.total)}</span> pending
                {g.overdue > 0 && (
                  <>
                    {" · "}
                    <span className="num font-medium text-bad">{inr(g.overdue)} overdue</span>
                  </>
                )}
              </p>
            </div>
            {g.overdue > 0 &&
              (customers ? (
                <Button size="sm" onClick={() => setRemind(g.name)}>
                  <MessageCircle className="size-4" /> Draft reminder
                </Button>
              ) : (
                <Button size="sm" variant={added[g.name] ? "secondary" : "primary"} onClick={() => addTodo(g)} disabled={added[g.name]}>
                  {added[g.name] ? <Check className="size-4" /> : <Plus className="size-4" />} {added[g.name] ? "In your to-dos" : "Add to to-dos"}
                </Button>
              ))}
          </div>
          <ul className="mt-3 divide-y divide-line rounded-2xl border border-line">
            {g.items.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{i.what || i.id}</p>
                  <p className="text-xs text-muted">
                    {i.id} · due {i.due_label}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {i.state === "overdue" ? <Pill tone="bad">{i.days_late}d late</Pill> : i.state === "due_soon" ? <Pill tone="caution">in {i.days_left}d</Pill> : null}
                  <span className="num font-medium">{inr(i.amount)}</span>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ))}
      <EvidenceButton evidence={data.evidence} />
      <ReminderSheet customer={remind} onClose={() => setRemind(null)} />
    </div>
  );
}

interface Report {
  status: string;
  message?: string;
  period: string;
  totals: { sales: number; costs: number; profit: number; margin_pct: number | null };
  months: { month: string; sales: number; costs: number; profit: number; cash_change: number }[];
  outside_profit: { label: string; amount: number }[];
  evidence: Evidence;
}

function Profit() {
  const { data, error, loading, reload } = useApi<Report>("/api/report");
  if (error) return <ErrorNote message={error} retry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  if (data.status !== "ok") return <Card className="text-ink-2">{data.message}</Card>;
  return (
    <div className="space-y-4">
      <Card>
        <p className="text-sm text-ink-2">{data.period}</p>
        <div className="mt-3 grid grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-ink-2">Sales received</p>
            <p className="num text-xl font-semibold">{short(data.totals.sales)}</p>
          </div>
          <div>
            <p className="text-sm text-ink-2">Running costs</p>
            <p className="num text-xl font-semibold">{short(data.totals.costs)}</p>
          </div>
          <div>
            <p className="text-sm text-ink-2">
              Profit <span className="text-xs text-muted">(est.)</span>
            </p>
            <p className={cx("num text-xl font-semibold", data.totals.profit < 0 ? "text-bad" : "text-good")}>{short(data.totals.profit)}</p>
            {data.totals.margin_pct != null && <p className="text-xs text-muted">{data.totals.margin_pct.toFixed(0)}p of every ₹1 of sales</p>}
          </div>
        </div>
        <EvidenceButton evidence={data.evidence} label="How is profit worked out?" className="mt-4" />
      </Card>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[32rem] text-sm">
          <thead>
            <tr className="text-left text-xs text-muted uppercase tracking-wide">
              <th className="px-5 py-3 font-semibold">Month</th>
              <th className="px-3 py-3 text-right font-semibold">Sales</th>
              <th className="px-3 py-3 text-right font-semibold">Running costs</th>
              <th className="px-5 py-3 text-right font-semibold">Profit (est.)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.months.map((m) => (
              <tr key={m.month}>
                <td className="px-5 py-3 font-medium">{m.month}</td>
                <td className="num px-3 py-3 text-right">{inr(m.sales)}</td>
                <td className="num px-3 py-3 text-right">{inr(m.costs)}</td>
                <td className={cx("num px-5 py-3 text-right font-medium", m.profit < 0 && "text-bad")}>{inr(m.profit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card>
        <SectionTitle>Money that isn&apos;t part of profit</SectionTitle>
        <p className="mb-3 text-sm text-ink-2">These change your bank balance but aren&apos;t sales or running costs, so they&apos;re kept out of profit.</p>
        <ul className="divide-y divide-line">
          {data.outside_profit.map((o) => (
            <li key={o.label} className="flex justify-between py-2.5 text-sm">
              <span>{o.label}</span>
              <span className="num font-medium">{inr(o.amount)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
