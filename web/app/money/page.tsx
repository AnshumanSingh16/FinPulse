"use client";

import { Check, PartyPopper, Search, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useContext, useEffect, useMemo, useState } from "react";
import { CatIcon } from "@/components/cat";
import { DataVersion } from "@/components/data-version";
import { EvidenceButton } from "@/components/evidence";
import { confetti, useToast } from "@/components/fx";
import { Button, Card, cx, ErrorNote, Loading, Pill, Segmented, SectionTitle, Sheet } from "@/components/ui";
import { get, post, useApi } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Evidence } from "@/lib/types";

type Tab = "activity" | "sort" | "profit";

interface Txn {
  id: string;
  date: string;
  day: string;
  description: string;
  party: string;
  category: string;
  direction: "in" | "out";
  amount: number;
  guess: boolean;
}
interface TxnPage {
  total: number;
  money_in: number;
  money_out: number;
  categories: string[];
  rows: Txn[];
}
interface Cat {
  name: string;
  type: string;
}

export default function MoneyPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Money />
    </Suspense>
  );
}

function Money() {
  const { t } = useT();
  const params = useSearchParams();
  const router = useRouter();
  const tab = ((params.get("tab") as Tab) || "activity") as Tab;
  const change = (x: Tab) => router.replace(x === "activity" ? "/money/" : `/money/?tab=${x}`, { scroll: false });
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{t("Money")}</h1>
      <div className="no-scrollbar -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <Segmented<Tab>
          value={tab}
          onChange={change}
          options={[
            { value: "activity", label: t("Transactions") },
            { value: "sort", label: t("Sort transactions") },
            { value: "profit", label: t("Profit by month") },
          ]}
        />
      </div>
      {tab === "activity" && <Activity ids={params.get("ids") ?? ""} dir={params.get("dir") ?? ""} />}
      {tab === "sort" && <SortQueue />}
      {tab === "profit" && <Profit />}
    </div>
  );
}

function useCategories() {
  const [cats, setCats] = useState<Cat[]>([]);
  useEffect(() => {
    get<Cat[]>("/api/categories").then(setCats);
  }, []);
  return cats;
}

function CategoryPicker({ txn, onClose }: { txn: Txn; onClose: () => void }) {
  const { t } = useT();
  const cats = useCategories();
  const { refresh } = useContext(DataVersion);
  const toast = useToast();
  const [remember, setRemember] = useState(true);
  const pick = async (c: string) => {
    const r = await post<{ updated: number }>("/api/categorise", { ids: [txn.id], category: c, party: txn.party, remember });
    refresh();
    onClose();
    toast.show({ text: `${c} · ${r.updated}` });
  };
  const list = cats.filter((c) => c.type === "both" || c.type === txn.direction || c.type === "unclassified");
  return (
    <Sheet open onClose={onClose} title={`${txn.party} · ${inr(txn.amount)}`}>
      <p className="mb-3 text-sm text-ink-2">{txn.description}</p>
      <label className="mb-4 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /> {t("Always use this for {name}", { name: txn.party })}
      </label>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {list.map((c) => (
          <button key={c.name} onClick={() => pick(c.name)} className={cx("flex items-center gap-2 rounded-2xl border p-2 text-left text-sm", txn.category === c.name ? "border-brand bg-brand-50" : "border-line hover:border-ink-2")}>
            <CatIcon category={c.name} size="sm" /> <span className="truncate">{c.name}</span>
          </button>
        ))}
      </div>
    </Sheet>
  );
}

function Activity({ ids, dir: initialDir }: { ids: string; dir: string }) {
  const { t } = useT();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [dir, setDir] = useState<"" | "in" | "out">((initialDir as "in" | "out") || "");
  const [cat, setCat] = useState("");
  const [limit, setLimit] = useState(60);
  const [edit, setEdit] = useState<Txn | null>(null);
  useEffect(() => {
    const x = setTimeout(() => setQuery(q), 250);
    return () => clearTimeout(x);
  }, [q]);
  const path = `/api/transactions?${new URLSearchParams({ q: query, direction: dir, category: cat, ids, limit: String(limit) })}`;
  const { data, error, loading, reload } = useApi<TxnPage>(path);
  const groups = useMemo(() => {
    const g: { day: string; rows: Txn[]; net: number }[] = [];
    for (const r of data?.rows ?? []) {
      const last = g[g.length - 1];
      const s = r.direction === "in" ? r.amount : -r.amount;
      if (last && last.day === r.day) {
        last.rows.push(r);
        last.net += s;
      } else g.push({ day: r.day, rows: [r], net: s });
    }
    return g;
  }, [data]);

  if (error) return <ErrorNote message={error} retry={reload} />;
  return (
    <div className="space-y-4">
      {ids ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl bg-caution-50 px-4 py-3 text-sm">
          <span>Showing the {ids.split(",").length} payments to review. Compare them with your bank statement or ask the supplier.</span>
          <Button size="sm" variant="secondary" onClick={() => router.replace("/money/")}>
            {t("All")}
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-full border border-line bg-surface px-4 focus-within:border-brand sm:max-w-xs">
            <Search className="size-4 text-muted" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Search name")} className="w-full bg-transparent text-sm outline-none" aria-label="Search transactions" />
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
              { value: "", label: t("All") },
              { value: "in", label: t("Money in") },
              { value: "out", label: t("Money out") },
            ]}
          />
          <select value={cat} onChange={(e) => setCat(e.target.value)} className="h-10 rounded-full border border-line bg-surface px-4 text-sm" aria-label={t("Category")}>
            <option value="">{t("All categories")}</option>
            {data?.categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
      )}
      {data && (
        <div className="grid grid-cols-3 gap-3">
          <div className="grad-mint rounded-3xl p-4">
            <p className="text-xs text-white/85">{t("Money in")}</p>
            <p className="num text-xl font-bold">{short(data.money_in)}</p>
          </div>
          <div className="grad-sunset rounded-3xl p-4">
            <p className="text-xs text-white/85">{t("Money out")}</p>
            <p className="num text-xl font-bold">{short(data.money_out)}</p>
          </div>
          <div className="grad-violet rounded-3xl p-4">
            <p className="text-xs text-white/85">{t("Transactions")}</p>
            <p className="num text-xl font-bold">{data.total.toLocaleString("en-IN")}</p>
          </div>
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
              <div className="sticky top-14 z-10 flex justify-between bg-surface/95 px-5 pt-4 pb-1 text-xs font-semibold tracking-wide text-muted uppercase backdrop-blur lg:top-0">
                <span>{g.day}</span>
                <span className={cx("num", g.net >= 0 ? "text-good" : "")}>{g.net >= 0 ? "+" : "−"}{inr(Math.abs(g.net))}</span>
              </div>
              <ul>
                {g.rows.map((r) => (
                  <li key={r.id}>
                    <button onClick={() => setEdit(r)} className="flex w-full items-center gap-3 px-5 py-2.5 text-left hover:bg-canvas">
                      <CatIcon category={r.category} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{r.party !== "Unknown" ? r.party : r.description}</p>
                        <p className="flex items-center gap-1.5 truncate text-xs text-muted">
                          {r.category} {r.guess && <Pill tone="caution" className="!py-0 !text-[0.65rem]">{t("guess")}</Pill>} · {r.description}
                        </p>
                      </div>
                      <span className={cx("num shrink-0 font-semibold", r.direction === "in" && "text-good")}>
                        {r.direction === "in" ? "+" : "−"}
                        {inr(r.amount)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {data && data.total > data.rows.length && (
            <div className="p-4 text-center">
              <Button variant="secondary" onClick={() => setLimit((l) => l + 100)}>
                {t("Show more")} ({data.total - data.rows.length})
              </Button>
            </div>
          )}
        </Card>
      )}
      {edit && <CategoryPicker txn={edit} onClose={() => setEdit(null)} />}
    </div>
  );
}

interface Review {
  count: number;
  groups: { party: string; direction: "in" | "out"; count: number; total: number; current: string; ids: string[]; example: string }[];
}

function SortQueue() {
  const { t } = useT();
  const { data, reload } = useApi<Review>("/api/categorise/review");
  const cats = useCategories();
  const { refresh } = useContext(DataVersion);
  const [done, setDone] = useState(0);
  if (!data) return <Loading />;
  if (!data.groups.length)
    return (
      <Card className="flex flex-col items-center gap-3 py-12 text-center">
        <span className="grad-mint grid size-16 place-items-center rounded-3xl">
          <PartyPopper className="size-8" />
        </span>
        <p className="text-lg font-semibold">{t("All sorted! Every transaction has a category.")}</p>
      </Card>
    );
  const g = data.groups[0];
  const options = cats.filter((c) => c.type === "both" || c.type === g.direction || c.type === "unclassified");
  const pick = async (c: string) => {
    await post("/api/categorise", { ids: g.ids, category: c, party: g.party, remember: true });
    setDone((d) => d + 1);
    if (data.groups.length === 1) confetti();
    reload();
    refresh();
  };
  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="flex items-center justify-between text-sm text-ink-2">
        <span>{data.count} left</span>
        {done > 0 && (
          <span className="inline-flex items-center gap-1 text-good">
            <Check className="size-4" /> {done} sorted
          </span>
        )}
      </div>
      <div className="h-2 rounded-full bg-line">
        <div className="grad-violet h-2 rounded-full transition-all" style={{ width: `${(done / (done + data.groups.length)) * 100}%` }} />
      </div>
      <Card key={g.party + g.direction} className="rise space-y-4 p-6">
        <div>
          <p className="text-xs font-semibold tracking-wide text-muted uppercase">{g.direction === "in" ? t("Money in") : t("Money out")}</p>
          <p className="text-2xl font-bold">{g.party}</p>
          <p className="text-sm text-ink-2">
            {g.count} × · <span className="num font-semibold text-ink">{inr(g.total)}</span> · “{g.example}”
          </p>
          <p className="mt-1 text-xs text-muted">Now: {g.current}</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {options.slice(0, 18).map((c) => (
            <button key={c.name} onClick={() => pick(c.name)} className="flex items-center gap-2 rounded-2xl border border-line p-2 text-left text-sm transition hover:border-brand hover:bg-brand-50">
              <CatIcon category={c.name} size="sm" /> <span className="truncate">{c.name}</span>
            </button>
          ))}
        </div>
        <p className="text-xs text-muted">{t("Always use this for {name}", { name: g.party })} ✓</p>
      </Card>
    </div>
  );
}

interface Report {
  status: string;
  message?: string;
  period: string;
  totals: { sales: number; costs: number; profit: number; margin_pct: number | null };
  months: { month: string; key: string; sales: number; costs: number; profit: number }[];
  outside_profit: { label: string; amount: number }[];
  evidence: Evidence;
}

function Profit() {
  const { t } = useT();
  const { data, error, loading, reload } = useApi<Report>("/api/report");
  if (error) return <ErrorNote message={error} retry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  if (data.status !== "ok") return <Card className="text-ink-2">{data.message}</Card>;
  const max = Math.max(...data.months.map((m) => Math.max(m.sales, m.costs)), 1);
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="grad-mint rounded-3xl p-5">
          <p className="text-sm text-white/85">{t("Sales received")}</p>
          <p className="num text-2xl font-bold">{short(data.totals.sales)}</p>
        </div>
        <div className="grad-sunset rounded-3xl p-5">
          <p className="text-sm text-white/85">{t("Running costs paid")}</p>
          <p className="num text-2xl font-bold">{short(data.totals.costs)}</p>
        </div>
        <div className={cx("rounded-3xl p-5", data.totals.profit >= 0 ? "grad-violet" : "grad-hero-bad")}>
          <p className="text-sm text-white/85">
            {t("Profit")} {t("(estimate)")}
          </p>
          <p className="num text-2xl font-bold">{short(data.totals.profit)}</p>
          {data.totals.margin_pct != null && <p className="text-xs text-white/85">{data.totals.margin_pct.toFixed(0)}p / ₹1</p>}
        </div>
      </div>
      <Card className="p-0">
        <ul className="divide-y divide-line">
          {data.months.map((m) => (
            <li key={m.key} className="grid grid-cols-[7rem_1fr_auto] items-center gap-3 px-5 py-3">
              <span className="text-sm font-medium">{m.month}</span>
              <div className="space-y-1">
                <div className="h-2 rounded-full bg-in" style={{ width: `${(m.sales / max) * 100}%` }} title={`${t("Sales received")} ${inr(m.sales)}`} />
                <div className="h-2 rounded-full bg-out" style={{ width: `${(m.costs / max) * 100}%` }} title={`${t("Running costs paid")} ${inr(m.costs)}`} />
              </div>
              <span className={cx("num w-24 text-right font-semibold", m.profit < 0 ? "text-bad" : "text-good")}>{short(m.profit)}</span>
            </li>
          ))}
        </ul>
        <p className="flex gap-4 px-5 pb-4 text-xs text-ink-2">
          <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-in" /> {t("Sales received")}</span>
          <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-out" /> {t("Running costs paid")}</span>
        </p>
      </Card>
      <Card>
        <SectionTitle>Money that isn&apos;t part of profit</SectionTitle>
        <ul className="divide-y divide-line">
          {data.outside_profit.map((o) => (
            <li key={o.label} className="flex justify-between py-2.5 text-sm">
              <span>{o.label}</span>
              <span className="num font-medium">{inr(o.amount)}</span>
            </li>
          ))}
        </ul>
        <EvidenceButton evidence={data.evidence} className="mt-3" />
      </Card>
    </div>
  );
}
