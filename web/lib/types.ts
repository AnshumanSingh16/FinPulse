export type Tone = "good" | "caution" | "bad" | "neutral" | "info";

export interface Evidence {
  title: string;
  method: string;
  assumptions: string[];
  limitations: string[];
  record_ids: string[];
  record_count: number;
}

export interface BusinessType {
  key: string;
  label: string;
  customers: string;
  suppliers: string;
}

export interface DemoBusiness {
  key: string;
  name: string;
  type: string;
  city: string;
  story: string;
}

export interface AppState {
  business: string;
  source: string;
  is_demo: boolean;
  as_of: string;
  as_of_label: string;
  upload: { name: string; bank_rows: number; invoice_rows: number; balance_rows: number; ready: boolean };
  ai: AiStatus;
  business_type: string;
  type_info: BusinessType | null;
  types: BusinessType[];
  demos: DemoBusiness[];
}

export interface Action {
  type: "remind" | "review" | "todo" | "add_balance" | "open";
  label: string;
  customer?: string;
  ids?: string[];
  text?: string;
  href?: string;
}

export interface AttentionItem {
  id: string;
  tone: Tone;
  icon: string;
  title: string;
  body: string;
  action: Action;
}

export interface MonthNumbers {
  label: string;
  sales: number;
  costs: number;
  profit: number;
  margin_pct: number | null;
  evidence: Evidence;
}

export interface Home {
  business: string;
  is_demo: boolean;
  as_of: string;
  as_of_label: string;
  status: { tone: Tone; headline: string; detail: string };
  cash: {
    known: boolean;
    message?: string;
    amount?: number;
    label?: string;
    exact?: string;
    months_of_costs?: number | null;
    cushion?: number;
    cushion_label?: string;
    reconciled?: boolean;
    history?: { date: string; balance: number }[];
    outlook?: { date: string; balance: number }[];
    in_90_days?: number | null;
    evidence?: Evidence;
  };
  month: (MonthNumbers & { previous: MonthNumbers | null; change?: { sales: number | null; costs: number | null; profit: number | null } }) | null;
  insight: { tone: Tone; text: string; ask: string } | null;
  attention: AttentionItem[];
  spending: { category: string; amount: number; previous: number; change_pct: number | null }[];
  trend: { month: string; sales: number; costs: number; profit: number }[];
  upcoming: { date: string; day: string; name: string; what: string; amount: number }[];
  upcoming_total: number | null;
}

export interface Txn {
  id: string;
  date: string;
  day: string;
  description: string;
  party: string;
  category: string;
  direction: "in" | "out";
  amount: number;
  mode: string | null;
}

export interface OwedGroup {
  name: string;
  total: number;
  overdue: number;
  items: { id: string; what: string; amount: number; due: string; due_label: string; state: "overdue" | "due_soon" | "upcoming"; days_late: number; days_left: number }[];
}

export interface Todo {
  id: number;
  text: string;
  reason: string;
  status: "open" | "done" | "dismissed";
  created_at: string;
}

export interface Rec {
  id: string;
  type: "transaction" | "invoice" | "bill";
  date: string;
  title: string;
  party: string;
  category: string;
  amount: number;
  direction: "in" | "out";
  status?: string;
}

export interface AiStatus {
  enabled: boolean;
  has_key: boolean;
  paused: boolean;
  key_hint: string | null;
  source: "app" | "environment" | null;
  provider: "gemini" | "anthropic";
  provider_label: string;
  model: string;
}
