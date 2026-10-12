"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  "I want to buy a ₹75 lakh house",
  "A ₹20 lakh car with 30% down",
  "An MBA costing ₹30 lakh",
];

/**
 * "Describe your goal" box. Submitting opens the guided affordability flow with the goal text;
 * the flow reads it with the same rule-based interpreter the Planner agent uses.
 */
export function GoalInput({
  initial = "",
  onSubmit,
  autoFocus,
  size = "lg",
}: {
  initial?: string;
  onSubmit?: (goal: string) => void;
  autoFocus?: boolean;
  size?: "lg" | "md";
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
        className={cn(
          "flex items-center gap-2 rounded-2xl border border-input bg-background p-1.5 pl-4 transition focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/15",
        )}
      >
        <label htmlFor={id} className="sr-only">
          Describe what you want to buy
        </label>
        <input
          id={id}
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={300}
          autoFocus={autoFocus}
          placeholder="e.g. I want to buy a ₹75 lakh house"
          className={cn(
            "min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground/70",
            size === "lg" ? "h-11 text-base" : "h-10 text-[15px]",
          )}
        />
        <Button type="submit" size={size === "lg" ? "lg" : "default"} disabled={!text.trim()}>
          <span className="hidden sm:inline">Check</span>
          <ArrowRight />
        </Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((e) => (
          <button
            key={e}
            type="button"
            onClick={() => {
              setText(e);
              submit(e);
            }}
            className="min-h-9 rounded-full bg-muted px-3 text-xs text-muted-foreground transition hover:bg-accent hover:text-accent-foreground"
          >
            {e}
          </button>
        ))}
      </div>
    </div>
  );
}
