"use client";

import { ArrowDownRight, ArrowRight, ArrowUpRight, Bell, CalendarClock, Check, ChevronRight, Copy, Landmark, ReceiptText, Sparkles, TrendingDown, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CashChart, SalesCostsChart } from "@/components/charts";
import { EvidenceButton } from "@/components/evidence";
import { ReminderSheet } from "@/components/reminder";
import { Button, Card, cx, ErrorNote, Loading, Pill, SectionTitle, toneBg, ToneIcon, toneText } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { inr, pct, short } from "@/lib/format";
import type { AttentionItem, Home, Todo } from "@/lib/types";

const ICONS: Record<string, React.ElementType> = {
  customer: UserRound,
  bill: ReceiptText,
  copy: Copy,
  spark: Sparkles,
  trend: TrendingDown,
  bank: Landmark,
  alert: Bell,
};

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function HomePage() {
  const { data, error, loading, reload } = useApi<Home>("/api/home");
  const [hello, setHello] = useState("Hello");
  useEffect(() => setHello(greeting()), []);

  if (error) return <ErrorNote message={error} retry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm text-ink-2">{hello}</p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[1.75rem]">{data.business.replace(" (fictional)", "")}</h1>
        <p className="text-sm text-muted">Based on your records up to {data.as_of_label}</p>
      </header>

      <Hero home={data} />

      {data.attention.length > 0 && <Attention items={data.attention} onChange={reload} />}

      <div className="grid gap-6 lg:grid-cols-2">
        {data.month && <MonthCard home={data} />}
        {data.spending.length > 0 && <Spending home={data} />}
      </div>

      {data.trend.length > 1 && (
        <Card>
          <SectionTitle>Sales and running costs, month by month</SectionTitle>
          <SalesCostsChart data={data.trend} />
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {data.upcoming.length > 0 && <Upcoming home={data} />}
        <Todos />
      </div>
    </div>
  );
}

function Hero({ home }: { home: Home }) {
  const { status, cash } = home;
  return (
    <Card className="overflow-hidden p-0">
      <div className={cx("flex items-start gap-3 px-5 py-4 sm:px-6", toneBg[status.tone])}>
        <ToneIcon tone={status.tone} className="mt-0.5 size-6 shrink-0" />
        <div>
          <p className={cx("text-lg font-semibold leading-snug", status.tone === "neutral" ? "text-ink" : toneText[status.tone])}>{status.headline}</p>
          <p className="mt-0.5 text-[0.95rem] text-ink-2">{status.detail}</p>
        </div>
      </div>
      {cash.known ? (
        <div className="grid gap-4 p-5 sm:p-6 md:grid-cols-[minmax(0,17rem)_1fr] md:items-center">
          <div>
            <p className="text-sm text-ink-2">Money in the bank today</p>
            <p className="num mt-1 text-4xl font-semibold tracking-tight" title={cash.exact}>
              {cash.label}
            </p>
            {cash.reconciled && (
              <Pill tone="good" className="mt-2">
                <Check className="size-3.5" /> Matches your bank statement
              </Pill>
            )}
            <dl className="mt-4 space-y-1.5 text-sm">
              {cash.months_of_costs != null && (
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-2">Covers running costs for</dt>
                  <dd className="num font-medium">{cash.months_of_costs} months</dd>
                </div>
              )}
              {cash.in_90_days != null && (
                <div className="flex justify-between gap-4">
                  <dt className="text-ink-2">Expected in 90 days</dt>
                  <dd className="num font-medium">{short(cash.in_90_days)}</dd>
                </div>
              )}
            </dl>
            <EvidenceButton evidence={cash.evidence} className="mt-4" />
          </div>
          <div className="-mx-2">
            <CashChart history={cash.history ?? []} outlook={cash.outlook ?? []} cushion={cash.cushion} />
            <p className="px-2 text-xs text-muted">Solid: your actual balance. Dashed: expected, from bills, invoices and your usual spending — not a guarantee.</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-4 p-5 sm:p-6">
          <p className="max-w-lg text-ink-2">Type in the closing balance from your bank statement or banking app — it takes ten seconds. Then you&apos;ll see your cash, how long it lasts and warnings before it runs low.</p>
          <Link href="/data/#balance">
            <Button>Add bank balance</Button>
          </Link>
        </div>
      )}
    </Card>
  );
}

function Attention({ items, onChange }: { items: AttentionItem[]; onChange: () => void }) {
  const router = useRouter();
  const [remind, setRemind] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<string, boolean>>({});
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const [all, setAll] = useState(false);
  const remaining = items.filter((i) => !hidden[i.id]);
  const visible = all ? remaining : remaining.slice(0, 4);

  const act = async (i: AttentionItem) => {
    const a = i.action;
    if (a.type === "remind" && a.customer) setRemind(a.customer);
    else if (a.type === "review") router.push(`/money/?ids=${(a.ids ?? []).join(",")}`);
    else if (a.type === "add_balance") router.push("/data/#balance");
    else if (a.type === "open" && a.href) router.push(a.href);
    else if (a.type === "todo" && a.text) {
      await post("/api/todos", { text: a.text, reason: i.title });
      setAdded((s) => ({ ...s, [i.id]: true }));
      onChange();
    }
  };

  if (!visible.length) return null;
  return (
    <section>
      <SectionTitle>
        Needs your attention <span className="ml-1 text-ink-2 font-normal">({remaining.length})</span>
      </SectionTitle>
      <div className="grid gap-3 md:grid-cols-2">
        {visible.map((i) => {
          const I = ICONS[i.icon] ?? Bell;
          return (
            <Card key={i.id} className="flex gap-3.5 p-4">
              <span className={cx("grid size-10 shrink-0 place-items-center rounded-full", toneBg[i.tone])}>
                <I className={cx("size-5", toneText[i.tone])} aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold leading-snug">{i.title}</p>
                  <button onClick={() => setHidden((h) => ({ ...h, [i.id]: true }))} className="-mr-1 -mt-1 rounded-full p-1 text-muted hover:bg-canvas hover:text-ink" aria-label="Hide for now">
                    <X className="size-4" />
                  </button>
                </div>
                <p className="mt-0.5 text-sm text-ink-2">{i.body}</p>
                <Button size="sm" variant={added[i.id] ? "secondary" : "primary"} className="mt-3" onClick={() => act(i)} disabled={added[i.id]}>
                  {added[i.id] ? (
                    <>
                      <Check className="size-4" /> Added to to-dos
                    </>
                  ) : (
                    <>
                      {i.action.label} <ArrowRight className="size-4" />
                    </>
                  )}
                </Button>
              </div>
            </Card>
          );
        })}
      </div>
      {remaining.length > visible.length && (
        <Button variant="ghost" className="mt-2" onClick={() => setAll(true)}>
          Show {remaining.length - visible.length} more
        </Button>
      )}
      <ReminderSheet customer={remind} onClose={() => setRemind(null)} />
    </section>
  );
}

function Change({ value, good }: { value: number | null | undefined; good: "up" | "down" }) {
  if (value == null || Math.abs(value) < 0.5) return null;
  const up = value > 0;
  const isGood = (up && good === "up") || (!up && good === "down");
  const I = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={cx("inline-flex items-center text-xs font-medium", value === 0 ? "text-muted" : isGood ? "text-good" : "text-bad")}>
      <I className="size-3.5" aria-hidden />
      {pct(value)}
    </span>
  );
}

function MonthCard({ home }: { home: Home }) {
  const m = home.month!;
  const prev = m.previous;
  const rows = [
    { label: "Sales received", value: m.sales, change: m.change?.sales, good: "up" as const },
    { label: "Running costs paid", value: m.costs, change: m.change?.costs, good: "down" as const },
  ];
  return (
    <Card>
      <SectionTitle action={prev && <span className="text-xs text-muted">vs {prev.label.split(" ")[0]}</span>}>{m.label}</SectionTitle>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.label} className="flex items-baseline justify-between gap-3">
            <span className="text-ink-2">{r.label}</span>
            <span className="flex items-baseline gap-2">
              <span className="num text-lg font-medium">{short(r.value)}</span>
              <span className="w-12 text-right">
                <Change value={r.change} good={r.good} />
              </span>
            </span>
          </div>
        ))}
        <div className="flex items-baseline justify-between gap-3 border-t border-line pt-3">
          <span>
            <span className="font-medium">{m.profit >= 0 ? "Profit" : "Loss"}</span> <span className="text-xs text-muted">(estimate)</span>
          </span>
          <span className="flex items-baseline gap-2">
            <span className={cx("num text-xl font-semibold", m.profit < 0 && "text-bad")}>{short(m.profit)}</span>
            <span className="w-12 text-right">
              <Change value={m.change?.profit} good="up" />
            </span>
          </span>
        </div>
      </div>
      {home.insight && (
        <div className={cx("mt-4 rounded-2xl p-3.5 text-sm", toneBg[home.insight.tone])}>
          <p className="text-ink">{home.insight.text}</p>
          <Link href={`/ask/?q=${encodeURIComponent(home.insight.ask)}`} className="mt-1.5 inline-flex items-center gap-1 font-medium text-brand hover:underline">
            Ask FinPilot why <ChevronRight className="size-4" />
          </Link>
        </div>
      )}
      <div className="mt-4 flex items-center justify-between">
        <EvidenceButton evidence={m.evidence} label="How is profit worked out?" />
        <Link href="/money/?tab=profit" className="text-sm font-medium text-ink-2 hover:text-ink">
          All months →
        </Link>
      </div>
    </Card>
  );
}

function Spending({ home }: { home: Home }) {
  const max = Math.max(...home.spending.map((s) => s.amount));
  return (
    <Card>
      <SectionTitle action={<span className="text-xs text-muted">{home.month?.label}</span>}>Where your money went</SectionTitle>
      <ul className="space-y-3">
        {home.spending.map((s) => (
          <li key={s.category}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium">{s.category}</span>
              <span className="flex items-baseline gap-2">
                <span className="num">{inr(s.amount)}</span>
                <span className="w-12 text-right">
                  <Change value={s.change_pct} good="down" />
                </span>
              </span>
            </div>
            <div className="h-2 rounded-full bg-canvas" title={`${s.category}: ${inr(s.amount)}`}>
              <div className="h-2 rounded-full bg-out" style={{ width: `${Math.max(2, (s.amount / max) * 100)}%` }} />
            </div>
          </li>
        ))}
      </ul>
      <Link href="/money/?dir=out" className="mt-4 inline-block text-sm font-medium text-ink-2 hover:text-ink">
        See all payments →
      </Link>
    </Card>
  );
}

function Upcoming({ home }: { home: Home }) {
  return (
    <Card>
      <SectionTitle action={home.upcoming_total != null && <span className="num text-sm font-medium">{inr(home.upcoming_total)}</span>}>Bills in the next 14 days</SectionTitle>
      <ul className="divide-y divide-line">
        {home.upcoming.map((u) => (
          <li key={u.date + u.name + u.amount} className="flex items-center gap-3 py-2.5">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-canvas text-center text-[0.7rem] leading-tight font-medium text-ink-2">
              {u.day.split(" ").map((p) => (
                <span key={p} className="block">
                  {p}
                </span>
              ))}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{u.what || u.name}</p>
              <p className="truncate text-xs text-muted">{u.name}</p>
            </div>
            <span className="num font-medium">{inr(u.amount)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Todos() {
  const { data, reload } = useApi<Todo[]>("/api/todos");
  const open = (data ?? []).filter((t) => t.status === "open");
  const decide = async (id: number, status: "done" | "dismissed") => {
    await post(`/api/todos/${id}`, { status });
    reload();
  };
  useEffect(() => {
    const h = () => reload();
    window.addEventListener("focus", h);
    return () => window.removeEventListener("focus", h);
  }, [reload]);
  return (
    <Card>
      <SectionTitle>
        <span className="inline-flex items-center gap-2">
          <CalendarClock className="size-5 text-ink-2" aria-hidden /> Your to-dos
        </span>
      </SectionTitle>
      {open.length === 0 ? (
        <p className="text-sm text-ink-2">Nothing pending. When you or FinPilot suggest an action — like paying a bill — it lands here for you to approve. FinPilot never pays or sends anything itself.</p>
      ) : (
        <ul className="divide-y divide-line">
          {open.map((t) => (
            <li key={t.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{t.text}</p>
                {t.reason && <p className="truncate text-xs text-muted">{t.reason}</p>}
              </div>
              <Button size="sm" variant="secondary" onClick={() => decide(t.id, "done")} aria-label={`Mark done: ${t.text}`}>
                <Check className="size-4" /> Done
              </Button>
              <button onClick={() => decide(t.id, "dismissed")} className="rounded-full p-1.5 text-muted hover:bg-canvas" aria-label={`Dismiss: ${t.text}`}>
                <X className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

