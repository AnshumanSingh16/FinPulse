/**
 * The probabilistic plan model. A single projection answers "what happens if everything goes as
 * assumed?" — which it never does. This module runs the same month-by-month engine (plan.ts)
 * along thousands of possible futures and reports how often each goal lands:
 *
 *   markets      yearly returns drawn around the assumed return (long-term money volatile, near-
 *                term money nearly stable); volatility lowers typical growth, as it does in life
 *   inflation    yearly living-cost inflation drawn around the assumption; each goal's price
 *                follows general inflation plus its own noise
 *   income       yearly raises drawn around the assumed growth; variable earners also see
 *                month-to-month swings
 *   job loss     each year, a chance of losing income for a few months
 *   emergencies  each year, a chance of a one-off cost (medical, family, repairs) sized in months
 *                of spending
 *
 * Every parameter is an assumption shown to the person, not a forecast. Paths are generated from
 * a seeded generator and random streams are keyed so that comparing two versions of a plan uses
 * the same futures ("common random numbers"): differences come from the plan, not from luck.
 */
import {
  preparePlan,
  runPlan,
  type PlanPath,
  type PlanProjection,
  type PreparedPlan,
} from "./plan";

export type RiskModel = {
  /** Yearly volatility (standard deviation) of long-term returns, percentage points. */
  growthVolatilityPct: number;
  /** Yearly volatility of near-term returns. */
  safeVolatilityPct: number;
  /** Yearly volatility of living-cost inflation. */
  inflationVolatilityPct: number;
  /** Extra yearly volatility of each goal's price inflation. */
  goalPriceVolatilityPct: number;
  /** Yearly volatility of take-home income growth. */
  incomeGrowthVolatilityPct: number;
  /** Month-to-month swing of take-home income (variable earners). */
  incomeMonthlyVolatilityPct: number;
  /** Chance per year of losing income for a while, %. */
  jobLossYearlyPct: number;
  /** Months without income when it happens (uniform between the two). */
  jobLossMonthsMin: number;
  jobLossMonthsMax: number;
  /** Chance per year of an emergency cost, %. */
  emergencyYearlyPct: number;
  /** Typical emergency size in months of living costs (the median; sizes vary around it). */
  emergencyMedianMonths: number;
};

/** Round, conservative defaults for a salaried household. Assumptions, not forecasts. */
export const DEFAULT_RISK: RiskModel = {
  growthVolatilityPct: 15,
  safeVolatilityPct: 1,
  inflationVolatilityPct: 1.5,
  goalPriceVolatilityPct: 2,
  incomeGrowthVolatilityPct: 4,
  incomeMonthlyVolatilityPct: 0,
  jobLossYearlyPct: 3,
  jobLossMonthsMin: 3,
  jobLossMonthsMax: 9,
  emergencyYearlyPct: 10,
  emergencyMedianMonths: 1.5,
};

/** Variable earners: monthly income swings and a higher chance of a gap in work. */
export const VARIABLE_INCOME_RISK: Partial<RiskModel> = {
  incomeMonthlyVolatilityPct: 20,
  jobLossYearlyPct: 7,
};

export const NO_RISK: RiskModel = {
  ...DEFAULT_RISK,
  growthVolatilityPct: 0,
  safeVolatilityPct: 0,
  inflationVolatilityPct: 0,
  goalPriceVolatilityPct: 0,
  incomeGrowthVolatilityPct: 0,
  incomeMonthlyVolatilityPct: 0,
  jobLossYearlyPct: 0,
  emergencyYearlyPct: 0,
};

// ---------------------------------------------------------------- random numbers

/** mulberry32: small, fast, seedable. */
function rng(seed: number) {
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function normal(u: () => number): number {
  // Box–Muller; 1 − u avoids log(0).
  return Math.sqrt(-2 * Math.log(1 - u())) * Math.cos(2 * Math.PI * u());
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return h >>> 0;
}

// ---------------------------------------------------------------- paths

/**
 * Draw one future. The macro stream (markets, inflation, income, job loss, emergencies) depends
 * only on the seed — the same for every version of a plan. Each goal's price has its own stream
 * keyed by the goal's id, so adding, removing or reordering goals doesn't reshuffle the others.
 */
export function drawPath(prep: PreparedPlan, risk: RiskModel, seed: number): PlanPath {
  const n = prep.horizon;
  const a = prep.a;
  const years = Math.ceil(n / 12);
  const macro = rng(seed);
  const income = new Float64Array(n);
  const spending = new Float64Array(n);
  const safe = new Float64Array(n);
  const growth = new Float64Array(n);
  const shock = new Float64Array(n);
  const inflationByYear = new Float64Array(years);
  const baseSpend = prep.h.monthlyExpenses + prep.h.otherMonthlyObligations;

  const out = new Uint8Array(n);
  let incomeLevel = 1;
  let spendLevel = 1;
  for (let y = 0; y < years; y++) {
    // A fixed number of draws per year keeps streams aligned whatever the horizon.
    const zg = normal(macro);
    const zs = normal(macro);
    const zi = normal(macro);
    const zinc = normal(macro);
    const uJob = macro();
    const uJobAt = macro();
    const uJobLen = macro();
    const uEm = macro();
    const uEmAt = macro();
    const zEm = normal(macro);
    const zMonthly = Array.from({ length: 12 }, () => normal(macro));

    const g = Math.max(-0.6, (a.growthReturnPct + risk.growthVolatilityPct * zg) / 100);
    const sr = Math.max(0, (a.safeReturnPct + risk.safeVolatilityPct * zs) / 100);
    const infl = Math.max(-0.02, (a.expenseInflationPct + risk.inflationVolatilityPct * zi) / 100);
    inflationByYear[y] = infl;
    if (y > 0) {
      incomeLevel *= 1 + (a.incomeGrowthPct + risk.incomeGrowthVolatilityPct * zinc) / 100;
      spendLevel *= 1 + inflationByYear[y - 1]!;
    }
    const gm = Math.pow(1 + g, 1 / 12) - 1;
    const sm = Math.pow(1 + sr, 1 / 12) - 1;
    for (let k = 0; k < 12; k++) {
      const m = y * 12 + k;
      if (m >= n) break;
      const swing = 1 + (risk.incomeMonthlyVolatilityPct / 100) * zMonthly[k]!;
      income[m] = incomeLevel * Math.min(1.7, Math.max(0.3, swing));
      spending[m] = spendLevel;
      safe[m] = sm;
      growth[m] = gm;
    }
    if (uJob < risk.jobLossYearlyPct / 100) {
      const from = y * 12 + Math.floor(uJobAt * 12);
      const len =
        risk.jobLossMonthsMin +
        Math.floor(uJobLen * (risk.jobLossMonthsMax - risk.jobLossMonthsMin + 1));
      for (let m = from; m < Math.min(n, from + len); m++) out[m] = 1;
    }
    if (uEm < risk.emergencyYearlyPct / 100) {
      const m = y * 12 + Math.floor(uEmAt * 12);
      if (m < n)
        shock[m] =
          shock[m]! + baseSpend * spendLevel * risk.emergencyMedianMonths * Math.exp(0.75 * zEm);
    }
  }
  // Months out of work (a gap can run on into the next year).
  for (let m = 0; m < n; m++) if (out[m]) income[m] = 0;

  const price = prep.goals.map((goal) => {
    const s = rng(seed ^ hash(goal.id));
    const arr = new Float64Array(n);
    let level = 1;
    for (let y = 0; y < years; y++) {
      const r = Math.max(
        -0.05,
        (goal.inflationPct +
          (inflationByYear[y]! * 100 - a.expenseInflationPct) +
          risk.goalPriceVolatilityPct * normal(s)) /
          100,
      );
      for (let k = 0; k < 12; k++) {
        const m = y * 12 + k;
        if (m >= n) break;
        arr[m] = level * Math.pow(1 + r, k / 12);
      }
      level *= 1 + r;
    }
    return arr;
  });

  return { income, spending, safe, growth, shock, price };
}

// ---------------------------------------------------------------- simulation

export type GoalOdds = {
  id: string;
  name: string;
  priority: number;
  dueIndex: number;
  /** Share of futures in which the goal is reached by its target month (0–1). */
  onTime: number;
  /** …within a year of it. */
  withinYear: number;
  /** …at all within the projection. */
  reached: number;
  /** Months late in the median future (null if it's not reached in most). */
  medianDelay: number | null;
  /** Months late in a bad (90th percentile) future, null if not reached then. */
  badDelay: number | null;
};

export type PlanOdds = {
  paths: number;
  seed: number;
  risk: RiskModel;
  /** Share of futures in which every goal lands on time. */
  allOnTime: number;
  /** Share of futures in which money never runs out (no month the balances can't cover). */
  neverShort: number;
  goals: GoalOdds[];
  /** Savings set aside at the end of each year: 10th, 50th and 90th percentile across futures. */
  fan: { month: string; p10: number; p50: number; p90: number }[];
  /** Priority-weighted score in 0–1 used to compare plans (see planScore). */
  score: number;
};

export type SimInput = Parameters<typeof preparePlan>[0];

function quantile(sorted: number[], q: number): number {
  if (!sorted.length) return 0;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))));
  return sorted[i]!;
}

/**
 * Priority-weighted chance of goals landing on time (goal #1 counts most), with a heavy penalty
 * when money runs out in more than 10% of futures. Used to compare versions of a plan.
 */
export function planScore(o: Pick<PlanOdds, "goals" | "neverShort">): number {
  if (!o.goals.length) return o.neverShort;
  const n = o.goals.length;
  let w = 0;
  let total = 0;
  [...o.goals]
    .sort((x, y) => x.priority - y.priority)
    .forEach((g, i) => {
      const weight = n - i;
      w += weight;
      total += weight * (0.8 * g.onTime + 0.2 * g.withinYear);
    });
  const penalty = Math.max(0, 0.9 - o.neverShort) * 2;
  return Math.max(0, total / w - penalty);
}

export function simulatePlan(
  input: SimInput,
  opts: { risk?: Partial<RiskModel>; paths?: number; seed?: number } = {},
): PlanOdds {
  const risk = { ...DEFAULT_RISK, ...opts.risk };
  const paths = opts.paths ?? 1000;
  const seed = opts.seed ?? 20_261_013;
  const prep = preparePlan(input);
  const goals = prep.goals;
  const onTime = new Array<number>(goals.length).fill(0);
  const within = new Array<number>(goals.length).fill(0);
  const reached = new Array<number>(goals.length).fill(0);
  const delays: number[][] = goals.map(() => []);
  let all = 0;
  let never = 0;
  const fanValues: number[][] = [];
  let fanMonths: string[] = [];
  for (let k = 0; k < paths; k++) {
    const proj: PlanProjection = runPlan(prep, drawPath(prep, risk, seed + k * 7919));
    let allK = true;
    proj.goals.forEach((g, i) => {
      if (g.achievedIndex !== null) {
        reached[i]!++;
        delays[i]!.push(g.delayMonths!);
        if (g.delayMonths! <= 0) onTime[i]!++;
        else allK = false;
        if (g.delayMonths! <= 12) within[i]!++;
      } else {
        allK = false;
        delays[i]!.push(Number.POSITIVE_INFINITY);
      }
    });
    if (allK) all++;
    if (proj.summary.shortfallMonths === 0) never++;
    if (!fanMonths.length) fanMonths = proj.years.map((y) => y.month);
    proj.years.forEach((y, j) => {
      (fanValues[j] ??= []).push(y.reserve + y.freeSavings + y.goalFunds);
    });
  }
  const odds: Omit<PlanOdds, "score"> = {
    paths,
    seed,
    risk,
    allOnTime: goals.length ? all / paths : 1,
    neverShort: never / paths,
    goals: goals.map((g, i) => {
      const d = delays[i]!.sort((x, y) => x - y);
      const med = quantile(d, 0.5);
      const bad = quantile(d, 0.9);
      return {
        id: g.id,
        name: g.name,
        priority: g.priority,
        dueIndex: prep.due.get(g.id)!,
        onTime: onTime[i]! / paths,
        withinYear: within[i]! / paths,
        reached: reached[i]! / paths,
        medianDelay: Number.isFinite(med) ? Math.max(0, med) : null,
        badDelay: Number.isFinite(bad) ? Math.max(0, bad) : null,
      };
    }),
    fan: fanMonths.map((month, j) => {
      const v = fanValues[j]!.sort((x, y) => x - y);
      return {
        month,
        p10: Math.round(quantile(v, 0.1)),
        p50: Math.round(quantile(v, 0.5)),
        p90: Math.round(quantile(v, 0.9)),
      };
    }),
  };
  return { ...odds, score: planScore(odds) };
}

// ---------------------------------------------------------------- what hurts most

export const RISK_FACTORS = [
  {
    id: "markets",
    label: "Market swings",
    off: { growthVolatilityPct: 0, safeVolatilityPct: 0 },
  },
  {
    id: "inflation",
    label: "Inflation surprises",
    off: { inflationVolatilityPct: 0, goalPriceVolatilityPct: 0 },
  },
  {
    id: "income",
    label: "Uneven raises and pay",
    off: { incomeGrowthVolatilityPct: 0, incomeMonthlyVolatilityPct: 0 },
  },
  { id: "job_loss", label: "Losing income for a while", off: { jobLossYearlyPct: 0 } },
  { id: "emergencies", label: "Emergency costs", off: { emergencyYearlyPct: 0 } },
] as const satisfies readonly { id: string; label: string; off: Partial<RiskModel> }[];

export type RiskDriver = {
  id: (typeof RISK_FACTORS)[number]["id"];
  label: string;
  /** How much higher the chance of every goal landing on time would be without this risk. */
  allOnTimeCost: number;
  /** …and the plan score. */
  scoreCost: number;
};

/** Re-run with each risk switched off (same futures otherwise): which one costs the plan most? */
export function riskDrivers(
  input: SimInput,
  opts: { risk?: Partial<RiskModel>; paths?: number; seed?: number } = {},
): RiskDriver[] {
  const base = simulatePlan(input, opts);
  return RISK_FACTORS.map((f) => {
    const without = simulatePlan(input, { ...opts, risk: { ...opts.risk, ...f.off } });
    return {
      id: f.id,
      label: f.label,
      allOnTimeCost: Math.max(0, without.allOnTime - base.allOnTime),
      scoreCost: Math.max(0, without.score - base.score),
    };
  }).sort((x, y) => y.scoreCost - x.scoreCost || y.allOnTimeCost - x.allOnTimeCost);
}

// ---------------------------------------------------------------- safe to spend

export type SpendRoom = {
  /** The confidence the answer keeps: every goal on time in at least this share of futures. */
  target: number;
  current: number;
  /**
   * "spare": you could spend up to `monthly` more each month and still meet the target.
   * "cut": you'd need to spend `monthly` less each month to reach it.
   * "out_of_reach": cutting spending alone (up to 60%) doesn't get there.
   */
  kind: "spare" | "cut" | "out_of_reach";
  monthly: number;
};

/** How much monthly spending room the plan has at a given confidence (bisection, same futures). */
export function spendRoom(
  input: SimInput,
  opts: { target?: number; risk?: Partial<RiskModel>; paths?: number; seed?: number } = {},
): SpendRoom {
  const target = opts.target ?? 0.8;
  const sim = { risk: opts.risk, paths: opts.paths ?? 300, seed: opts.seed };
  const at = (extra: number) =>
    simulatePlan(
      {
        ...input,
        household: {
          ...input.household,
          monthlyExpenses: Math.max(0, input.household.monthlyExpenses + extra),
        },
      },
      sim,
    ).allOnTime;
  const current = at(0);
  const h = input.household;
  const round = (x: number) => Math.floor(x / 500) * 500;
  if (current >= target) {
    let lo = 0;
    let hi = Math.max(
      0,
      h.monthlyIncome - h.monthlyExpenses - h.existingEmis - h.otherMonthlyObligations,
    );
    if (at(hi) >= target) return { target, current, kind: "spare", monthly: round(hi) };
    for (let i = 0; i < 10; i++) {
      const mid = (lo + hi) / 2;
      if (at(mid) >= target) lo = mid;
      else hi = mid;
    }
    return { target, current, kind: "spare", monthly: round(lo) };
  }
  const maxCut = h.monthlyExpenses * 0.6;
  if (at(-maxCut) < target) return { target, current, kind: "out_of_reach", monthly: 0 };
  let lo = 0;
  let hi = maxCut;
  for (let i = 0; i < 10; i++) {
    const mid = (lo + hi) / 2;
    if (at(-mid) >= target) hi = mid;
    else lo = mid;
  }
  return { target, current, kind: "cut", monthly: Math.ceil(hi / 500) * 500 };
}
