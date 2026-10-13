/**
 * Simulating a plan takes a fraction of a second; pages ask for it often. Results are cached by
 * the plan's fingerprint (planKey), so an unchanged plan is never simulated twice.
 */
import "server-only";

import {
  riskDrivers,
  simulatePlan,
  spendRoom,
  VARIABLE_INCOME_RISK,
  type PlanOdds,
  type RiskDriver,
  type SpendRoom,
} from "./finance/montecarlo";
import { effectiveAssumptions, householdFromProfile, planKey } from "./plan-model";
import type { PlanGoalValues, ProfileValues } from "./schemas";
import type { PlanAssumptions } from "./finance/plan";

type Entry = { odds?: PlanOdds; drivers?: RiskDriver[]; room?: SpendRoom };
const MAX = 64;
const g = globalThis as unknown as { __finpulseOdds?: Map<string, Entry> };
const cache = (g.__finpulseOdds ??= new Map());

function entry(key: string): Entry {
  let e = cache.get(key);
  if (e) {
    cache.delete(key);
    cache.set(key, e); // most recently used last
    return e;
  }
  e = {};
  cache.set(key, e);
  if (cache.size > MAX) cache.delete(cache.keys().next().value!);
  return e;
}

type PlanArgs = {
  profile: ProfileValues;
  goals: PlanGoalValues[];
  assumptions: Partial<PlanAssumptions>;
  startMonth: string;
};

/** Variable earners get the variable-income risk profile. */
export function riskFor(profile: ProfileValues) {
  return profile.incomeVariability === "variable" ? VARIABLE_INCOME_RISK : {};
}

function simInput(a: PlanArgs) {
  const h = householdFromProfile(a.profile);
  if (!h.household || !a.goals.length) return null;
  return {
    household: h.household,
    goals: a.goals,
    assumptions: effectiveAssumptions(a.profile, a.assumptions),
    startMonth: a.startMonth,
  };
}

export function cachedOdds(a: PlanArgs, paths = 1000): PlanOdds | null {
  const input = simInput(a);
  if (!input) return null;
  const e = entry(`${paths}|${planKey(a)}`);
  return (e.odds ??= simulatePlan(input, { paths, risk: riskFor(a.profile) }));
}

export function cachedInsights(a: PlanArgs): { drivers: RiskDriver[]; room: SpendRoom } | null {
  const input = simInput(a);
  if (!input) return null;
  const e = entry(`insights|${planKey(a)}`);
  const risk = riskFor(a.profile);
  e.drivers ??= riskDrivers(input, { paths: 300, risk });
  e.room ??= spendRoom(input, { paths: 300, risk });
  return { drivers: e.drivers, room: e.room };
}
