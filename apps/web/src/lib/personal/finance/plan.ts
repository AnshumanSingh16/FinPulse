/**
 * The goal plan: a deterministic, month-by-month projection of a household's money across all of
 * its goals at once.
 *
 * A single "can I afford this?" check treats each purchase in isolation. Real goals compete for
 * the same salary and the same savings, so this engine simulates them together:
 *
 *   each month
 *     income and living costs grow at the assumed rates (stepping once a year)
 *     balances earn the assumed return (goal funds more than three years from their date earn the
 *       growth return, everything else the safe return)
 *     loan EMIs taken for earlier goals are paid and amortised
 *     the surplus first tops up the emergency reserve, then funds goals in priority order — each
 *       goal takes the contribution that would reach its (inflated) cash need on its date — and
 *       anything left becomes free savings
 *     a deficit is covered from free savings, then goal funds (lowest priority first), then the
 *       reserve
 *     a goal whose date has arrived is bought once its fund (topped up from free savings) covers
 *       the cash it needs; a loan-funded goal then starts its EMI. Buying late costs more, because
 *       the price keeps inflating.
 *
 * Nothing here is a forecast: growth, inflation and return figures are assumptions the person can
 * see and change. Existing investments are left untouched (reported separately), and the value of
 * things bought is not counted as savings.
 */
import { requireFinite, requireNonNegative, roundRupees } from "./errors";
import { calculateEMI } from "./loan";

export const GOAL_KINDS = [
  "house",
  "car",
  "education",
  "wedding",
  "travel",
  "business",
  "custom",
] as const;
export type GoalKind = (typeof GOAL_KINDS)[number];

/** Default yearly price inflation per goal type. Assumptions shown to (and editable by) the user. */
export const GOAL_INFLATION_DEFAULTS: Record<GoalKind, number> = {
  house: 6,
  car: 5,
  education: 10,
  wedding: 7,
  travel: 6,
  business: 6,
  custom: 6,
};

/** Default one-time costs on top of the price (stamp duty, registration…) as % of the price. */
export const GOAL_UPFRONT_DEFAULTS: Record<GoalKind, number> = {
  house: 7,
  car: 0,
  education: 0,
  wedding: 0,
  travel: 0,
  business: 0,
  custom: 0,
};

export type PlanGoal = {
  id: string;
  kind: GoalKind;
  name: string;
  /** Price in today's rupees. */
  targetAmount: number;
  /** "YYYY-MM" — when the person wants it. */
  targetMonth: string;
  /** 1 = most important. Goals with a lower number are funded first. */
  priority: number;
  /** Yearly price inflation, %. */
  inflationPct: number;
  /** One-time costs on top of the price, % of the price (always paid in cash). */
  upfrontCostPct: number;
  funding: "cash" | "loan";
  /** For loan-funded goals: share of the price paid upfront, %. */
  downPaymentPct: number;
  loanRatePct: number;
  loanTenureMonths: number;
};

export type PlanAssumptions = {
  /** Yearly growth of take-home income, %. */
  incomeGrowthPct: number;
  /** Yearly growth of living costs and fixed obligations, %. */
  expenseInflationPct: number;
  /** Yearly return on the reserve, free savings and goal funds due within 3 years, %. */
  safeReturnPct: number;
  /** Yearly return on goal funds 3+ years from their date and on existing investments, %. */
  growthReturnPct: number;
  /** Months of essential spending kept as an emergency reserve. */
  emergencyMonths: number;
  /** Months left on existing EMIs; null = they continue throughout the projection. */
  existingEmiMonthsLeft: number | null;
};

export const DEFAULT_ASSUMPTIONS: PlanAssumptions = {
  incomeGrowthPct: 6,
  expenseInflationPct: 6,
  safeReturnPct: 6.5,
  growthReturnPct: 10,
  emergencyMonths: 6,
  existingEmiMonthsLeft: null,
};

export type PlanHousehold = {
  monthlyIncome: number;
  monthlyExpenses: number;
  existingEmis: number;
  otherMonthlyObligations: number;
  liquidSavings: number;
  investments: number;
};

export type GoalStatus = "on_track" | "delayed" | "not_reached";

export type GoalProjection = {
  id: string;
  name: string;
  kind: GoalKind;
  priority: number;
  funding: PlanGoal["funding"];
  targetMonth: string;
  /** Months from the start of the projection to the target date (0 if already due). */
  dueIndex: number;
  status: GoalStatus;
  achievedMonth: string | null;
  achievedIndex: number | null;
  /** Months later than wanted; 0 when on time, null when never reached in the horizon. */
  delayMonths: number | null;
  /** Price on the target date after inflation. */
  priceAtTarget: number;
  /** Cash needed on the target date: down payment (or full price) plus one-time costs. */
  cashNeededAtTarget: number;
  /** Price actually paid (later = more expensive). Null when never reached. */
  pricePaid: number | null;
  /** Savings set aside for this goal on day one. */
  startingAllocation: number;
  /** Monthly contribution this goal needs from today to land on time. */
  requiredMonthly: number;
  /** What it actually receives this month after higher priorities. */
  allocatedMonthly: number;
  /** Fund as a share of the cash needed, on the target date (capped at 100). */
  fundedPctAtTarget: number;
  loan: { principal: number; emi: number; ratePct: number; tenureMonths: number } | null;
};

export type PlanYear = {
  /** Index of the month this snapshot was taken at the end of. */
  monthIndex: number;
  month: string;
  income: number;
  spending: number;
  emis: number;
  surplus: number;
  reserve: number;
  freeSavings: number;
  goalFunds: number;
  investments: number;
  loanOutstanding: number;
  goalsBought: string[];
};

export type PlanProjection = {
  startMonth: string;
  horizonMonths: number;
  assumptions: PlanAssumptions;
  goals: GoalProjection[];
  years: PlanYear[];
  summary: {
    surplusNow: number;
    requiredMonthlyTotal: number;
    allocatedMonthlyTotal: number;
    /** Surplus left this month after the reserve top-up and goal contributions. */
    freeMonthlyNow: number;
    /** Share of this month's surplus the goals need, % (null when there's no surplus). */
    commitmentPct: number | null;
    reserveTarget: number;
    reserveNow: number;
    /** First month the reserve reaches its target, or null if not within the horizon. */
    reserveFullMonth: string | null;
    /** Months in which outgoings exceeded income. */
    deficitMonths: number;
    /** Months in which even every balance could not cover the deficit. */
    shortfallMonths: number;
    onTrack: number;
    delayed: number;
    notReached: number;
    status: "on_track" | "stretched" | "off_track" | "no_goals";
  };
};

// ---------------------------------------------------------------- months

const MONTH_RE = /^(\d{4})-(0[1-9]|1[0-2])$/;

export function isMonth(value: string): boolean {
  return MONTH_RE.test(value);
}

function monthNumber(value: string): number {
  const m = MONTH_RE.exec(value);
  if (!m) throw new RangeError(`Invalid month "${value}" (expected YYYY-MM)`);
  return Number(m[1]) * 12 + (Number(m[2]) - 1);
}

export function addMonths(month: string, n: number): string {
  const t = monthNumber(month) + n;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`;
}

export function monthsBetween(from: string, to: string): number {
  return monthNumber(to) - monthNumber(from);
}

export function currentMonth(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

// ---------------------------------------------------------------- helpers

const monthlyRate = (annualPct: number) => Math.pow(1 + annualPct / 100, 1 / 12) - 1;
const grow = (value: number, annualPct: number, months: number) =>
  value * Math.pow(1 + annualPct / 100, months / 12);

function validate(household: PlanHousehold, goals: PlanGoal[], a: PlanAssumptions) {
  for (const [k, v] of Object.entries(household)) requireNonNegative(k, v);
  for (const [k, v] of Object.entries(a)) if (v !== null) requireFinite(k, v as number);
  for (const g of goals) {
    requireNonNegative(`${g.name}: amount`, g.targetAmount);
    requireNonNegative(`${g.name}: inflation`, g.inflationPct);
    requireNonNegative(`${g.name}: one-time costs`, g.upfrontCostPct);
    if (!isMonth(g.targetMonth)) throw new RangeError(`${g.name}: invalid target month`);
  }
}

type Loan = { goalId: string; balance: number; emi: number; r: number };

// ---------------------------------------------------------------- projection

export function projectPlan(input: {
  household: PlanHousehold;
  goals: PlanGoal[];
  assumptions?: Partial<PlanAssumptions>;
  startMonth: string;
  /** Override the horizon (months). Defaults to the last goal + 5 years, between 5 and 30 years. */
  horizonMonths?: number;
}): PlanProjection {
  const a: PlanAssumptions = { ...DEFAULT_ASSUMPTIONS, ...input.assumptions };
  const h = input.household;
  validate(h, input.goals, a);
  const start = input.startMonth;
  const goals = [...input.goals].sort(
    (x, y) => x.priority - y.priority || monthsBetween(y.targetMonth, x.targetMonth),
  );
  const due = new Map(goals.map((g) => [g.id, Math.max(0, monthsBetween(start, g.targetMonth))]));
  const lastDue = Math.max(0, ...due.values());
  const horizon =
    input.horizonMonths ?? Math.min(360, Math.max(60, Math.ceil((lastDue + 60) / 12) * 12));

  const rSafe = monthlyRate(a.safeReturnPct);
  const rGrowth = monthlyRate(a.growthReturnPct);
  const fundRate = (g: PlanGoal, m: number) => (due.get(g.id)! - m > 36 ? rGrowth : rSafe);
  const price = (g: PlanGoal, m: number) => grow(g.targetAmount, g.inflationPct, m);
  const cashNeed = (g: PlanGoal, m: number) =>
    (price(g, m) * ((g.funding === "loan" ? g.downPaymentPct : 100) + g.upfrontCostPct)) / 100;
  // Compounding factors per goal: growth[j] is what ₹1 held at the end of month j is worth on the
  // goal's date; level[j] is what ₹1 contributed every month from j to the date is worth then.
  const factors = new Map<string, { growth: number[]; level: number[] }>();
  for (const g of goals) {
    const d = due.get(g.id)!;
    const growth = new Array<number>(d + 1);
    const level = new Array<number>(d + 1);
    growth[d] = 1;
    level[d] = 1;
    for (let j = d - 1; j >= 0; j--) {
      growth[j] = growth[j + 1]! * (1 + fundRate(g, j + 1));
      level[j] = level[j + 1]! + growth[j]!;
    }
    factors.set(g.id, { growth, level });
  }
  /** Contribution needed this month (month end) to reach the cash need on the goal's date. */
  const required = (g: PlanGoal, fund: number, m: number) => {
    const d = due.get(g.id)!;
    if (d <= m) return Math.max(0, cashNeed(g, m) - fund);
    const f = factors.get(g.id)!;
    return Math.max(0, (cashNeed(g, d) - fund * f.growth[m]!) / f.level[m]!);
  };

  const essentials0 = h.monthlyExpenses + h.otherMonthlyObligations + h.existingEmis;
  const reserveTarget0 = a.emergencyMonths * essentials0;
  let reserve = Math.min(h.liquidSavings, reserveTarget0);
  let free = h.liquidSavings - reserve;
  let investments = h.investments;

  // Day one: earmark spare savings for goals in priority order, up to each goal's present need.
  const fund = new Map<string, number>();
  const startAlloc = new Map<string, number>();
  for (const g of goals) {
    const d = due.get(g.id)!;
    const pv = cashNeed(g, d) / factors.get(g.id)!.growth[0]!;
    const take = Math.min(free, pv);
    fund.set(g.id, take);
    startAlloc.set(g.id, take);
    free -= take;
  }

  const achieved = new Map<string, { index: number; price: number }>();
  const fundedAtDue = new Map<string, number>();
  const loans: Loan[] = [];
  const firstAllocated = new Map<string, number>();
  const firstRequired = new Map<string, number>();
  const years: PlanYear[] = [];
  let surplusNow = 0;
  let freeMonthlyNow = 0;
  let reserveFullIndex: number | null = reserve >= reserveTarget0 - 0.5 ? 0 : null;
  let deficitMonths = 0;
  let shortfallMonths = 0;
  let yearBought: string[] = [];

  for (let m = 0; m < horizon; m++) {
    const yr = Math.floor(m / 12);
    const income = h.monthlyIncome * Math.pow(1 + a.incomeGrowthPct / 100, yr);
    const inflate = Math.pow(1 + a.expenseInflationPct / 100, yr);
    const spending = (h.monthlyExpenses + h.otherMonthlyObligations) * inflate;
    const oldEmi =
      a.existingEmiMonthsLeft === null || m < a.existingEmiMonthsLeft ? h.existingEmis : 0;

    // Returns on balances held through the month.
    if (m > 0) {
      reserve *= 1 + rSafe;
      if (free > 0) free *= 1 + rSafe;
      for (const g of goals)
        if (!achieved.has(g.id)) fund.set(g.id, fund.get(g.id)! * (1 + fundRate(g, m)));
      investments *= 1 + rGrowth;
    }

    // Loans taken for goals already bought.
    let newEmi = 0;
    for (const l of loans) {
      if (l.balance <= 0) continue;
      const interest = l.balance * l.r;
      const pay = Math.min(l.emi, l.balance + interest);
      l.balance = Math.max(0, l.balance + interest - pay);
      newEmi += pay;
    }

    const emis = oldEmi + newEmi;
    const surplus = income - spending - emis;
    const reserveTarget = a.emergencyMonths * (spending + emis);

    if (surplus >= 0) {
      let s = surplus;
      const top = Math.min(s, Math.max(0, reserveTarget - reserve));
      reserve += top;
      s -= top;
      for (const g of goals) {
        if (achieved.has(g.id)) continue;
        const need = required(g, fund.get(g.id)!, m);
        const c = Math.min(s, need);
        fund.set(g.id, fund.get(g.id)! + c);
        s -= c;
        if (m === 0) {
          firstAllocated.set(g.id, c);
          firstRequired.set(g.id, need);
        }
      }
      free += s;
      if (m === 0) freeMonthlyNow = s;
    } else {
      deficitMonths++;
      let gap = -surplus;
      const takeFree = Math.min(Math.max(0, free), gap);
      free -= takeFree;
      gap -= takeFree;
      for (const g of [...goals].reverse()) {
        if (gap <= 0) break;
        if (achieved.has(g.id)) continue;
        const t = Math.min(fund.get(g.id)!, gap);
        fund.set(g.id, fund.get(g.id)! - t);
        gap -= t;
      }
      const takeReserve = Math.min(reserve, gap);
      reserve -= takeReserve;
      gap -= takeReserve;
      if (gap > 0.5) {
        shortfallMonths++;
        free -= gap; // money that isn't there: tracked as a negative balance
      }
      if (m === 0) {
        for (const g of goals) {
          firstAllocated.set(g.id, 0);
          firstRequired.set(g.id, required(g, fund.get(g.id)!, 0));
        }
        freeMonthlyNow = surplus;
      }
    }
    if (m === 0) surplusNow = surplus;
    if (reserveFullIndex === null && reserve >= reserveTarget - 0.5) reserveFullIndex = m;

    // Buy goals whose date has come, in priority order.
    for (const g of goals) {
      if (achieved.has(g.id)) continue;
      const d = due.get(g.id)!;
      if (m < d) continue;
      if (m === d)
        fundedAtDue.set(g.id, Math.min(100, (fund.get(g.id)! / cashNeed(g, d)) * 100 || 0));
      const need = cashNeed(g, m);
      const have = fund.get(g.id)!;
      if (have + Math.max(0, free) + 0.5 < need) continue;
      const fromFree = Math.max(0, need - have);
      free -= fromFree;
      free += Math.max(0, have - need);
      fund.set(g.id, 0);
      const p = price(g, m);
      achieved.set(g.id, { index: m, price: p });
      yearBought.push(g.name);
      if (g.funding === "loan" && g.downPaymentPct < 100) {
        const principal = p * (1 - g.downPaymentPct / 100);
        loans.push({
          goalId: g.id,
          balance: principal,
          emi: calculateEMI(roundRupees(principal), g.loanRatePct, g.loanTenureMonths),
          r: g.loanRatePct / 12 / 100,
        });
      }
    }

    if (m % 12 === 11 || m === horizon - 1) {
      years.push({
        monthIndex: m,
        month: addMonths(start, m),
        income: roundRupees(income),
        spending: roundRupees(spending),
        emis: roundRupees(emis),
        surplus: roundRupees(surplus),
        reserve: roundRupees(reserve),
        freeSavings: roundRupees(free),
        goalFunds: roundRupees(
          goals.reduce((t, g) => t + (achieved.has(g.id) ? 0 : fund.get(g.id)!), 0),
        ),
        investments: roundRupees(investments),
        loanOutstanding: roundRupees(loans.reduce((t, l) => t + l.balance, 0)),
        goalsBought: yearBought,
      });
      yearBought = [];
    }
  }

  const projections: GoalProjection[] = goals.map((g) => {
    const d = due.get(g.id)!;
    const got = achieved.get(g.id);
    const loan = loans.find((l) => l.goalId === g.id);
    const delay = got ? got.index - d : null;
    return {
      id: g.id,
      name: g.name,
      kind: g.kind,
      priority: g.priority,
      funding: g.funding,
      targetMonth: g.targetMonth,
      dueIndex: d,
      status: !got ? "not_reached" : delay! > 0 ? "delayed" : "on_track",
      achievedMonth: got ? addMonths(start, got.index) : null,
      achievedIndex: got?.index ?? null,
      delayMonths: delay,
      priceAtTarget: roundRupees(price(g, d)),
      cashNeededAtTarget: roundRupees(cashNeed(g, d)),
      pricePaid: got ? roundRupees(got.price) : null,
      startingAllocation: roundRupees(startAlloc.get(g.id) ?? 0),
      requiredMonthly: roundRupees(firstRequired.get(g.id) ?? 0),
      allocatedMonthly: roundRupees(firstAllocated.get(g.id) ?? 0),
      fundedPctAtTarget: Math.round(fundedAtDue.get(g.id) ?? (got && got.index <= d ? 100 : 0)),
      loan:
        loan && got
          ? {
              principal: roundRupees(got.price * (1 - g.downPaymentPct / 100)),
              emi: loan.emi,
              ratePct: g.loanRatePct,
              tenureMonths: g.loanTenureMonths,
            }
          : null,
    };
  });

  const requiredMonthlyTotal = projections.reduce((t, g) => t + g.requiredMonthly, 0);
  const allocatedMonthlyTotal = projections.reduce((t, g) => t + g.allocatedMonthly, 0);
  const onTrack = projections.filter((g) => g.status === "on_track").length;
  const delayed = projections.filter((g) => g.status === "delayed").length;
  const notReached = projections.filter((g) => g.status === "not_reached").length;
  return {
    startMonth: start,
    horizonMonths: horizon,
    assumptions: a,
    goals: projections,
    years,
    summary: {
      surplusNow: roundRupees(surplusNow),
      requiredMonthlyTotal: roundRupees(requiredMonthlyTotal),
      allocatedMonthlyTotal: roundRupees(allocatedMonthlyTotal),
      freeMonthlyNow: roundRupees(freeMonthlyNow),
      commitmentPct:
        surplusNow > 0 ? Math.round((requiredMonthlyTotal / surplusNow) * 1000) / 10 : null,
      reserveTarget: roundRupees(reserveTarget0),
      reserveNow: roundRupees(Math.min(h.liquidSavings, reserveTarget0)),
      reserveFullMonth: reserveFullIndex === null ? null : addMonths(start, reserveFullIndex),
      deficitMonths,
      shortfallMonths,
      onTrack,
      delayed,
      notReached,
      status:
        goals.length === 0
          ? "no_goals"
          : notReached > 0 || shortfallMonths > 0
            ? "off_track"
            : delayed > 0
              ? "stretched"
              : "on_track",
    },
  };
}

// ---------------------------------------------------------------- impact of a new goal

export type GoalImpact = {
  id: string;
  name: string;
  before: { status: GoalStatus; achievedMonth: string | null };
  after: { status: GoalStatus; achievedMonth: string | null };
  /** Extra months of delay caused by the new goal (null if it now never happens). */
  extraDelayMonths: number | null;
};

export type PlanImpact = {
  verdict: "fits" | "delays_others" | "new_goal_late" | "breaks_plan";
  newGoal: GoalProjection;
  affected: GoalImpact[];
  freeMonthlyBefore: number;
  freeMonthlyAfter: number;
  statusBefore: PlanProjection["summary"]["status"];
  statusAfter: PlanProjection["summary"]["status"];
};

/** Goals whose timing or status differs between two projections of the same plan. */
export function goalChanges(before: PlanProjection, after: PlanProjection): GoalImpact[] {
  const out: GoalImpact[] = [];
  for (const b of before.goals) {
    const x = after.goals.find((g) => g.id === b.id);
    if (!x || (b.achievedIndex === x.achievedIndex && b.status === x.status)) continue;
    out.push({
      id: b.id,
      name: b.name,
      before: { status: b.status, achievedMonth: b.achievedMonth },
      after: { status: x.status, achievedMonth: x.achievedMonth },
      extraDelayMonths:
        x.achievedIndex === null ? null : x.achievedIndex - (b.achievedIndex ?? x.achievedIndex),
    });
  }
  return out;
}

/** Compare the plan with and without one extra goal: what does adding it do to everything else? */
export function planImpact(
  before: PlanProjection,
  after: PlanProjection,
  newGoalId: string,
): PlanImpact {
  const newGoal = after.goals.find((g) => g.id === newGoalId);
  if (!newGoal) throw new RangeError("The new goal is not in the projection");
  const affected = goalChanges(before, after);
  const broken = affected.some(
    (g) => g.after.status === "not_reached" && g.before.status !== "not_reached",
  );
  return {
    verdict: broken
      ? "breaks_plan"
      : affected.some((g) => (g.extraDelayMonths ?? 0) > 0)
        ? "delays_others"
        : newGoal.status !== "on_track"
          ? "new_goal_late"
          : "fits",
    newGoal,
    affected,
    freeMonthlyBefore: before.summary.freeMonthlyNow,
    freeMonthlyAfter: after.summary.freeMonthlyNow,
    statusBefore: before.summary.status,
    statusAfter: after.summary.status,
  };
}
