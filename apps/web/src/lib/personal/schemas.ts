/**
 * Shared, validated shapes for the personal-finance product: the financial profile ("Financial
 * Brain") and a purchase request. Zod validates everything that crosses the API boundary.
 */
import { z } from "zod";

const money = z.number().finite().min(0).max(1e11);
const nullableMoney = money.nullable();

export const PROFILE_FIELDS = [
  "name",
  "monthlyIncome",
  "incomeVariability",
  "monthlyExpenses",
  "liquidSavings",
  "investments",
  "existingEmis",
  "otherMonthlyObligations",
  "dependents",
  "upcomingExpenses",
  "emergencyBufferMonths",
  "goals",
] as const;
export type ProfileField = (typeof PROFILE_FIELDS)[number];

export const ProfileValuesSchema = z.object({
  name: z.string().trim().max(40).nullable(),
  monthlyIncome: nullableMoney,
  incomeVariability: z.enum(["stable", "variable"]).nullable(),
  monthlyExpenses: nullableMoney,
  liquidSavings: nullableMoney,
  investments: nullableMoney,
  existingEmis: nullableMoney,
  otherMonthlyObligations: nullableMoney,
  dependents: z.number().int().min(0).max(20).nullable(),
  upcomingExpenses: nullableMoney,
  emergencyBufferMonths: z.number().min(0).max(36).nullable(),
  goals: z.string().max(500).nullable(),
});
export type ProfileValues = z.infer<typeof ProfileValuesSchema>;

export const PROFILE_LABELS: Record<ProfileField, string> = {
  name: "What should we call you?",
  monthlyIncome: "Monthly take-home income",
  incomeVariability: "Income variability",
  monthlyExpenses: "Monthly living expenses",
  liquidSavings: "Liquid savings",
  investments: "Investments & other assets",
  existingEmis: "Existing EMIs (monthly)",
  otherMonthlyObligations: "Insurance & other fixed obligations (monthly)",
  dependents: "Dependents",
  upcomingExpenses: "Major expenses in the next 12 months",
  emergencyBufferMonths: "Preferred emergency buffer (months)",
  goals: "Financial goals",
};

export const EMPTY_PROFILE: ProfileValues = {
  name: null,
  monthlyIncome: null,
  incomeVariability: null,
  monthlyExpenses: null,
  liquidSavings: null,
  investments: null,
  existingEmis: null,
  otherMonthlyObligations: null,
  dependents: null,
  upcomingExpenses: null,
  emergencyBufferMonths: null,
  goals: null,
};

export type FieldSourceKind = "user" | "demo" | "document" | "derived";
export type FieldSource = { kind: FieldSourceKind; at: string; note?: string; documentId?: string };

export type FinancialProfile = {
  values: ProfileValues;
  sources: Partial<Record<ProfileField, FieldSource>>;
  isDemo: boolean;
  updatedAt: string | null;
};

export const PURCHASE_TYPES = ["house", "car", "education", "business", "custom"] as const;
export type PurchaseType = (typeof PURCHASE_TYPES)[number];

export const PurchaseRequestSchema = z.object({
  type: z.enum(PURCHASE_TYPES),
  label: z.string().trim().min(1).max(80),
  price: money.min(1000, "Purchase price must be at least ₹1,000"),
  downPaymentPct: z.number().min(0).max(100).nullable(),
  /** Upfront cash costs (stamp duty, registration, fees). Null = not provided. */
  upfrontCosts: nullableMoney,
  financeUpfrontCosts: z.boolean().default(false),
  interestRate: z.number().min(0).max(50).nullable(),
  tenureMonths: z.number().int().min(1).max(600).nullable(),
  monthlyOwnershipCost: nullableMoney,
  /** Ask the Research Agent for financing options even when a rate is given. */
  researchFinancing: z.boolean().default(true),
});
export type PurchaseRequest = z.infer<typeof PurchaseRequestSchema>;

export const AnalyzeBodySchema = z.object({
  goal: z.string().trim().max(500).optional(),
  purchase: PurchaseRequestSchema,
  /** Profile overrides typed into the purchase form; saved to the profile as user-supplied. */
  profile: ProfileValuesSchema.partial().optional(),
});

/** Fictional demo profile. Not a real person; figures are illustrative. */
export const DEMO_PROFILE: ProfileValues = {
  name: "Riya",
  monthlyIncome: 200_000,
  incomeVariability: "stable",
  monthlyExpenses: 70_000,
  liquidSavings: 2_500_000,
  investments: 800_000,
  existingEmis: 15_000,
  otherMonthlyObligations: 0,
  dependents: 1,
  upcomingExpenses: null,
  emergencyBufferMonths: 6,
  goals: "Buy a first home in Pune within the next year.",
};

export const DEMO_PURCHASE: PurchaseRequest = {
  type: "house",
  label: "₹75 lakh house",
  price: 7_500_000,
  downPaymentPct: 20,
  upfrontCosts: null,
  financeUpfrontCosts: false,
  interestRate: 8.5,
  tenureMonths: 240,
  monthlyOwnershipCost: null,
  researchFinancing: true,
};

// ---------------------------------------------------------------- goal plan

const month = z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/, "Use YYYY-MM");

export const GoalKindSchema = z.enum([
  "house",
  "car",
  "education",
  "wedding",
  "travel",
  "business",
  "custom",
]);

export const PlanGoalSchema = z.object({
  id: z.string().regex(/^goal_[a-z0-9]{6,20}$/),
  kind: GoalKindSchema,
  name: z.string().trim().min(1).max(60),
  targetAmount: money.min(1000, "Amount must be at least ₹1,000"),
  targetMonth: month,
  priority: z.number().int().min(1).max(20),
  inflationPct: z.number().min(0).max(25),
  upfrontCostPct: z.number().min(0).max(30),
  funding: z.enum(["cash", "loan"]),
  downPaymentPct: z.number().min(0).max(100),
  loanRatePct: z.number().min(0).max(30),
  loanTenureMonths: z.number().int().min(6).max(360),
  /** The analysis this goal was created from, if any. */
  fromRunId: z.string().max(40).optional(),
});
export type PlanGoalValues = z.infer<typeof PlanGoalSchema>;

export const PlanAssumptionsSchema = z.object({
  incomeGrowthPct: z.number().min(-10).max(30),
  expenseInflationPct: z.number().min(0).max(25),
  safeReturnPct: z.number().min(0).max(15),
  growthReturnPct: z.number().min(0).max(20),
  emergencyMonths: z.number().min(0).max(36),
  existingEmiMonthsLeft: z.number().int().min(0).max(360).nullable(),
});

export const PlanBodySchema = z.object({
  goals: z.array(PlanGoalSchema).max(12),
  assumptions: PlanAssumptionsSchema.partial(),
});

export const CheckInSchema = z.object({
  month,
  /** Take-home income actually received that month. */
  income: money,
  /** Everything spent that month, including EMIs and fixed obligations. */
  spending: money,
  note: z.string().trim().max(200).optional(),
});
export type CheckInValues = z.infer<typeof CheckInSchema>;
