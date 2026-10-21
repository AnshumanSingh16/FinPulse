import { inr, short } from "@/lib/format";
import type { Evidence } from "@/lib/types";

export type T = (s: string, v?: Record<string, string | number>) => string;

export interface Summary {
  lowest: number;
  lowest_date: string;
  end: number;
  below_safety_from: string | null;
  runs_out: string | null;
  safe: boolean;
  free_cash_today: number;
  spendable_today: number;
  days_to_trouble: number | null;
}
export interface Odds {
  sims: number;
  p_safe: number;
  p_short: number;
  bad_case_lowest: number;
}
export interface Move {
  id: string;
  kind: "collect" | "defer" | "pause" | "reserve" | "borrow" | "discount";
  agent: string;
  party: string;
  amount: number;
  monthly?: number;
  items: string[];
  days_late?: number;
  from_date?: string;
  to_date?: string;
  due?: string;
  impact: number;
  suggested: boolean;
  backup?: boolean;
  odds_with_plan?: number;
  interest_if_used?: number;
  invoice?: number;
  cost?: number;
  state: "open" | "approved" | "done";
}
export interface Activity {
  id?: number;
  book_date: string;
  agent: string;
  tone: string;
  text: string;
  action: { type: "remind"; party: string } | { type: "plan_b" } | null;
}
export interface PlanB {
  if_fails: string;
  checkpoint: string;
  then: string[];
  p_safe: number;
  backup: { amount: number; p_safe: number; interest_if_used: number } | null;
}
export interface Plan {
  status: string;
  message?: string;
  as_of: string;
  business: string;
  is_demo: boolean;
  today: number;
  safety: number;
  default_safety: number | null;
  baseline: Summary;
  with_suggested: Summary;
  with_approved: Summary;
  plan_basis: "approved" | "suggested";
  series: { baseline: { date: string; balance: number }[]; plan: { date: string; balance: number }[] };
  causes: { date: string; label: string; amount: number }[];
  at_risk: { party: string; amount: number; next_due: string; oldest_late_days: number }[];
  moves: Move[];
  odds: { baseline: Odds; suggested: Odds; approved: Odds | null; target: number };
  weekly: { start: string; end: string; closing: number }[];
  changes: { tone: string; text: string }[];
  plan_b: PlanB[];
  watching: { move_id: string; party: string; checkpoint: string; kind: string }[];
  activity: Activity[];
  clock: { date: string; days_moved: number };
  search: { combinations: number; stress_tested: number; sims_each: number;
            plans: { moves: string[]; cost: number; lowest: number; reaches_safety: boolean; p_safe: number }[] };
  events: { id: number; date: string; amount: number; label: string }[];
  evidence: Evidence;
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function day(iso: string | null | undefined, lang = "en") {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
}

export function moveTitle(m: Move, t: T, lang: string) {
  if (m.kind === "collect") return t("Collect {amt} from {who}", { amt: short(m.amount), who: m.party });
  if (m.kind === "defer") return t("Ask {who} to move {bill} to {date}", { who: m.party, bill: m.items[0], date: day(m.to_date, lang) });
  if (m.kind === "pause") return m.party === "Owner Drawings" ? t("Pause owner drawings for 60 days") : t("Pause marketing spend for 60 days");
  if (m.kind === "borrow") return t("Keep a {amt} overdraft ready", { amt: short(m.amount) });
  if (m.kind === "discount") return t("Offer {who} 2% off to pay {amt} by {date}", { who: m.party, amt: short(m.invoice ?? 0), date: day(m.to_date, lang) });
  return t("Set aside {amt} for GST due {date}", { amt: short(m.amount), date: day(m.due, lang) });
}

export function moveDetail(m: Move, t: T, lang: string) {
  if (m.kind === "collect") return t("{n} invoice(s) overdue, oldest {d} days. Assumes they pay within a week of your reminder.", { n: m.items.length, d: m.days_late ?? 0 });
  if (m.kind === "defer") return t("{amt} due {from}. Assumes they agree to 3 more weeks.", { amt: inr(m.amount), from: day(m.from_date, lang) });
  if (m.kind === "pause") return t("About {amt} a month on average; pausing keeps {kept} in the bank.", { amt: short(m.monthly ?? 0), kept: short(m.amount) });
  if (m.kind === "discount") return t("Due {date}. Costs {amt}; assumes they accept (7 in 10 do in the simulation).", { date: day(m.from_date, lang), amt: short(m.cost ?? 0) });
  if (m.kind === "borrow") return t("Only if the plan falls short. Using all of it for 90 days would cost about {amt} in interest (at about 14% a year).", { amt: short(m.interest_if_used ?? 0) });
  return t("Your typical monthly GST payment, kept aside so it isn't spent by mistake.");
}

/** Where the business stands, in one tone. */
export function standing(p: Plan): "out" | "tight" | "unsure" | "ok" {
  const anyApproved = p.moves.some((m) => m.state !== "open");
  const b = anyApproved ? p.with_approved : p.baseline;
  const odds = anyApproved && p.odds.approved ? p.odds.approved : p.odds.baseline;
  if (b.runs_out) return "out";
  if (!b.safe) return "tight";
  if (odds.p_safe < p.odds.target) return "unsure";
  return "ok";
}

export function currentOdds(p: Plan) {
  const anyApproved = p.moves.some((m) => m.state !== "open");
  return anyApproved && p.odds.approved ? p.odds.approved : p.odds.baseline;
}

/** Short name for a move id, for comparison tables. */
export function moveShort(id: string, p: Plan, t: T, lang: string) {
  const m = p.moves.find((x) => x.id === id);
  if (m) return moveTitle(m, t, lang);
  const [kind, rest] = [id.split(":")[0], id.slice(id.indexOf(":") + 1)];
  if (kind === "collect") return t("collect from {who}", { who: rest });
  if (kind === "pause") return rest === "Owner Drawings" ? t("pause owner drawings") : t("pause marketing");
  return id;
}
