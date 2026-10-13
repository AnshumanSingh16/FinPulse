"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { cn } from "@/lib/utils";

const EXAMPLES = [
  "I want to buy a ₹75 lakh house",
  "A ₹20 lakh car with 30% down",
  "An MBA costing ₹30 lakh",
];

/**
 * The natural-language goal box. Submitting opens the guided affordability flow with the goal
 * text, which is read by the same rule-based interpreter the Planner agent uses.
 */
export function GoalInput({
  initial = "",
  onSubmit,
  autoFocus,
  examples = EXAMPLES,
}: {
  initial?: string;
  onSubmit?: (goal: string) => void;
  autoFocus?: boolean;
  /** Example goals shown as one-tap chips; pass [] to hide them. */
  examples?: string[];
}) {
  const router = useRouter();
  const [text, setText] = useState(initial);
  const id = useId();
  const submit = (goal: string) => {
    const g = goal.trim();
    if (!g) return;
    if (onSubmit) onSubmit(g);
    else router.push(`/afford?goal=${encodeURIComponent(g)}`);
  };
  return (
    <div className="flex flex-col gap-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(text);
        }}
        className="flex items-center gap-2 rounded-2xl border border-line-strong bg-surface p-1.5 pl-4 shadow-sm transition focus-within:border-brand-600 focus-within:ring-4 focus-within:ring-brand-500/12"
      >
        <Sparkles className="size-5 shrink-0 text-agent-500" aria-hidden />
        <label htmlFor={id} className="sr-only">
          Describe a financial goal
        </label>
        <input
          id={id}
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={300}
          autoFocus={autoFocus}
          placeholder="e.g. I want to buy a ₹75 lakh house"
          className="h-12 min-w-0 flex-1 bg-transparent text-[16px] outline-none placeholder:text-ink-400"
        />
        <button
          type="submit"
          disabled={!text.trim()}
          className={cn(
            "flex h-11 shrink-0 items-center gap-1.5 rounded-xl bg-brand-600 px-4 text-[14px] font-semibold text-white transition hover:bg-brand-700 disabled:bg-ink-400/40",
          )}
        >
          <span className="hidden sm:inline">Analyse</span>
          <ArrowRight className="size-4" aria-hidden />
        </button>
      </form>
      {examples.length ? (
        <div className="flex flex-wrap gap-2">
          {examples.map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => {
                setText(e);
                submit(e);
              }}
              className="min-h-9 rounded-full border border-line bg-surface px-3.5 text-[13px] text-ink-700 transition-colors hover:border-line-strong hover:bg-surface-sunken"
            >
              {e}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
