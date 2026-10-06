import type { RiskTimelinePoint } from "@finpulse/contracts";

import { formatMonthShort } from "@/lib/format";
import { TONE_CLASSES, label, riskTone } from "@/lib/presentation";
import { cn } from "@/lib/utils";

/** One cell per month-end: the early-warning level (colour + letter), index below. */
export function RiskTimeline({
  points,
  compact = false,
}: {
  points: RiskTimelinePoint[];
  compact?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <ol
        className="grid gap-0.5"
        style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}
      >
        {points.map((p) => {
          const tone = riskTone(p.level);
          return (
            <li
              key={p.as_of}
              className="group relative flex flex-col items-center gap-1"
              title={`${p.as_of}: ${label(p.level)} risk, index ${p.index}${p.rules.length ? ` — ${p.rules.join(", ")}` : ""}`}
            >
              <span
                className={cn(
                  "flex w-full items-center justify-center rounded-[3px] text-[10px] font-bold text-white/95",
                  compact ? "h-5" : "h-8",
                  TONE_CLASSES[tone].bar,
                  tone === "warning" && "text-black/70",
                )}
              >
                {p.level === "none" ? "–" : label(p.level)[0]}
              </span>
              {!compact ? (
                <span className="tabular text-[10px] text-muted-foreground">{p.index}</span>
              ) : null}
            </li>
          );
        })}
      </ol>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{points[0] ? formatMonthShort(points[0].as_of) : ""}</span>
        <span>{points.at(-1) ? formatMonthShort(points.at(-1)!.as_of) : ""}</span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
        {["none", "low", "medium", "high", "critical"].map((l) => (
          <span key={l} className="flex items-center gap-1">
            <span
              className={cn("inline-block size-2 rounded-[2px]", TONE_CLASSES[riskTone(l)].bar)}
            />
            {l === "none" ? "None" : `${label(l)[0]} = ${label(l)}`}
          </span>
        ))}
      </div>
    </div>
  );
}
