"use client";

import {
  ArrowDownLeft, ArrowDownRight, ArrowRight, ArrowUpRight, Bell, CalendarClock, Check, ChevronRight, Copy, HandCoins, Landmark, MessageCircle,
  Play, ReceiptText, ShieldCheck, Sparkles, Store, Tag, TrendingDown, Undo2, UserRound, Wallet, X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useContext, useEffect, useState } from "react";
import { CatIcon } from "@/components/cat";
import { HeroCashChart, SalesCostsChart } from "@/components/charts";
import { DataVersion } from "@/components/data-version";
import { EvidenceButton } from "@/components/evidence";
import { CountUp, useToast } from "@/components/fx";
import { Gauge } from "@/components/gauge";
import { useQuickEntry } from "@/components/quick-entry";
import { BulkReminders, ReminderSheet } from "@/components/reminder";
import { StoryViewer, type StoryCard } from "@/components/story";
import { Button, Card, cx, ErrorNote, Loading, SectionTitle, toneBg, toneText } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { inr, pct, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { AttentionItem, Home, Todo } from "@/lib/types";

const ICONS: Record<string, React.ElementType> = { customer: UserRound, bill: ReceiptText, copy: Copy, spark: Sparkles, trend: TrendingDown, bank: Landmark, alert: Bell, wallet: Wallet, tag: Tag };

interface Health {
  status: string;
  score: number;
  grade: string;
  change: number | null;
  focus: { label: string; tip: string; href: string } | null;
}
interface Story {
  status: string;
  title: string;
  range: string;
  cards: StoryCard[];
  this?: { sales: number };
}

export default function HomePage() {
  const { t } = useT();
  const { data, error, loading, reload } = useApi<Home>("/api/home");
  const [hello, setHello] = useState("Hello");
  useEffect(() => {
    const h = new Date().getHours();
    setHello(h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening");
  }, []);

  if (error) return <ErrorNote message={error} retry={reload} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <header className="rise">
        <p className="eyebrow">{t(hello)}</p>
        <h1 className="mt-1 text-3xl sm:text-4xl">{data.business.replace(" (fictional)", "")}</h1>
        <p className="text-sm text-muted">{t("Based on your records up to {date}", { date: data.as_of_label })}</p>
      </header>

      <Hero home={data} />
      <QuickActions />

      <div className="grid gap-4 md:grid-cols-2">
        <HealthCard />
        <StoryCardTile />
      </div>

      {data.attention.length > 0 && <Attention items={data.attention} onChange={reload} />}

      <div className="grid gap-6 lg:grid-cols-2">
        {data.month && <MonthCard home={data} />}
        {data.spending.length > 0 && <Spending home={data} />}
      </div>

      {data.trend.length > 1 && (
        <Card>
          <SectionTitle>{t("Sales and running costs, month by month")}</SectionTitle>
          <SalesCostsChart data={data.trend} />
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {data.upcoming.length > 0 && <Upcoming home={data} />}
        <Todos />
        <RecentEntries />
      </div>
    </div>
  );
}

function Hero({ home }: { home: Home }) {
  const { t } = useT();
  const { status, cash } = home;
  const grad = status.tone === "bad" ? "grad-hero-bad" : status.tone === "caution" ? "grad-hero-caution" : "grad-hero";
  return (
    <section className={cx("rise rise-1 overflow-hidden rounded-[1.75rem] p-5 shadow-xl shadow-black/10 sm:p-7", grad)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-xl">
          <p className="display text-2xl leading-tight sm:text-[1.7rem]">{status.headline}</p>
          <p className="mt-1 text-sm text-white/80">{status.detail}</p>
        </div>
        {cash.reconciled && (
          <span className="glass inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium">
            <ShieldCheck className="size-3.5" /> {t("Matches your bank statement")}
          </span>
        )}
      </div>
      {cash.known ? (
        <div className="mt-5 grid gap-4 md:grid-cols-[minmax(0,16rem)_1fr] md:items-end">
          <div>
            <p className="eyebrow !text-white/55">{t("Money in the bank today")}</p>
            <p className="display num mt-2 text-6xl" title={cash.exact}>
              <CountUp value={cash.amount ?? 0} format={short} />
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {cash.months_of_costs != null && <span className="glass rounded-full px-3 py-1 text-xs font-medium">{t("Covers {n} months of costs", { n: cash.months_of_costs })}</span>}
              {cash.in_90_days != null && (
                <span className="glass rounded-full px-3 py-1 text-xs font-medium">
                  {t("Expected in 90 days")}: {short(cash.in_90_days)}
                </span>
              )}
            </div>
            <EvidenceButton evidence={cash.evidence} label={t("How do we know?")} className="mt-4 !text-white/90" />
          </div>
          <div className="-mx-2">
            <HeroCashChart history={cash.history ?? []} outlook={cash.outlook ?? []} />
            <p className="px-2 text-[0.7rem] text-white/65">{t("Solid: your actual balance. Dashed: expected — not a guarantee.")}</p>
          </div>
        </div>
      ) : (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
          <p className="max-w-lg text-white/85">{t("Type in the closing balance from your bank statement or banking app — it takes ten seconds.")}</p>
          <Link href="/data/#balance">
            <Button className="">{t("Add bank balance")}</Button>
          </Link>
        </div>
      )}
    </section>
  );
}

function QuickActions() {
  const { t } = useT();
  const qe = useQuickEntry();
  const [bulk, setBulk] = useState(false);
  const items = [
    { label: "Add sale", I: Store, grad: "grad-mint", go: () => qe.open({ kind: "sale" }) },
    { label: "Add expense", I: ArrowUpRight, grad: "grad-sunset", go: () => qe.open({ kind: "expense" }) },
    { label: "Gave udhaar", I: HandCoins, grad: "grad-violet", go: () => qe.open({ kind: "credit_sale" }) },
    { label: "Got payment", I: ArrowDownLeft, grad: "grad-ocean", go: () => qe.open({ kind: "payment_in" }) },
    { label: "Remind all", I: MessageCircle, grad: "grad-berry", go: () => setBulk(true) },
  ];
  return (
    <>
      <div className="rise rise-2 no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 sm:mx-0 sm:grid sm:grid-cols-5 sm:px-0">
        {items.map(({ label, I, grad, go }) => (
          <button key={label} onClick={go} className="card flex min-w-[6.5rem] flex-col items-center gap-2 p-3 text-center text-sm font-medium transition hover:-translate-y-0.5 hover:shadow-lg">
            <span className={cx("grid size-12 place-items-center rounded-2xl shadow-md", grad)}>
              <I className="size-6" aria-hidden />
            </span>
            {t(label)}
          </button>
        ))}
      </div>
      {bulk && <BulkReminders onClose={() => setBulk(false)} />}
    </>
  );
}

function HealthCard() {
  const { t } = useT();
  const { data } = useApi<Health>("/api/health");
  if (!data || data.status !== "ok") return <Card className="h-44 animate-pulse" />;
  return (
    <Link href="/health/" className="card rise rise-3 group flex items-center gap-4 p-5 transition hover:shadow-lg">
      <div className="text-ink">
        <Gauge score={data.score} size={150} label={t("Health score")} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-ink-2">{t("Health score")}</p>
        <p className="display text-2xl">{data.grade}</p>
        {data.change != null && data.change !== 0 && (
          <p className={cx("text-sm font-medium", data.change > 0 ? "text-good" : "text-bad")}>
            {data.change > 0 ? "▲" : "▼"} {Math.abs(data.change)} {t("since last month")}
          </p>
        )}
        {data.focus && <p className="mt-1 line-clamp-2 text-xs text-ink-2">{data.focus.label}: {data.focus.tip}</p>}
        <span className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand group-hover:underline">
          {t("Health score")} <ChevronRight className="size-4" />
        </span>
      </div>
    </Link>
  );
}

function StoryCardTile() {
  const { t } = useT();
  const { data } = useApi<Story>("/api/story");
  const [open, setOpen] = useState(false);
  if (!data) return <Card className="h-44 animate-pulse" />;
  return (
    <>
      <button onClick={() => setOpen(true)} className="rise rise-4 grad-sunset relative flex items-center gap-4 overflow-hidden rounded-[1.5rem] p-5 text-left shadow-lg shadow-black/10 transition hover:brightness-105">
        <div className="flex -space-x-3">
          {["grad-hero", "grad-ocean", "grad-mint"].map((g, i) => (
            <span key={g} className={cx("grid size-14 place-items-center rounded-full ring-4 ring-white/30", g)} style={{ zIndex: 3 - i }}>
              {i === 0 && <Play className="size-6 fill-white" />}
            </span>
          ))}
        </div>
        <div className="min-w-0">
          <p className="text-sm text-white/80">{data.range}</p>
          <p className="display text-2xl">{data.title ?? t("Your week")}</p>
          <p className="truncate text-sm text-white/90">{data.cards[0]?.title}</p>
          <span className="mt-1 inline-block text-xs font-semibold text-white/90 underline underline-offset-2">{t("Tap to see your week")}</span>
        </div>
      </button>
      {open && <StoryViewer cards={data.cards} title={data.title ?? t("Your week")} range={data.range} onClose={() => setOpen(false)} />}
    </>
  );
}

function Attention({ items, onChange }: { items: AttentionItem[]; onChange: () => void }) {
  const { t } = useT();
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
  if (!remaining.length) return null;
  return (
    <section>
      <SectionTitle>
        {t("Needs your attention")} <span className="ml-1 rounded-full bg-bad px-2 py-0.5 text-xs font-bold text-white">{remaining.length}</span>
      </SectionTitle>
      <div className="grid gap-3 md:grid-cols-2">
        {visible.map((i) => {
          const I = ICONS[i.icon] ?? Bell;
          return (
            <Card key={i.id} className={cx("relative flex gap-3.5 overflow-hidden p-4 pl-5")}>
              <span className={cx("absolute inset-y-0 left-0 w-1.5", i.tone === "bad" ? "bg-bad" : i.tone === "caution" ? "bg-[#f59e0b]" : i.tone === "info" ? "bg-info" : "bg-good")} />
              <span className={cx("grid size-11 shrink-0 place-items-center rounded-2xl", toneBg[i.tone])}>
                <I className={cx("size-5", toneText[i.tone])} aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold leading-snug">{i.title}</p>
                  <button onClick={() => setHidden((h) => ({ ...h, [i.id]: true }))} className="-mr-1 -mt-1 rounded-full p-1 text-muted hover:bg-canvas hover:text-ink" aria-label={t("Hide for now")}>
                    <X className="size-4" />
                  </button>
                </div>
                <p className="mt-0.5 text-sm text-ink-2">{i.body}</p>
                <Button size="sm" variant={added[i.id] ? "secondary" : "primary"} className="mt-3" onClick={() => act(i)} disabled={added[i.id]}>
                  {added[i.id] ? (
                    <>
                      <Check className="size-4" /> {t("Added to to-dos")}
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
          {t("Show {n} more", { n: remaining.length - visible.length })}
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
    <span className={cx("inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-semibold", isGood ? "bg-good-50 text-good" : "bg-bad-50 text-bad")}>
      <I className="size-3.5" aria-hidden />
      {pct(value)}
    </span>
  );
}

function MonthCard({ home }: { home: Home }) {
  const { t } = useT();
  const m = home.month!;
  const prev = m.previous;
  const rows = [
    { label: "Sales received", value: m.sales, change: m.change?.sales, good: "up" as const, grad: "grad-mint", I: Store },
    { label: "Running costs paid", value: m.costs, change: m.change?.costs, good: "down" as const, grad: "grad-sunset", I: ArrowUpRight },
  ];
  return (
    <Card>
      <SectionTitle action={prev && <span className="text-xs text-muted">{t("vs {month}", { month: (prev as { short_label?: string }).short_label ?? prev.label })}</span>}>{m.label}</SectionTitle>
      <div className="space-y-3">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-3">
            <span className={cx("grid size-10 place-items-center rounded-2xl", r.grad)}>
              <r.I className="size-5" aria-hidden />
            </span>
            <span className="flex-1 text-ink-2">{t(r.label)}</span>
            <span className="num text-lg font-semibold">{short(r.value)}</span>
            <span className="w-16 text-right">
              <Change value={r.change} good={r.good} />
            </span>
          </div>
        ))}
        <div className={cx("flex items-center justify-between gap-3 rounded-2xl p-4", m.profit >= 0 ? "bg-good-50" : "bg-bad-50")}>
          <span>
            <span className="font-semibold">{t(m.profit >= 0 ? "Profit" : "Loss")}</span> <span className="text-xs text-muted">{t("(estimate)")}</span>
          </span>
          <span className="flex items-center gap-2">
            <span className={cx("display num text-3xl", m.profit < 0 ? "text-bad" : "text-good")}>{short(m.profit)}</span>
            <Change value={m.change?.profit} good="up" />
          </span>
        </div>
      </div>
      {home.insight && (
        <div className={cx("mt-4 rounded-2xl p-4 text-sm", toneBg[home.insight.tone])}>
          <p className="text-ink">{home.insight.text}</p>
          <Link href={`/ask/?q=${encodeURIComponent(home.insight.ask)}`} className="mt-2 inline-flex items-center gap-1 font-semibold text-brand hover:underline">
            <Sparkles className="size-4" /> {t("Ask FinPilot why")} <ChevronRight className="size-4" />
          </Link>
        </div>
      )}
      <div className="mt-4 flex items-center justify-between">
        <EvidenceButton evidence={m.evidence} label={t("How is profit worked out?")} />
        <Link href="/money/?tab=profit" className="text-sm font-medium text-ink-2 hover:text-ink">
          {t("All months")} →
        </Link>
      </div>
    </Card>
  );
}

function Spending({ home }: { home: Home }) {
  const { t } = useT();
  const max = Math.max(...home.spending.map((s) => s.amount));
  return (
    <Card>
      <SectionTitle action={<span className="text-xs text-muted">{home.month?.label}</span>}>{t("Where your money went")}</SectionTitle>
      <ul className="space-y-3.5">
        {home.spending.map((s) => (
          <li key={s.category} className="flex items-center gap-3">
            <CatIcon category={s.category} />
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                <span className="truncate font-medium">{s.category}</span>
                <span className="num font-semibold">{inr(s.amount)}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-2 flex-1 rounded-full bg-canvas">
                  <div className="h-2 rounded-full bg-out" style={{ width: `${Math.max(3, (s.amount / max) * 100)}%` }} />
                </div>
                <span className="w-14 text-right">
                  <Change value={s.change_pct} good="down" />
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>
      <Link href="/money/?dir=out" className="mt-4 inline-block text-sm font-medium text-ink-2 hover:text-ink">
        {t("See all payments")} →
      </Link>
    </Card>
  );
}

function Upcoming({ home }: { home: Home }) {
  const { t } = useT();
  return (
    <Card>
      <SectionTitle action={home.upcoming_total != null && <span className="num text-sm font-semibold">{inr(home.upcoming_total)}</span>}>{t("Bills in the next 14 days")}</SectionTitle>
      <ul className="divide-y divide-line">
        {home.upcoming.map((u) => (
          <li key={u.date + u.name + u.amount} className="flex items-center gap-3 py-2.5">
            <span className="grad-violet grid size-11 shrink-0 place-items-center rounded-2xl text-center text-[0.7rem] leading-tight font-semibold">
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
            <span className="num font-semibold">{inr(u.amount)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Todos() {
  const { t } = useT();
  const { data, reload } = useApi<Todo[]>("/api/todos");
  const open = (data ?? []).filter((x) => x.status === "open");
  const decide = async (id: number, status: "done" | "dismissed") => {
    await post(`/api/todos/${id}`, { status });
    reload();
  };
  return (
    <Card>
      <SectionTitle>
        <span className="inline-flex items-center gap-2">
          <CalendarClock className="size-5 text-brand" aria-hidden /> {t("Your to-dos")}
        </span>
      </SectionTitle>
      {open.length === 0 ? (
        <p className="text-sm text-ink-2">
          {t("Nothing pending. When you or FinPilot suggest an action — like paying a bill — it lands here for you to approve. FinPilot never pays or sends anything itself.")}
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {open.map((x) => (
            <li key={x.id} className="flex items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{x.text}</p>
                {x.reason && <p className="truncate text-xs text-muted">{x.reason}</p>}
              </div>
              <Button size="sm" variant="secondary" onClick={() => decide(x.id, "done")}>
                <Check className="size-4" /> {t("Done")}
              </Button>
              <button onClick={() => decide(x.id, "dismissed")} className="rounded-full p-1.5 text-muted hover:bg-canvas" aria-label="Dismiss">
                <X className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function RecentEntries() {
  const { t } = useT();
  const { refresh } = useContext(DataVersion);
  const toast = useToast();
  const { data } = useApi<{ entries: { id: string; kind: string; summary: string; undone: number; at: string }[] }>("/api/entries");
  const list = (data?.entries ?? []).filter((e) => !e.undone).slice(0, 6);
  if (!list.length) return null;
  const undo = async (id: string) => {
    await post(`/api/entries/${id}/undo`, {});
    refresh();
    toast.show({ text: t("Undone") });
  };
  const KIND_GRAD: Record<string, string> = { sale: "grad-mint", payment_in: "grad-ocean", credit_sale: "grad-violet", expense: "grad-sunset", bill: "grad-berry", payment_out: "grad-night" };
  return (
    <Card>
      <SectionTitle>{t("Recent entries")}</SectionTitle>
      <ul className="divide-y divide-line">
        {list.map((e) => (
          <li key={e.id} className="flex items-center gap-3 py-2.5">
            <span className={cx("size-2.5 shrink-0 rounded-full", KIND_GRAD[e.kind] ?? "grad-violet")} />
            <p className="min-w-0 flex-1 truncate text-sm">{e.summary}</p>
            <button onClick={() => undo(e.id)} className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium text-ink-2 hover:bg-canvas">
              <Undo2 className="size-3.5" /> {t("Undo")}
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
