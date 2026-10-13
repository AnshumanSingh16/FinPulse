"use client";

import { Loader2, Scale } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import type { PrepayVsInvestResult, RentVsBuyResult } from "@/lib/personal/finance/decisions";
import { cn } from "@/lib/utils";

import { RentBuyChart } from "./charts";
import { MoneyInput, NumberInput } from "./fields";
import { Tabs } from "./kit";
import { usePersonal } from "./provider";
import { Disclosure, Notice, PageTitle } from "./ui";

type Num = number | null;

export function DecideWorkspace() {
  const params = useSearchParams();
  const [tab, setTab] = useState(params.get("tab") === "prepay" ? "prepay" : "rent");
  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        eyebrow="Decide"
        title="Two questions every home owner asks"
        description="Side-by-side simulations, month by month, with every assumption on the page. They compare paths under assumptions you control — they don't predict markets."
      />
      <Tabs
        label="Decision"
        value={tab}
        onChange={setTab}
        items={[
          { id: "rent", label: "Rent or buy a home?" },
          { id: "prepay", label: "Prepay my loan or invest?" },
        ]}
        className="w-fit max-w-full"
      />
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "rent" ? <RentVsBuy /> : <PrepayVsInvest />}
      </div>
    </div>
  );
}

function useRunner<R>() {
  const [result, setResult] = useState<R | null>(null);
  const [ranWith, setRanWith] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(key: string, fn: () => Promise<{ result: R }>) {
    setBusy(true);
    setError(null);
    try {
      setResult((await fn()).result);
      setRanWith(key);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The comparison failed");
    } finally {
      setBusy(false);
    }
  }
  return { result, ranWith, busy, error, run };
}

function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <section
      className={cn(
        "flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6",
        className,
      )}
    >
      {children}
    </section>
  );
}

function Big({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "good" | "warn";
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[12px] text-ink-500">{label}</span>
      <span
        className={cn(
          "tabular font-display text-[19px] font-bold whitespace-nowrap",
          tone === "good" && "text-brand-700",
          tone === "warn" && "text-caution-text",
        )}
      >
        {value}
      </span>
      {note ? <span className="text-[12px] text-ink-400">{note}</span> : null}
    </div>
  );
}

// ---------------------------------------------------------------- rent vs buy

function RentVsBuy() {
  const { state } = usePersonal();
  const house = state?.latestRun?.request.type === "house" ? state.latestRun : null;
  const [v, setV] = useState({
    price: (house?.inputs?.purchase.purchasePrice ?? 7_500_000) as Num,
    monthlyRent: 25_000 as Num,
    downPaymentPct: (house?.inputs?.purchase.downPaymentPct ?? 20) as Num,
    upfrontCostPct: 7 as Num,
    loanRatePct: (house?.inputs?.purchase.annualInterestRate ?? 8.5) as Num,
    tenureYears: (house ? house.inputs!.purchase.tenureMonths / 12 : 20) as Num,
    rentGrowthPct: 5 as Num,
    appreciationPct: 5 as Num,
    ownershipCostPct: 0.5 as Num,
    investReturnPct: 10 as Num,
    years: 15 as Num,
  });
  const r = useRunner<RentVsBuyResult>();
  const set = (k: keyof typeof v) => (x: Num) => setV({ ...v, [k]: x });
  const key = JSON.stringify(v);
  const ready = Object.values(v).every((x) => x !== null) && (v.price ?? 0) >= 100_000;
  const stale = r.result !== null && r.ranWith !== key;
  const res = r.result;
  const last = res?.years[res.years.length - 1];

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
      <Card>
        <h2 className="text-[16px] font-bold">The home</h2>
        {house ? (
          <p className="-mt-2 text-[12.5px] text-ink-500">
            Prefilled from your analysis of {house.request.label}.
          </p>
        ) : null}
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <MoneyInput label="Price" value={v.price} onChange={set("price")} />
          </div>
          <div className="col-span-2">
            <MoneyInput
              label="Rent for a similar home"
              value={v.monthlyRent}
              onChange={set("monthlyRent")}
              hint="per month"
            />
          </div>
          <NumberInput
            label="Down payment"
            suffix="%"
            min={0}
            max={100}
            value={v.downPaymentPct}
            onChange={set("downPaymentPct")}
          />
          <NumberInput
            label="Loan rate"
            suffix="% p.a."
            min={0}
            max={30}
            step={0.05}
            value={v.loanRatePct}
            onChange={set("loanRatePct")}
          />
          <NumberInput
            label="Loan tenure"
            suffix="years"
            min={1}
            max={30}
            value={v.tenureYears}
            onChange={set("tenureYears")}
          />
          <NumberInput
            label="Compare over"
            suffix="years"
            min={1}
            max={30}
            value={v.years}
            onChange={set("years")}
          />
        </div>
        <Disclosure title="Market assumptions" hint="Change these — they decide the answer">
          <div className="grid grid-cols-2 gap-4">
            <NumberInput
              label="Home price growth"
              suffix="%/yr"
              min={0}
              max={20}
              step={0.5}
              value={v.appreciationPct}
              onChange={set("appreciationPct")}
            />
            <NumberInput
              label="Rent growth"
              suffix="%/yr"
              min={0}
              max={20}
              step={0.5}
              value={v.rentGrowthPct}
              onChange={set("rentGrowthPct")}
            />
            <NumberInput
              label="Investment return"
              suffix="%/yr"
              min={0}
              max={20}
              step={0.5}
              value={v.investReturnPct}
              onChange={set("investReturnPct")}
            />
            <NumberInput
              label="Upkeep, society, tax"
              suffix="%/yr"
              min={0}
              max={10}
              step={0.1}
              value={v.ownershipCostPct}
              onChange={set("ownershipCostPct")}
              hint="of the home's value"
            />
            <NumberInput
              label="Stamp duty & fees"
              suffix="%"
              min={0}
              max={20}
              step={0.5}
              value={v.upfrontCostPct}
              onChange={set("upfrontCostPct")}
            />
          </div>
        </Disclosure>
        <Button
          size="lg"
          disabled={!ready || r.busy}
          onClick={() =>
            r.run(key, () =>
              api.rentVsBuy({
                price: v.price!,
                monthlyRent: v.monthlyRent!,
                downPaymentPct: v.downPaymentPct!,
                upfrontCostPct: v.upfrontCostPct!,
                loanRatePct: v.loanRatePct!,
                tenureMonths: Math.round(v.tenureYears! * 12),
                rentGrowthPct: v.rentGrowthPct!,
                appreciationPct: v.appreciationPct!,
                ownershipCostPct: v.ownershipCostPct!,
                investReturnPct: v.investReturnPct!,
                years: Math.round(v.years!),
              }),
            )
          }
        >
          {r.busy ? <Loader2 className="animate-spin" /> : <Scale />}{" "}
          {res ? "Compare again" : "Compare"}
        </Button>
        {r.error ? <Notice tone="error">{r.error}</Notice> : null}
      </Card>

      {res && last ? (
        <Card className={cn("transition-opacity", stale && "opacity-60")}>
          {stale ? (
            <span className="w-fit rounded-full bg-caution-50 px-3 py-1 text-[12.5px] font-medium text-caution-text">
              Inputs changed — compare again to update
            </span>
          ) : null}
          <div className="flex flex-col gap-1" aria-live="polite">
            <h2 className="text-[20px] leading-snug font-extrabold text-balance">
              {res.winner === "even"
                ? `After ${last.year} years, buying and renting come out about level`
                : `After ${last.year} years, ${res.winner === "buy" ? "buying" : "renting and investing the difference"} is ahead by ${formatINR(Math.abs(res.difference))}`}
            </h2>
            <p className="text-[14px] text-pretty text-ink-700">
              {res.breakevenAppreciationPct !== null
                ? `The tipping point: buying wins over ${last.year} years only if home prices grow faster than ${res.breakevenAppreciationPct}% a year.`
                : "Within 0–20% yearly price growth, the answer doesn't flip."}
              {res.breakevenYear !== null && res.winner === "buy"
                ? ` Buying pulls ahead from year ${res.breakevenYear}.`
                : ""}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4 border-y border-line py-4 sm:grid-cols-4">
            <Big
              label="Cash to buy"
              value={formatINR(res.upfrontCash)}
              note="down payment + fees"
            />
            <Big label="EMI" value={formatINR(res.emi)} />
            <Big
              label="Buy: worth"
              value={formatINR(last.buyerWealth)}
              note="equity + invested savings"
              tone={res.winner === "buy" ? "good" : undefined}
            />
            <Big
              label="Rent: worth"
              value={formatINR(last.renterWealth)}
              note="invested portfolio"
              tone={res.winner === "rent" ? "good" : undefined}
            />
          </div>
          <RentBuyChart years={res.years} />
          <p className="text-[12px] text-ink-400">
            Each month the buyer pays the EMI plus upkeep; the renter pays rent and invests whatever
            the buyer would have spent beyond it (and the buyer invests the difference when owning
            is cheaper). The renter starts by investing the down payment and fees. Not modelled: tax
            benefits on home loans, selling costs, and the non-financial value of owning.
          </p>
        </Card>
      ) : (
        <Card className="items-center justify-center py-12 text-center">
          <Scale className="size-6 text-ink-400" aria-hidden />
          <p className="max-w-sm text-[14px] text-ink-500">
            Enter the price and a comparable rent, then compare. You&apos;ll see both paths year by
            year and the price growth at which the answer flips.
          </p>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- prepay vs invest

function PrepayVsInvest() {
  const [v, setV] = useState({
    outstanding: 4_000_000 as Num,
    loanRatePct: 8.5 as Num,
    remainingYears: 15 as Num,
    lumpSum: 500_000 as Num,
    investReturnPct: 10 as Num,
    taxOnGainsPct: 12.5 as Num,
  });
  const r = useRunner<PrepayVsInvestResult>();
  const set = (k: keyof typeof v) => (x: Num) => setV({ ...v, [k]: x });
  const key = JSON.stringify(v);
  const ready =
    Object.values(v).every((x) => x !== null) &&
    (v.outstanding ?? 0) >= 1000 &&
    (v.lumpSum ?? 0) >= 1000;
  const stale = r.result !== null && r.ranWith !== key;
  const res = r.result;

  return (
    <div className="grid items-start gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
      <Card>
        <h2 className="text-[16px] font-bold">Your loan and the money</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <MoneyInput
              label="Loan outstanding"
              value={v.outstanding}
              onChange={set("outstanding")}
            />
          </div>
          <NumberInput
            label="Loan rate"
            suffix="% p.a."
            min={0}
            max={30}
            step={0.05}
            value={v.loanRatePct}
            onChange={set("loanRatePct")}
          />
          <NumberInput
            label="Years left"
            suffix="years"
            min={1}
            max={30}
            step={0.5}
            value={v.remainingYears}
            onChange={set("remainingYears")}
          />
          <div className="col-span-2">
            <MoneyInput
              label="Lump sum available"
              value={v.lumpSum}
              onChange={set("lumpSum")}
              hint="bonus, maturity, sale proceeds"
            />
          </div>
          <NumberInput
            label="Investment return"
            suffix="%/yr"
            min={0}
            max={20}
            step={0.5}
            value={v.investReturnPct}
            onChange={set("investReturnPct")}
          />
          <NumberInput
            label="Tax on gains"
            suffix="%"
            min={0}
            max={50}
            step={0.5}
            value={v.taxOnGainsPct}
            onChange={set("taxOnGainsPct")}
            hint="when you withdraw"
          />
        </div>
        <Button
          size="lg"
          disabled={!ready || r.busy}
          onClick={() =>
            r.run(key, () =>
              api.prepayVsInvest({
                outstanding: v.outstanding!,
                loanRatePct: v.loanRatePct!,
                remainingMonths: Math.max(1, Math.round(v.remainingYears! * 12)),
                lumpSum: v.lumpSum!,
                investReturnPct: v.investReturnPct!,
                taxOnGainsPct: v.taxOnGainsPct!,
              }),
            )
          }
        >
          {r.busy ? <Loader2 className="animate-spin" /> : <Scale />}{" "}
          {res ? "Compare again" : "Compare"}
        </Button>
        {r.error ? <Notice tone="error">{r.error}</Notice> : null}
      </Card>

      {res ? (
        <Card className={cn("transition-opacity", stale && "opacity-60")}>
          {stale ? (
            <span className="w-fit rounded-full bg-caution-50 px-3 py-1 text-[12.5px] font-medium text-caution-text">
              Inputs changed — compare again to update
            </span>
          ) : null}
          <div className="flex flex-col gap-1" aria-live="polite">
            <h2 className="text-[20px] leading-snug font-extrabold text-balance">
              {res.winner === "even"
                ? "Prepaying and investing come out about level"
                : `${res.winner === "prepay" ? "Prepaying" : "Investing"} comes out ahead by ${formatINR(Math.abs(res.difference))}`}
            </h2>
            <p className="text-[14px] text-pretty text-ink-700">
              {res.breakevenReturnPct !== null
                ? `Investing only wins if you reliably earn more than ${res.breakevenReturnPct}% a year after costs — the loan's ${v.loanRatePct}% is a guaranteed return.`
                : "Within 0–30% returns, the answer doesn't flip."}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div
              className={cn(
                "flex flex-col gap-3 rounded-xl border p-4",
                res.winner === "prepay" ? "border-brand-600" : "border-line",
              )}
            >
              <h3 className="text-[14px] font-bold">Prepay, keep the EMI</h3>
              <Big label="Interest saved" value={formatINR(res.prepay.interestSaved)} tone="good" />
              <Big
                label="Loan ends"
                value={`${res.prepay.monthsSaved} months sooner`}
                note={`after ${res.prepay.monthsToClose} more EMIs of ${formatINR(res.emi)}`}
              />
              <Big
                label="Worth at the original end date"
                value={formatINR(res.prepay.corpusAtOriginalEnd)}
                note="freed EMIs invested, after tax"
              />
            </div>
            <div
              className={cn(
                "flex flex-col gap-3 rounded-xl border p-4",
                res.winner === "invest" ? "border-brand-600" : "border-line",
              )}
            >
              <h3 className="text-[14px] font-bold">Invest the lump sum</h3>
              <Big label="Tax on gains" value={formatINR(res.invest.gainsTax)} />
              <Big label="Loan" value="Unchanged" note={`${formatINR(res.emi)} EMI to the end`} />
              <Big
                label="Worth at the original end date"
                value={formatINR(res.invest.corpusAtOriginalEnd)}
                note="after tax"
              />
            </div>
          </div>
          <p className="text-[12px] text-ink-400">
            Both paths are valued on the date the loan would originally have ended, with the same
            monthly outgoings until then. Not modelled: home-loan tax deductions you may lose by
            prepaying, prepayment charges (usually nil on floating-rate home loans), and the value
            of keeping cash liquid.
          </p>
        </Card>
      ) : (
        <Card className="items-center justify-center py-12 text-center">
          <Scale className="size-6 text-ink-400" aria-hidden />
          <p className="max-w-sm text-[14px] text-ink-500">
            Enter your loan and the lump sum, then compare. You&apos;ll see the interest saved and
            the return investing would need to beat it.
          </p>
        </Card>
      )}
    </div>
  );
}
