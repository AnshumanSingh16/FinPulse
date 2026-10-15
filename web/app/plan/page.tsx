"use client";

import { ArrowLeft, ArrowRight, Banknote, ChevronDown, Landmark, Percent, ShoppingBag, Tags, TrendingUp, UserPlus } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ForecastChart, PurchaseChart } from "@/components/charts";
import { EvidenceButton } from "@/components/evidence";
import { Button, Card, cx, ErrorNote, Field, Loading, MoneyInput, Segmented, SectionTitle, Stat, toneBg, ToneIcon, toneText } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { day, inr, short, words } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Evidence, Tone } from "@/lib/types";

type Tab = "afford" | "cash" | "price" | "discount" | "hire" | "loan";

const TOOLS: { key: Tab; label: string; sub: string; grad: string; I: React.ElementType }[] = [
  { key: "afford", label: "Can I afford it?", sub: "Machine, van, stock…", grad: "grad-hero", I: ShoppingBag },
  { key: "cash", label: "Cash ahead", sub: "Next 30–180 days", grad: "grad-ocean", I: TrendingUp },
  { key: "price", label: "Raise prices?", sub: "Profit if prices change", grad: "grad-mint", I: Tags },
  { key: "discount", label: "Run a discount?", sub: "Festival offers", grad: "grad-sunset", I: Percent },
  { key: "hire", label: "Hire someone?", sub: "Salary vs extra sales", grad: "grad-berry", I: UserPlus },
  { key: "loan", label: "Take a loan?", sub: "EMI and cash impact", grad: "grad-night", I: Landmark },
];

export default function PlanPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Plan />
    </Suspense>
  );
}

function Plan() {
  const { t } = useT();
  const params = useSearchParams();
  const router = useRouter();
  const tab = ((params.get("tab") as Tab) || "afford") as Tab;
  const change = (x: Tab) => router.replace(x === "afford" ? "/plan/" : `/plan/?tab=${x}`, { scroll: false });
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl">{t("Plan ahead")}</h1>
        <p className="text-ink-2">Try a decision on your real numbers before you commit.</p>
      </div>
      <div className="no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 pb-1 sm:mx-0 sm:grid sm:grid-cols-3 sm:px-0 lg:grid-cols-6">
        {TOOLS.map(({ key, label, sub, grad, I }) => (
          <button
            key={key}
            onClick={() => change(key)}
            aria-pressed={tab === key}
            className={cx("flex min-w-[9.5rem] flex-col gap-2 rounded-3xl p-4 text-left transition", tab === key ? `${grad} shadow-xl` : "card hover:-translate-y-0.5")}
          >
            <span className={cx("grid size-10 place-items-center rounded-2xl", tab === key ? "glass" : grad)}>
              <I className="size-5" aria-hidden />
            </span>
            <span className="text-sm leading-tight font-semibold">{t(label)}</span>
            <span className={cx("text-xs", tab === key ? "text-white/80" : "text-muted")}>{sub}</span>
          </button>
        ))}
      </div>
      {tab === "afford" && <Afford />}
      {tab === "cash" && <CashAhead />}
      {(tab === "price" || tab === "discount" || tab === "hire" || tab === "loan") && <WhatIf kind={tab} />}
    </div>
  );
}

// ---------------------------------------------------------------- Can I afford it?

interface AffordResult {
  status: string;
  message?: string;
  tone: Tone;
  headline: string;
  detail: string;
  cushion: number;
  cushion_label: string;
  upfront: number;
  emi: number | null;
  total_interest: number | null;
  payback_months: number | null;
  months: number | null;
  today: number;
  scenarios: {
    key: string;
    name: string;
    assumes: string;
    lowest: number;
    lowest_date: string;
    lowest_without: number;
    end: number;
    end_without: number;
    below_cushion: string | null;
    negative: string | null;
    series: { date: string; with: number; without: number }[];
  }[];
  evidence: Evidence;
}

interface Form {
  name: string;
  price: string;
  paid_with: "cash" | "loan";
  down: number;
  rate: string;
  years: number;
  benefit: string;
  starts: number;
  running: string;
  once: string;
}

const START: Form = { name: "", price: "", paid_with: "cash", down: 20, rate: "", years: 3, benefit: "", starts: 1, running: "", once: "" };
const IDEAS = [
  { name: "Packing machine", price: "1200000" },
  { name: "Delivery van", price: "800000" },
  { name: "New shop counter", price: "150000" },
];

function Afford() {
  const [step, setStep] = useState(0);
  const [f, setF] = useState<Form>(START);
  const [res, setRes] = useState<AffordResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((s) => ({ ...s, [k]: v }));
  const price = Number(f.price) || 0;

  const run = async (form: Form) => {
    setBusy(true);
    setErr(null);
    try {
      const r = await post<AffordResult>("/api/afford", {
        name: form.name || "This purchase",
        price: Number(form.price),
        paid_with: form.paid_with,
        down_payment_pct: form.down,
        rate: form.paid_with === "loan" ? (form.rate === "" ? null : Number(form.rate)) : undefined,
        years: form.paid_with === "loan" ? form.years : undefined,
        monthly_benefit: Number(form.benefit) || 0,
        benefit_start_months: form.starts,
        running_cost: Number(form.running) || 0,
        one_time_cost: Number(form.once) || 0,
      });
      if (r.status !== "ok") setErr(r.message ?? "Couldn't check this.");
      else {
        setRes(r);
        setStep(3);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Live re-check when tweaking on the result screen.
  useEffect(() => {
    if (step !== 3) return;
    const t = setTimeout(() => run(f), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [f.price, f.benefit, f.down, f.years, f.rate, f.paid_with]);

  const canNext = [price > 0, f.paid_with === "cash" || (f.rate !== "" && Number(f.rate) >= 0), true][step] ?? true;

  if (step === 3 && res) return <AffordResultView r={res} f={f} set={set} busy={busy} err={err} edit={() => setStep(0)} />;

  return (
    <Card className="mx-auto max-w-xl p-6 sm:p-8">
      <div className="mb-6 flex gap-1.5" aria-label={`Step ${step + 1} of 3`}>
        {[0, 1, 2].map((i) => (
          <span key={i} className={cx("h-1.5 flex-1 rounded-full", i <= step ? "bg-brand" : "bg-line")} />
        ))}
      </div>

      {step === 0 && (
        <div className="space-y-5">
          <div>
            <ShoppingBag className="size-7 text-brand" aria-hidden />
            <h2 className="mt-2 text-xl font-semibold tracking-tight">What do you want to buy?</h2>
          </div>
          <Field label="What is it?" htmlFor="what">
            <input id="what" value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Packing machine" className="h-12 w-full rounded-2xl border border-line px-4 text-lg outline-none focus:border-brand focus:ring-2 focus:ring-brand/15" />
          </Field>
          <Field label="Price" htmlFor="price" hint={price ? `₹${words(price)} · ${inr(price)}` : "Including GST, as quoted"}>
            <MoneyInput id="price" value={f.price} onChange={(v) => set("price", v)} placeholder="12,00,000" />
          </Field>
          <div className="flex flex-wrap gap-2">
            {IDEAS.map((i) => (
              <button key={i.name} onClick={() => setF((s) => ({ ...s, name: i.name, price: i.price }))} className="rounded-full border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-brand hover:text-brand">
                {i.name} · {short(Number(i.price))}
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-5">
          <div>
            <Banknote className="size-7 text-brand" aria-hidden />
            <h2 className="mt-2 text-xl font-semibold tracking-tight">How will you pay?</h2>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                ["cash", "From my bank balance", Banknote],
                ["loan", "With a loan / EMI", Landmark],
              ] as const
            ).map(([v, label, I]) => (
              <button
                key={v}
                onClick={() => set("paid_with", v)}
                className={cx("rounded-2xl border-2 p-4 text-left transition", f.paid_with === v ? "border-brand bg-brand-50" : "border-line hover:border-ink-2")}
                aria-pressed={f.paid_with === v}
              >
                <I className={cx("size-6", f.paid_with === v ? "text-brand" : "text-ink-2")} />
                <p className="mt-2 font-medium">{label}</p>
              </button>
            ))}
          </div>
          {f.paid_with === "loan" && (
            <div className="space-y-5 rounded-2xl bg-canvas p-4">
              <Field label={`Down payment: ${f.down}%`} hint={price ? `You pay ${inr((price * f.down) / 100)} upfront` : undefined}>
                <input type="range" min={0} max={90} step={5} value={f.down} onChange={(e) => set("down", Number(e.target.value))} className="w-full" aria-label="Down payment percent" />
              </Field>
              <Field label="Interest rate (% per year)" htmlFor="rate" hint="From your bank's or lender's quote. FinPilot doesn't guess this.">
                <input id="rate" inputMode="decimal" value={f.rate} onChange={(e) => set("rate", e.target.value.replace(/[^\d.]/g, ""))} placeholder="e.g. 11" className="h-12 w-full rounded-2xl border border-line bg-surface px-4 text-lg outline-none focus:border-brand" />
              </Field>
              <Field label="Loan length">
                <div className="flex flex-wrap gap-2">
                  {[1, 2, 3, 4, 5, 7].map((y) => (
                    <button key={y} onClick={() => set("years", y)} className={cx("h-10 rounded-full border px-4 text-sm font-medium", f.years === y ? "border-[#f4f2ee] bg-[#f4f2ee] text-black" : "border-line bg-surface")}>
                      {y} {y === 1 ? "year" : "years"}
                    </button>
                  ))}
                </div>
              </Field>
            </div>
          )}
        </div>
      )}

      {step === 2 && (
        <div className="space-y-5">
          <div>
            <TrendingUp className="size-7 text-brand" aria-hidden />
            <h2 className="mt-2 text-xl font-semibold tracking-tight">Will it bring in money or save costs?</h2>
            <p className="mt-1 text-sm text-ink-2">Optional. Your best estimate — leave it blank if you&apos;re not sure.</p>
          </div>
          <Field label="Extra money each month" htmlFor="benefit" hint="More sales, or costs you'll save (e.g. less labour or wastage)">
            <MoneyInput id="benefit" value={f.benefit} onChange={(v) => set("benefit", v)} placeholder="45,000" />
          </Field>
          <Field label={`Starts after ${f.starts} month${f.starts === 1 ? "" : "s"}`}>
            <input type="range" min={0} max={12} value={f.starts} onChange={(e) => set("starts", Number(e.target.value))} className="w-full" aria-label="Months until the benefit starts" />
          </Field>
          <details className="group rounded-2xl border border-line p-4">
            <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium">
              Running and setup costs <ChevronDown className="size-4 transition group-open:rotate-180" />
            </summary>
            <div className="mt-4 space-y-4">
              <Field label="Running cost per month" hint="Maintenance, power, an operator…">
                <MoneyInput value={f.running} onChange={(v) => set("running", v)} placeholder="4,000" />
              </Field>
              <Field label="One-time costs" hint="Installation, transport, training">
                <MoneyInput value={f.once} onChange={(v) => set("once", v)} placeholder="35,000" />
              </Field>
            </div>
          </details>
        </div>
      )}

      {err && <p className="mt-4 rounded-2xl bg-caution-50 p-3 text-sm text-caution">{err}</p>}

      <div className="mt-8 flex items-center justify-between">
        {step > 0 ? (
          <Button variant="ghost" onClick={() => setStep((s) => s - 1)}>
            <ArrowLeft className="size-4" /> Back
          </Button>
        ) : (
          <span />
        )}
        {step < 2 ? (
          <Button size="lg" onClick={() => setStep((s) => s + 1)} disabled={!canNext}>
            Next <ArrowRight className="size-4" />
          </Button>
        ) : (
          <Button size="lg" onClick={() => run(f)} disabled={busy}>
            {busy ? "Checking…" : "Check if I can afford it"}
          </Button>
        )}
      </div>
    </Card>
  );
}

function AffordResultView({ r, f, set, busy, err, edit }: { r: AffordResult; f: Form; set: <K extends keyof Form>(k: K, v: Form[K]) => void; busy: boolean; err: string | null; edit: () => void }) {
  const [key, setKey] = useState("downside");
  const sc = r.scenarios.find((s) => s.key === key) ?? r.scenarios[0];
  const price = Number(f.price) || 0;
  return (
    <div className={cx("grid gap-5 lg:grid-cols-[1fr_20rem]", busy && "opacity-70 transition")}>
      <div className="space-y-5">
        <Card className={cx("p-6", toneBg[r.tone])}>
          <div className="flex items-start gap-3">
            <ToneIcon tone={r.tone} className="size-8 shrink-0" />
            <div>
              <p className="text-sm text-ink-2">{f.name || "This purchase"} · {short(price)}{f.paid_with === "loan" ? ` on a ${f.years}-year loan` : " in cash"}</p>
              <h2 className={cx("text-2xl font-semibold tracking-tight", toneText[r.tone])}>{r.headline}</h2>
              <p className="mt-1 text-ink-2">{r.detail}</p>
            </div>
          </div>
        </Card>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Card className="p-4">
            <Stat label="Pay upfront" value={short(r.upfront)} sub={f.paid_with === "loan" ? "Down payment + setup" : "Price + setup"} />
          </Card>
          {r.emi ? (
            <Card className="p-4">
              <Stat label="Monthly EMI" value={inr(r.emi)} sub={`for ${r.months} months`} />
            </Card>
          ) : null}
          <Card className="p-4">
            <Stat label="Pays for itself in" value={r.payback_months ? `${Math.round(r.payback_months)} months` : "—"} sub={r.payback_months ? "if your estimate holds" : "Add the monthly benefit"} />
          </Card>
        </div>

        <Card>
          <SectionTitle>Your bank balance over the next 6 months</SectionTitle>
          <Segmented
            value={key}
            onChange={setKey}
            className="mb-3 max-w-full overflow-x-auto"
            options={[
              { value: "downside", label: "Tough months" },
              { value: "base", label: "Most likely" },
              { value: "optimistic", label: "Goes well" },
            ]}
          />
          <p className="mb-2 text-sm text-ink-2">{sc.assumes}</p>
          <PurchaseChart series={sc.series} cushion={r.cushion} />
          <p className="mt-2 text-sm">
            Lowest balance if you buy: <span className="num font-semibold">{short(sc.lowest)}</span> on {day(sc.lowest_date)}
            <span className="text-ink-2"> (vs {short(sc.lowest_without)} if you don&apos;t)</span>
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <EvidenceButton evidence={r.evidence} label="How we checked this" />
            <span className="text-xs text-muted">Scenarios show &ldquo;what if&rdquo;, not predictions.</span>
          </div>
        </Card>
      </div>

      <Card className="h-fit space-y-5 lg:sticky lg:top-6">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Try changes</h3>
          <button onClick={edit} className="text-sm font-medium text-brand hover:underline">
            Start over
          </button>
        </div>
        <Field label={`Price: ${short(price)}`}>
          <input type="range" min={Math.round(price * 0.25) || 10000} max={Math.round(price * 2) || 100000} step={Math.max(1000, Math.round(price / 100 / 1000) * 1000)} value={price} onChange={(e) => set("price", e.target.value)} className="w-full" aria-label="Price" />
        </Field>
        <Field label={`Extra money a month: ${inr(Number(f.benefit) || 0)}`}>
          <input type="range" min={0} max={Math.max(100000, (Number(f.benefit) || 0) * 2)} step={1000} value={Number(f.benefit) || 0} onChange={(e) => set("benefit", e.target.value)} className="w-full" aria-label="Monthly benefit" />
        </Field>
        <Segmented
          value={f.paid_with}
          onChange={(v) => set("paid_with", v)}
          options={[
            { value: "cash", label: "Cash" },
            { value: "loan", label: "Loan" },
          ]}
        />
        {f.paid_with === "loan" && (
          <>
            <Field label={`Down payment: ${f.down}%`}>
              <input type="range" min={0} max={90} step={5} value={f.down} onChange={(e) => set("down", Number(e.target.value))} className="w-full" aria-label="Down payment" />
            </Field>
            <Field label="Interest % per year">
              <input inputMode="decimal" value={f.rate} onChange={(e) => set("rate", e.target.value.replace(/[^\d.]/g, ""))} placeholder="from your lender" className="h-10 w-full rounded-xl border border-line px-3 outline-none focus:border-brand" />
            </Field>
            <Field label={`Loan length: ${f.years} years`}>
              <input type="range" min={1} max={7} value={f.years} onChange={(e) => set("years", Number(e.target.value))} className="w-full" aria-label="Loan years" />
            </Field>
          </>
        )}
        {err && <p className="rounded-xl bg-caution-50 p-3 text-sm text-caution">{err}</p>}
        <p className="text-xs text-muted">Cushion: {r.cushion_label} — about one month of your running costs.</p>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- Cash ahead

interface ForecastResp {
  status: string;
  message?: string;
  tone: Tone;
  headline: string;
  detail: string;
  cushion: number;
  cushion_label: string;
  checkpoints: { days: number; date: string; balance: number; label: string }[];
  series: { date: string; balance: number }[];
  big_items: { date: string; day: string; what: string; category: string; amount: number }[];
  not_counted: number;
  evidence: Evidence;
}

function CashAhead() {
  const [late, setLate] = useState(0);
  const [collect, setCollect] = useState(100);
  const [overdue, setOverdue] = useState(false);
  const [typical, setTypical] = useState(true);
  const [days, setDays] = useState(90);
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(new URLSearchParams({ days: String(days), late_days: String(late), collect_pct: String(collect), count_overdue: String(overdue), typical: String(typical) }).toString()), 200);
    return () => clearTimeout(t);
  }, [late, collect, overdue, typical, days]);
  const { data, error, loading, reload } = useApi<ForecastResp>(q ? `/api/forecast?${q}` : null);

  if (error) return <ErrorNote message={error} retry={reload} />;
  if (!data) return <Loading />;
  if (data.status !== "ok")
    return (
      <Card className="text-ink-2">
        {data.message}{" "}
        <a href="/data/#balance" className="font-medium text-brand">
          Add balance →
        </a>
      </Card>
    );
  return (
    <div className={cx("grid gap-5 lg:grid-cols-[1fr_20rem]", loading && "opacity-70 transition")}>
      <div className="space-y-5">
        <Card className={cx("p-6", toneBg[data.tone])}>
          <div className="flex items-start gap-3">
            <ToneIcon tone={data.tone} className="size-7 shrink-0" />
            <div>
              <h2 className={cx("text-xl font-semibold tracking-tight", toneText[data.tone])}>{data.headline}</h2>
              <p className="mt-1 text-ink-2">{data.detail}</p>
            </div>
          </div>
        </Card>
        <div className="grid grid-cols-3 gap-3">
          {data.checkpoints.slice(0, 3).map((c) => (
            <Card key={c.days} className="p-4">
              <Stat label={`In ${c.days} days`} value={c.label} sub={day(c.date)} tone={c.balance < 0 ? "bad" : c.balance < data.cushion ? "caution" : undefined} />
            </Card>
          ))}
        </div>
        <Card>
          <SectionTitle>Expected bank balance</SectionTitle>
          <ForecastChart series={data.series} cushion={data.cushion} />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <EvidenceButton evidence={data.evidence} label="How this forecast works" />
            {data.not_counted > 0 && !overdue && <span className="text-xs text-muted">{short(data.not_counted)} of overdue customer payments isn&apos;t counted.</span>}
          </div>
        </Card>
        {data.big_items.length > 0 && (
          <Card>
            <SectionTitle>Big payments coming in and out</SectionTitle>
            <ul className="divide-y divide-line">
              {data.big_items.map((i, n) => (
                <li key={n} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span className="w-14 shrink-0 text-ink-2">{i.day}</span>
                  <span className="min-w-0 flex-1 truncate font-medium">{i.what}</span>
                  <span className={cx("num font-medium", i.amount > 0 && "text-good")}>
                    {i.amount > 0 ? "+" : "−"}
                    {inr(Math.abs(i.amount))}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
      <Card className="h-fit space-y-5 lg:sticky lg:top-6">
        <h3 className="font-semibold">What if…</h3>
        <Field label={`Customers pay ${late ? `${late} days late` : "on time"}`}>
          <input type="range" min={0} max={60} step={5} value={late} onChange={(e) => setLate(Number(e.target.value))} className="w-full" aria-label="Days late" />
        </Field>
        <Field label={`You collect ${collect}% of what you're owed`}>
          <input type="range" min={50} max={100} step={5} value={collect} onChange={(e) => setCollect(Number(e.target.value))} className="w-full" aria-label="Collection percent" />
        </Field>
        <Toggle checked={overdue} onChange={setOverdue} label="Overdue customers pay within a month" />
        <Toggle checked={typical} onChange={setTypical} label="Include your usual monthly sales and spending" hint="Based on your last 3 months, leaving out one-offs" />
        <Field label="Look ahead">
          <Segmented
            value={String(days)}
            onChange={(v) => setDays(Number(v))}
            options={[
              { value: "30", label: "30d" },
              { value: "60", label: "60d" },
              { value: "90", label: "90d" },
              { value: "180", label: "6m" },
            ]}
          />
        </Field>
      </Card>
    </div>
  );
}

function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-3">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cx("relative h-6 w-11 shrink-0 rounded-full transition", checked ? "bg-brand" : "bg-line")}
      >
        <span className={cx("absolute top-0.5 size-5 rounded-full bg-white shadow transition", checked ? "left-[1.375rem]" : "left-0.5")} />
      </button>
    </label>
  );
}


// ---------------------------------------------------------------- what-if simulators

interface Baseline {
  sales: number;
  variable: number;
  fixed: number;
  profit: number;
  contribution_pct: number | null;
}
interface CashFx {
  lowest_without: number;
  lowest_with: number;
  lowest_date: string;
  end_without: number;
  end_with: number;
  cushion: number;
  below_cushion: string | null;
  negative: string | null;
  series: { date: string; with: number; without: number }[];
}
interface WhatIfResp {
  status: string;
  message?: string;
  baseline?: Baseline;
  new_profit?: number;
  monthly_change?: number;
  yearly_change?: number;
  breakeven_volume_pct?: number | null;
  profit_change?: number;
  period_sales_change?: number;
  uplift_needed_pct?: number | null;
  breakeven_sales?: number | null;
  emi?: number;
  months?: number;
  total_interest?: number;
  emi_share_of_profit_pct?: number | null;
  profit_cover?: number | null;
  cash?: CashFx | null;
  evidence: Evidence;
}

const SLIDERS: Record<string, { key: string; label: string; min: number; max: number; step: number; def: number; fmt: (v: number) => string }[]> = {
  price: [
    { key: "price_pct", label: "Change prices by", min: -20, max: 30, step: 1, def: 5, fmt: (v) => `${v > 0 ? "+" : ""}${v}%` },
    { key: "volume_pct", label: "Customers buy (units)", min: -40, max: 20, step: 1, def: -3, fmt: (v) => `${v > 0 ? "+" : ""}${v}%` },
  ],
  discount: [
    { key: "discount_pct", label: "Discount", min: 0, max: 40, step: 1, def: 10, fmt: (v) => `${v}%` },
    { key: "uplift_pct", label: "Extra sales volume expected", min: 0, max: 100, step: 5, def: 15, fmt: (v) => `+${v}%` },
    { key: "weeks", label: "For how long", min: 1, max: 12, step: 1, def: 4, fmt: (v) => `${v} weeks` },
  ],
  hire: [
    { key: "salary", label: "Monthly salary", min: 5000, max: 60000, step: 1000, def: 15000, fmt: (v) => inr(v) },
    { key: "extra_sales", label: "Extra sales they bring each month", min: 0, max: 200000, step: 5000, def: 40000, fmt: (v) => inr(v) },
    { key: "start_months", label: "Sales start after", min: 0, max: 6, step: 1, def: 1, fmt: (v) => `${v} month${v === 1 ? "" : "s"}` },
  ],
  loan: [
    { key: "amount", label: "Loan amount", min: 50000, max: 2500000, step: 25000, def: 500000, fmt: (v) => short(v) },
    { key: "rate", label: "Interest rate (from your lender)", min: 6, max: 30, step: 0.5, def: 12, fmt: (v) => `${v}%` },
    { key: "years", label: "Years", min: 1, max: 7, step: 1, def: 3, fmt: (v) => `${v} yr` },
  ],
};

function WhatIf({ kind }: { kind: "price" | "discount" | "hire" | "loan" }) {
  const { t } = useT();
  const [vals, setVals] = useState<Record<string, number>>(() => Object.fromEntries(SLIDERS[kind].map((s) => [s.key, s.def])));
  const [q, setQ] = useState("");
  useEffect(() => setVals(Object.fromEntries(SLIDERS[kind].map((s) => [s.key, s.def]))), [kind]);
  useEffect(() => {
    const x = setTimeout(() => setQ(new URLSearchParams(Object.fromEntries(Object.entries(vals).map(([k, v]) => [k, String(v)]))).toString()), 200);
    return () => clearTimeout(x);
  }, [vals]);
  const { data, loading } = useApi<WhatIfResp>(q ? `/api/whatif/${kind}?${q}` : null);

  let tone: Tone = "neutral";
  let head = "";
  let sub = "";
  if (data && data.status === "ok") {
    if (kind === "price") {
      const ch = data.monthly_change ?? 0;
      tone = ch >= 0 ? "good" : "bad";
      head = `${ch >= 0 ? "+" : "−"}${short(Math.abs(ch))} profit a month`;
      sub = `${short(Math.abs(data.yearly_change ?? 0))} a year. ` + (data.breakeven_volume_pct != null ? `You can lose up to ${Math.abs(data.breakeven_volume_pct).toFixed(1)}% of units sold before profit drops.` : "");
    } else if (kind === "discount") {
      const ch = data.profit_change ?? 0;
      tone = ch >= 0 ? "good" : "caution";
      head = `${ch >= 0 ? "+" : "−"}${short(Math.abs(ch))} profit over the offer`;
      sub = data.uplift_needed_pct != null ? `To break even you need about ${data.uplift_needed_pct.toFixed(0)}% more volume.` : "";
    } else if (kind === "hire") {
      const ch = data.monthly_change ?? 0;
      tone = ch >= 0 ? "good" : "caution";
      head = `${ch >= 0 ? "+" : "−"}${short(Math.abs(ch))} profit a month`;
      sub = data.breakeven_sales ? `They pay for themselves if they bring ${short(data.breakeven_sales)} of extra sales a month.` : "";
    } else {
      tone = (data.profit_cover ?? 0) >= 1.25 ? "good" : (data.profit_cover ?? 0) >= 1 ? "caution" : "bad";
      head = `EMI ${inr(data.emi ?? 0)} for ${data.months} months`;
      sub = `Total interest ${short(data.total_interest ?? 0)}. ` + (data.profit_cover != null ? `Your average profit covers the EMI ${data.profit_cover.toFixed(2)}× (lenders like 1.25× or more).` : "");
    }
  }
  return (
    <div className={cx("grid gap-5 lg:grid-cols-[1fr_21rem]", loading && "opacity-80 transition")}>
      <div className="space-y-5">
        {data && data.status !== "ok" ? (
          <Card className="text-ink-2">{data.message}</Card>
        ) : data ? (
          <>
            <Card className={cx("p-6", toneBg[tone])}>
              <div className="flex items-start gap-3">
                <ToneIcon tone={tone} className="size-8 shrink-0" />
                <div>
                  <h2 className={cx("text-2xl font-bold tracking-tight", toneText[tone])}>{head}</h2>
                  <p className="mt-1 text-ink-2">{sub}</p>
                </div>
              </div>
            </Card>
            {data.baseline && (
              <div className="grid grid-cols-3 gap-3">
                <Card className="p-4">
                  <Stat label="Avg monthly sales" value={short(data.baseline.sales)} />
                </Card>
                <Card className="p-4">
                  <Stat label="Stock & delivery costs" value={short(data.baseline.variable)} sub="move with sales" />
                </Card>
                <Card className="p-4">
                  <Stat label="Avg monthly profit" value={short(data.baseline.profit)} tone={data.baseline.profit < 0 ? "bad" : undefined} />
                </Card>
              </div>
            )}
            {kind === "price" && data.baseline && (
              <Card>
                <SectionTitle>Monthly profit</SectionTitle>
                <div className="space-y-3">
                  {[
                    { l: "Today", v: data.baseline.profit, c: "bg-muted" },
                    { l: "With the change", v: data.new_profit ?? 0, c: (data.new_profit ?? 0) >= data.baseline.profit ? "bg-good" : "bg-bad" },
                  ].map((r) => {
                    const m = Math.max(Math.abs(data.baseline!.profit), Math.abs(data.new_profit ?? 0), 1);
                    return (
                      <div key={r.l}>
                        <div className="mb-1 flex justify-between text-sm">
                          <span>{r.l}</span>
                          <span className="num font-semibold">{inr(r.v)}</span>
                        </div>
                        <div className="h-3 rounded-full bg-canvas">
                          <div className={cx("h-3 rounded-full transition-all", r.c)} style={{ width: `${(Math.abs(r.v) / m) * 100}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}
            {data.cash && (
              <Card>
                <SectionTitle>Your bank balance, next 6 months</SectionTitle>
                <PurchaseChart series={data.cash.series} cushion={data.cash.cushion} />
                <p className="mt-2 text-sm">
                  Lowest balance: <span className="num font-semibold">{short(data.cash.lowest_with)}</span> on {day(data.cash.lowest_date)}{" "}
                  <span className="text-ink-2">(vs {short(data.cash.lowest_without)} without)</span>
                </p>
              </Card>
            )}
            <EvidenceButton evidence={data.evidence} />
          </>
        ) : (
          <Loading />
        )}
      </div>
      <Card className="h-fit space-y-5 lg:sticky lg:top-6">
        <h3 className="font-semibold">What if…</h3>
        {SLIDERS[kind].map((s) => (
          <Field key={s.key} label={`${s.label}: ${s.fmt(vals[s.key] ?? s.def)}`}>
            <input type="range" min={s.min} max={s.max} step={s.step} value={vals[s.key] ?? s.def} onChange={(e) => setVals((v) => ({ ...v, [s.key]: Number(e.target.value) }))} className="w-full" aria-label={s.label} />
          </Field>
        ))}
        <p className="text-xs text-muted">Based on your last 3 full months. {t("Not financial advice.")}</p>
      </Card>
    </div>
  );
}
