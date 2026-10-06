import type * as React from "react";

import { TONE_CLASSES, type Tone } from "@/lib/presentation";
import { cn } from "@/lib/utils";

/** A stat tile: label · value · optional delta · optional trend. */
export function StatTile({
  label,
  value,
  sub,
  delta,
  trend,
  badge,
  className,
  hero = false,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  delta?: { text: string; tone: Tone; caption?: string } | null;
  trend?: React.ReactNode;
  badge?: React.ReactNode;
  className?: string;
  hero?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-4 shadow-xs sm:p-5",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {badge}
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span
            className={cn(
              "leading-none font-semibold tracking-tight",
              hero ? "text-5xl" : "text-2xl",
            )}
          >
            {value}
          </span>
          {delta ? (
            <span className={cn("text-xs font-medium", TONE_CLASSES[delta.tone].text)}>
              {delta.text}
              {delta.caption ? (
                <span className="font-normal text-muted-foreground"> {delta.caption}</span>
              ) : null}
            </span>
          ) : null}
        </div>
        {trend ? <div className="shrink-0">{trend}</div> : null}
      </div>
      {sub ? <div className="text-xs text-pretty text-muted-foreground">{sub}</div> : null}
    </div>
  );
}
