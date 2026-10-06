import { TONE_CLASSES, type Tone } from "@/lib/presentation";
import { cn } from "@/lib/utils";

/** 0–100 score bar; the unfilled track is a lighter step of the fill. */
export function ScoreBar({
  value,
  tone = "info",
  className,
}: {
  value: number | null;
  tone?: Tone;
  className?: string;
}) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
      role="presentation"
    >
      <div
        className={cn("h-full rounded-full", TONE_CLASSES[tone].bar)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export type BandRange = { code: string; label: string; min: number; max: number; tone: Tone };

/** The passport's band scale with a marker at the score. */
export function BandScale({ bands, score }: { bands: BandRange[]; score: number | null }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="relative flex h-2.5 w-full gap-0.5">
        {bands.map((b) => (
          <div
            key={b.code}
            className={cn(
              "h-full first:rounded-l-full last:rounded-r-full",
              TONE_CLASSES[b.tone].bar,
            )}
            style={{ width: `${b.max - b.min}%`, opacity: 0.35 }}
          />
        ))}
        {score !== null ? (
          <div
            className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-foreground shadow"
            style={{ left: `${Math.max(0, Math.min(100, score))}%` }}
            aria-hidden
          />
        ) : null}
      </div>
      <div className="flex w-full gap-0.5 text-[11px] text-muted-foreground">
        {bands.map((b) => (
          <div key={b.code} className="truncate" style={{ width: `${b.max - b.min}%` }}>
            {b.label} <span className="tabular">{b.min}+</span>
          </div>
        ))}
      </div>
    </div>
  );
}
