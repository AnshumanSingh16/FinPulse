"use client";

import { Gift, Landmark, PiggyBank, Plus, ShieldCheck, Sparkles, Target, Trash2, Wrench } from "lucide-react";
import { useContext, useState } from "react";
import { CatIcon } from "@/components/cat";
import { DataVersion } from "@/components/data-version";
import { confetti, useToast } from "@/components/fx";
import { Ring } from "@/components/gauge";
import { Button, Card, cx, Field, Loading, MoneyInput, SectionTitle, Sheet } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";

interface BudgetResp {
  limits: Record<string, number>;
  suggested: Record<string, number>;
  status: {
    month: string;
    days_left: number;
    total_limit: number;
    total_spent: number;
    rows: { category: string; limit: number; spent: number; left: number; pct: number; pace: number; state: "ok" | "near" | "over" }[];
  } | null;
}
interface Goal {
  id: number;
  name: string;
  target: number;
  saved: number;
  target_date: string | null;
  icon: string;
  left: number;
  pct: number;
  done: boolean;
  per_month: number | null;
  months_left: number | null;
}

const GOAL_ICONS: Record<string, { I: React.ElementType; grad: string; color: string }> = {
  gst: { I: Landmark, grad: "grad-violet", color: "#6a44ff" },
  festival: { I: Gift, grad: "grad-sunset", color: "#ff7a59" },
  emergency: { I: ShieldCheck, grad: "grad-mint", color: "#0e9f6e" },
  machine: { I: Wrench, grad: "grad-ocean", color: "#2a78d6" },
  target: { I: Target, grad: "grad-berry", color: "#c2287a" },
};
const TEMPLATES = [
  { name: "GST set-aside", icon: "gst", target: 50000 },
  { name: "Diwali stock fund", icon: "festival", target: 200000 },
  { name: "Emergency fund (3 months)", icon: "emergency", target: 600000 },
  { name: "New machine", icon: "machine", target: 300000 },
];

export default function GoalsPage() {
  const { t } = useT();
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">{t("Goals & budgets")}</h1>
      <Goals />
      <Budgets />
    </div>
  );
}

function Goals() {
  const { t } = useT();
  const { refresh } = useContext(DataVersion);
  const toast = useToast();
  const { data, reload } = useApi<Goal[]>("/api/goals");
  const [adding, setAdding] = useState<null | { name: string; icon: string; target: string; date: string }>(null);
  const [topup, setTopup] = useState<Goal | null>(null);
  const [amt, setAmt] = useState("");

  const create = async () => {
    if (!adding) return;
    await post("/api/goals", { name: adding.name, icon: adding.icon, target: Number(adding.target), target_date: adding.date || null });
    setAdding(null);
    reload();
    refresh();
  };
  const add = async () => {
    if (!topup) return;
    const res = await post<Goal[]>(`/api/goals/${topup.id}`, { add: Number(amt) });
    const g = res.find((x) => x.id === topup.id);
    if (g?.done && !topup.done) confetti();
    toast.show({ text: `${inr(Number(amt))} → ${topup.name}` });
    setTopup(null);
    setAmt("");
    reload();
  };
  const remove = async (g: Goal) => {
    if (!confirm(`Delete “${g.name}”?`)) return;
    await post(`/api/goals/${g.id}`, { delete: true });
    reload();
  };

  return (
    <section>
      <SectionTitle
        action={
          <Button size="sm" onClick={() => setAdding({ name: "", icon: "target", target: "", date: "" })}>
            <Plus className="size-4" /> {t("Add goal")}
          </Button>
        }
      >
        {t("Savings goals")}
      </SectionTitle>
      {!data ? (
        <Loading />
      ) : data.length === 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {TEMPLATES.map((tpl) => {
            const s = GOAL_ICONS[tpl.icon];
            return (
              <button key={tpl.name} onClick={() => setAdding({ name: tpl.name, icon: tpl.icon, target: String(tpl.target), date: "" })} className={cx("rounded-3xl p-5 text-left shadow-lg transition hover:-translate-y-0.5", s.grad)}>
                <s.I className="size-7" />
                <p className="mt-3 font-semibold">{tpl.name}</p>
                <p className="text-sm text-white/80">e.g. {short(tpl.target)}</p>
                <span className="glass mt-3 inline-flex rounded-full px-3 py-1 text-xs font-semibold">
                  <Plus className="mr-1 size-3.5" /> Start
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((g) => {
            const s = GOAL_ICONS[g.icon] ?? GOAL_ICONS.target;
            return (
              <Card key={g.id} className="relative">
                <button onClick={() => remove(g)} className="absolute top-3 right-3 rounded-full p-1.5 text-muted hover:bg-canvas" aria-label={`${t("Delete")} ${g.name}`}>
                  <Trash2 className="size-4" />
                </button>
                <div className="flex items-center gap-4">
                  <div className="relative">
                    <Ring pct={g.pct} size={76} stroke={9} color={s.color} />
                    <span className={cx("absolute inset-0 m-auto grid size-11 place-items-center rounded-full", s.grad)}>
                      <s.I className="size-5" />
                    </span>
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{g.name}</p>
                    <p className="num text-lg font-bold">
                      {short(g.saved)} <span className="text-sm font-medium text-muted">/ {short(g.target)}</span>
                    </p>
                    <p className="text-xs text-ink-2">{g.done ? "🎉 Reached!" : g.per_month ? `${inr(g.per_month)} a month for ${g.months_left} months` : `${short(g.left)} to go`}</p>
                  </div>
                </div>
                <Button size="sm" variant={g.done ? "secondary" : "primary"} className="mt-4 w-full" onClick={() => setTopup(g)}>
                  <PiggyBank className="size-4" /> {t("Add money")}
                </Button>
              </Card>
            );
          })}
        </div>
      )}
      <p className="mt-2 text-xs text-muted">Goals are envelopes to plan with — FinPilot doesn&apos;t move money. Keep the amount aside in your bank yourself.</p>

      {adding && (
        <Sheet open onClose={() => setAdding(null)} title={t("Add goal")}>
          <div className="space-y-4">
            <Field label="Name">
              <input value={adding.name} onChange={(e) => setAdding({ ...adding, name: e.target.value })} className="h-11 w-full rounded-xl border border-line px-3 outline-none focus:border-brand" />
            </Field>
            <Field label="Target">
              <MoneyInput value={adding.target} onChange={(v) => setAdding({ ...adding, target: v })} placeholder="2,00,000" />
            </Field>
            <Field label="By (optional)">
              <input type="date" value={adding.date} onChange={(e) => setAdding({ ...adding, date: e.target.value })} className="h-11 w-full rounded-xl border border-line px-3" />
            </Field>
            <div className="flex gap-2">
              {Object.entries(GOAL_ICONS).map(([k, s]) => (
                <button key={k} onClick={() => setAdding({ ...adding, icon: k })} className={cx("grid size-11 place-items-center rounded-2xl", s.grad, adding.icon === k && "ring-2 ring-ink ring-offset-2")} aria-label={k}>
                  <s.I className="size-5" />
                </button>
              ))}
            </div>
            <Button onClick={create} disabled={!adding.name || !Number(adding.target)} className="w-full">
              <Sparkles className="size-4" /> {t("Save")}
            </Button>
          </div>
        </Sheet>
      )}
      {topup && (
        <Sheet open onClose={() => setTopup(null)} title={`${t("Add money")} · ${topup.name}`}>
          <div className="space-y-4">
            <MoneyInput value={amt} onChange={setAmt} placeholder="10,000" autoFocus />
            <div className="flex flex-wrap gap-2">
              {[1000, 5000, 10000, topup.per_month ?? 0].filter(Boolean).map((v) => (
                <button key={v} onClick={() => setAmt(String(Math.round(v)))} className="rounded-full border border-line px-3 py-1.5 text-sm hover:border-brand">
                  {inr(v)}
                </button>
              ))}
            </div>
            <Button onClick={add} disabled={!Number(amt)} className="w-full">
              {t("Save")}
            </Button>
          </div>
        </Sheet>
      )}
    </section>
  );
}

function Budgets() {
  const { t } = useT();
  const { refresh } = useContext(DataVersion);
  const { data, reload } = useApi<BudgetResp>("/api/budgets");
  const [edit, setEdit] = useState<Record<string, string> | null>(null);
  if (!data) return <Loading />;
  const save = async (limits: Record<string, number | null>) => {
    await post("/api/budgets", { limits });
    setEdit(null);
    reload();
    refresh();
  };
  const st = data.status;
  return (
    <section>
      <SectionTitle
        action={
          <div className="flex gap-2">
            {Object.keys(data.suggested).length > 0 && (
              <Button size="sm" variant="secondary" onClick={() => setEdit(Object.fromEntries(Object.entries({ ...data.suggested, ...data.limits }).map(([k, v]) => [k, String(v)])))}>
                <Sparkles className="size-4" /> {t("Suggest from my spending")}
              </Button>
            )}
          </div>
        }
      >
        {t("Budgets")} {st && <span className="ml-1 text-sm font-normal text-muted">· {st.month}</span>}
      </SectionTitle>
      {!st ? (
        <Card className="flex flex-col items-center gap-3 py-10 text-center">
          <span className="grad-sunset grid size-14 place-items-center rounded-3xl">
            <Target className="size-7" />
          </span>
          <p className="max-w-md text-ink-2">Set a monthly limit for your biggest costs. FinPilot warns you on Home when one is crossed.</p>
          {Object.keys(data.suggested).length > 0 && (
            <Button onClick={() => setEdit(Object.fromEntries(Object.entries(data.suggested).map(([k, v]) => [k, String(v)])))}>
              <Sparkles className="size-4" /> {t("Suggest from my spending")}
            </Button>
          )}
        </Card>
      ) : (
        <Card>
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm text-ink-2">Spent this month</p>
              <p className="num text-3xl font-bold">
                {short(st.total_spent)} <span className="text-base font-medium text-muted">/ {short(st.total_limit)}</span>
              </p>
            </div>
            <p className="text-sm text-ink-2">{st.days_left} days left</p>
          </div>
          <ul className="space-y-4">
            {st.rows.map((r) => (
              <li key={r.category} className="flex items-center gap-3">
                <CatIcon category={r.category} />
                <div className="min-w-0 flex-1">
                  <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2 text-sm">
                    <span className="font-medium">{r.category}</span>
                    <span>
                      <span className={cx("num font-semibold", r.state === "over" ? "text-bad" : "")}>{inr(r.spent)}</span>
                      <span className="text-muted"> / {inr(r.limit)}</span>
                    </span>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-canvas">
                    <div
                      className={cx("h-full rounded-full transition-all", r.state === "over" ? "bg-bad" : r.state === "near" ? "bg-[#f59e0b]" : "bg-good")}
                      style={{ width: `${Math.min(100, r.pct)}%` }}
                    />
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    {r.state === "over" ? `Over by ${inr(-r.left)}` : `${inr(r.left)} left`}
                    {r.state !== "over" && r.pace > r.limit && ` · on pace for ${short(r.pace)}`}
                  </p>
                </div>
              </li>
            ))}
          </ul>
          <Button variant="ghost" className="mt-3" onClick={() => setEdit(Object.fromEntries(Object.entries(data.limits).map(([k, v]) => [k, String(v)])))}>
            Edit limits
          </Button>
        </Card>
      )}
      {edit && (
        <Sheet open onClose={() => setEdit(null)} title={t("Budgets")}>
          <div className="space-y-3">
            {Object.entries(edit).map(([cat, v]) => (
              <div key={cat} className="flex items-center gap-3">
                <CatIcon category={cat} size="sm" />
                <span className="flex-1 truncate text-sm">{cat}</span>
                <div className="w-36">
                  <MoneyInput value={v} onChange={(x) => setEdit({ ...edit, [cat]: x })} />
                </div>
              </div>
            ))}
            <Button className="w-full" onClick={() => save(Object.fromEntries(Object.entries(edit).map(([k, v]) => [k, Number(v) || null])))}>
              {t("Save")}
            </Button>
          </div>
        </Sheet>
      )}
    </section>
  );
}
