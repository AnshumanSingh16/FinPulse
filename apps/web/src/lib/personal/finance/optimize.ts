/**
 * The plan search behind the Strategist agent. Given a plan, it looks for the smallest set of
 * concrete, human-actionable changes that most improve the chance of goals landing on time:
 *
 *   push a goal back · trim a goal's budget · change a loan's down payment or tenure ·
 *   move a goal up the priority order · commit to spending a little less each month
 *
 * Every candidate is scored with the Monte Carlo model (montecarlo.ts) on the same futures
 * (common random numbers), so a change wins on merit, not luck. Each change carries a
 * "disruption" cost — a plan that needs fewer and smaller changes is preferred — and a move is
 * only accepted when it beats that cost. Search is greedy with racing: every candidate is
 * screened on a small sample, the best few are re-scored on a larger one, and the final proposal
 * is checked on fresh futures it was never tuned on.
 */
import { formatINR } from "../../format";
import { simulatePlan, type PlanOdds, type RiskModel, type SimInput } from "./montecarlo";
import { addMonths, type PlanGoal } from "./plan";

export type PlanChange =
  | { kind: "delay"; goalId: string; months: number }
  | { kind: "reduce"; goalId: string; pct: number }
  | { kind: "down_payment"; goalId: string; toPct: number }
  | { kind: "tenure"; goalId: string; toMonths: number }
  | { kind: "raise_priority"; goalId: string }
  | { kind: "spend_less"; monthly: number };

export type ChangeView = PlanChange & { text: string; disruption: number };

type State = { goals: PlanGoal[]; spendingCut: number };

const DISRUPTION = {
  delay: (m: number) => 0.012 + m * 0.0022, // 6 mo ≈ 0.025, 12 ≈ 0.038, 24 ≈ 0.065
  reduce: (pct: number) => pct * 0.003, // 10% ≈ 0.03
  down_payment: 0.015,
  tenure: 0.02,
  raise_priority: 0.012,
  spend_less: (share: number) => share * 0.6, // 5% of spending ≈ 0.03
};

function describe(c: PlanChange, goals: PlanGoal[]): string {
  const g = "goalId" in c ? goals.find((x) => x.id === c.goalId) : undefined;
  const name = g ? `“${g.name}”` : "";
  switch (c.kind) {
    case "delay":
      return `Move ${name} ${c.months} months later, to ${g ? addMonths(g.targetMonth, c.months) : ""}`;
    case "reduce":
      return `Trim ${name}'s budget by ${c.pct}% (to ${formatINR(Math.round((g!.targetAmount * (100 - c.pct)) / 100))})`;
    case "down_payment":
      return `Change ${name}'s down payment from ${g!.downPaymentPct}% to ${c.toPct}%`;
    case "tenure":
      return `Take ${name}'s loan over ${Math.round(c.toMonths / 12)} years instead of ${Math.round(g!.loanTenureMonths / 12)}`;
    case "raise_priority":
      return `Fund ${name} before the goal above it`;
    case "spend_less":
      return `Spend ${formatINR(c.monthly)} less each month`;
  }
}

function apply(s: State, c: PlanChange): State {
  const map = (fn: (g: PlanGoal) => PlanGoal) => ({
    ...s,
    goals: s.goals.map((g) => ("goalId" in c && g.id === c.goalId ? fn(g) : g)),
  });
  switch (c.kind) {
    case "delay":
      return map((g) => ({ ...g, targetMonth: addMonths(g.targetMonth, c.months) }));
    case "reduce":
      return map((g) => ({
        ...g,
        targetAmount: Math.round((g.targetAmount * (100 - c.pct)) / 100),
      }));
    case "down_payment":
      return map((g) => ({ ...g, downPaymentPct: c.toPct }));
    case "tenure":
      return map((g) => ({ ...g, loanTenureMonths: c.toMonths }));
    case "raise_priority": {
      const sorted = [...s.goals].sort((a, b) => a.priority - b.priority);
      const i = sorted.findIndex((g) => g.id === c.goalId);
      if (i <= 0) return s;
      [sorted[i - 1], sorted[i]] = [sorted[i]!, sorted[i - 1]!];
      return { ...s, goals: sorted.map((g, k) => ({ ...g, priority: k + 1 })) };
    }
    case "spend_less":
      return { ...s, spendingCut: s.spendingCut + c.monthly };
  }
}

/** Candidate single changes from a state, within limits relative to the original plan. */
function candidates(
  s: State,
  original: State,
  expenses: number,
  opts: { locked: Set<string> },
): ChangeView[] {
  const out: ChangeView[] = [];
  const orig = new Map(original.goals.map((g) => [g.id, g]));
  const sorted = [...s.goals].sort((a, b) => a.priority - b.priority);
  for (const g of s.goals) {
    if (opts.locked.has(g.id)) continue;
    const o = orig.get(g.id)!;
    const delayed = monthsDiff(o.targetMonth, g.targetMonth);
    for (const m of [6, 12, 24]) {
      if (delayed + m <= 36)
        out.push(view({ kind: "delay", goalId: g.id, months: m }, s.goals, DISRUPTION.delay(m)));
    }
    const trimmed = 100 - (g.targetAmount / o.targetAmount) * 100;
    for (const pct of [10, 20]) {
      if (trimmed + pct <= 30.5)
        out.push(view({ kind: "reduce", goalId: g.id, pct }, s.goals, DISRUPTION.reduce(pct)));
    }
    if (g.funding === "loan") {
      for (const d of [-10, 10]) {
        const to = g.downPaymentPct + d;
        if (to >= 10 && to <= 60 && Math.abs(to - o.downPaymentPct) <= 20)
          out.push(
            view(
              { kind: "down_payment", goalId: g.id, toPct: to },
              s.goals,
              DISRUPTION.down_payment,
            ),
          );
      }
      const maxTenure = g.kind === "house" ? 360 : 84;
      const to = Math.min(maxTenure, g.loanTenureMonths + (g.kind === "house" ? 60 : 12));
      if (to > g.loanTenureMonths && to - o.loanTenureMonths <= 120)
        out.push(view({ kind: "tenure", goalId: g.id, toMonths: to }, s.goals, DISRUPTION.tenure));
    }
    if (sorted[0]?.id !== g.id)
      out.push(view({ kind: "raise_priority", goalId: g.id }, s.goals, DISRUPTION.raise_priority));
  }
  for (const share of [0.05, 0.1]) {
    const monthly = Math.round((expenses * share) / 500) * 500;
    if (monthly > 0 && s.spendingCut + monthly <= expenses * 0.15 + 1)
      out.push(view({ kind: "spend_less", monthly }, s.goals, DISRUPTION.spend_less(share)));
  }
  return out;
}

function view(c: PlanChange, goals: PlanGoal[], disruption: number): ChangeView {
  return { ...c, text: describe(c, goals), disruption } as ChangeView;
}

function monthsDiff(from: string, to: string) {
  const [a, b] = from.split("-").map(Number);
  const [c, d] = to.split("-").map(Number);
  return (c! - a!) * 12 + (d! - b!);
}

export type SearchRound = {
  round: number;
  tried: number;
  /** The best few candidates this round, re-scored on the larger sample. */
  shortlist: { text: string; score: number; gain: number }[];
  accepted: ChangeView | null;
  scoreAfter: number;
};

export type Proposal = {
  changes: ChangeView[];
  goals: PlanGoal[];
  spendingCut: number;
  rounds: SearchRound[];
  /** Checked on fresh futures, never used during the search. */
  before: PlanOdds;
  after: PlanOdds;
  evaluations: number;
};

export type OptimizeOptions = {
  risk?: Partial<RiskModel>;
  /** Goals the search may not change. */
  locked?: string[];
  maxChanges?: number;
  screenPaths?: number;
  confirmPaths?: number;
  checkPaths?: number;
  seed?: number;
};

/** Run the whole search, reporting each round. */
export function optimizePlan(
  input: SimInput,
  opts: OptimizeOptions & { onRound?: (r: SearchRound) => void } = {},
): Proposal {
  const it = optimizeRounds(input, opts);
  for (;;) {
    const next = it.next();
    if (next.done) return next.value;
    opts.onRound?.(next.value);
  }
}

/** The same search, yielding to the event loop between rounds so progress can stream. */
export async function optimizePlanAsync(
  input: SimInput,
  opts: OptimizeOptions & { onRound?: (r: SearchRound) => void } = {},
): Promise<Proposal> {
  const it = optimizeRounds(input, opts);
  for (;;) {
    await new Promise((r) => setTimeout(r, 0));
    const next = it.next();
    if (next.done) return next.value;
    opts.onRound?.(next.value);
  }
}

export function* optimizeRounds(
  input: SimInput,
  opts: OptimizeOptions = {},
): Generator<SearchRound, Proposal, void> {
  const seed = opts.seed ?? 4242;
  const screen = opts.screenPaths ?? 120;
  const confirm = opts.confirmPaths ?? 400;
  const locked = new Set(opts.locked ?? []);
  const baseCut = input.assumptions?.monthlySpendingCut ?? 0;
  const original: State = { goals: input.goals.map((g) => ({ ...g })), spendingCut: baseCut };
  const expenses = input.household.monthlyExpenses;
  let evaluations = 0;
  const odds = (s: State, paths: number, sd = seed) => {
    evaluations++;
    return simulatePlan(
      {
        ...input,
        goals: s.goals,
        assumptions: { ...input.assumptions, monthlySpendingCut: s.spendingCut },
      },
      { risk: opts.risk, paths, seed: sd },
    );
  };

  let state = original;
  let current = odds(state, confirm).score;
  const changes: ChangeView[] = [];
  const rounds: SearchRound[] = [];
  for (let round = 1; round <= (opts.maxChanges ?? 3); round++) {
    const cands = candidates(state, original, expenses, { locked });
    const screened = cands
      .map((c) => ({ c, s: odds(apply(state, c), screen).score - c.disruption }))
      .sort((a, b) => b.s - a.s)
      .slice(0, 3)
      .map(({ c }) => {
        const score = odds(apply(state, c), confirm).score;
        return { c, score, net: score - c.disruption };
      })
      .sort((a, b) => b.net - a.net);
    const best = screened[0];
    const accept = best && best.net - current >= 0.01 ? best : null;
    const r: SearchRound = {
      round,
      tried: cands.length,
      shortlist: screened.map((x) => ({ text: x.c.text, score: x.score, gain: x.score - current })),
      accepted: accept?.c ?? null,
      scoreAfter: accept ? accept.score : current,
    };
    rounds.push(r);
    yield r;
    if (!accept) break;
    // Describe against the state it applies to, then move on.
    changes.push(accept.c);
    state = apply(state, accept.c);
    current = accept.score;
  }

  // Out-of-sample check on fresh futures.
  const check = opts.checkPaths ?? 1000;
  const fresh = seed + 1_000_003;
  return {
    changes,
    goals: state.goals,
    spendingCut: state.spendingCut,
    rounds,
    before: odds(original, check, fresh),
    after: odds(state, check, fresh),
    evaluations,
  };
}
