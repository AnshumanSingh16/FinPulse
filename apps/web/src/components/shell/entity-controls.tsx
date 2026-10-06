"use client";

import type { EntitySummary } from "@finpulse/contracts";
import { CalendarClock, ChevronsUpDown } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

import { formatDate, formatMonth } from "@/lib/format";
import { cn } from "@/lib/utils";

import { currentSection, sectionHref } from "./nav";

const selectClass =
  "h-9 appearance-none rounded-md border bg-card pr-8 pl-8 text-sm font-medium shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60";

/** Switch entity, staying on the same section (the date resets: entities' data ranges differ). */
export function EntitySwitcher({
  entities,
  entityId,
}: {
  entities: EntitySummary[];
  entityId: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, start] = useTransition();
  return (
    <label className="relative inline-flex items-center">
      <span className="sr-only">Entity</span>
      <ChevronsUpDown
        className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground"
        aria-hidden
      />
      <select
        className={cn(selectClass, "max-w-72 pl-8")}
        value={entityId}
        disabled={pending}
        onChange={(e) =>
          start(() => router.push(sectionHref(e.target.value, currentSection(pathname))))
        }
      >
        {entities.map((e) => (
          <option key={e.id} value={e.id}>
            {e.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Month-end dates between the first complete month and the end of the data. Calendar only. */
export function monthEnds(first: string, last: string): string[] {
  const out: string[] = [];
  const [ly = 0, lm = 0] = last.split("-").map(Number);
  let [y = 0, m = 0] = first.split("-").map(Number);
  while (y < ly || (y === ly && m < lm)) {
    const end = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
    if (end > first) out.push(end);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out.reverse();
}

/** View every page as the data stood at an earlier month-end (no look-ahead in the engines). */
export function AsOfSelect({ first, last }: { first: string; last: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [pending, start] = useTransition();
  const value = params.get("asOf") ?? "";
  const options = monthEnds(first, last).filter((d) => d !== last);
  return (
    <label className="relative inline-flex items-center">
      <span className="sr-only">As of</span>
      <CalendarClock
        className="pointer-events-none absolute left-2.5 size-4 text-muted-foreground"
        aria-hidden
      />
      <select
        className={cn(selectClass, pending && "animate-pulse")}
        value={value}
        disabled={pending}
        onChange={(e) => {
          const next = new URLSearchParams(params.toString());
          if (e.target.value) next.set("asOf", e.target.value);
          else next.delete("asOf");
          const qs = next.toString();
          start(() => router.push(qs ? `${pathname}?${qs}` : pathname));
        }}
      >
        <option value="">Latest · {formatDate(last)}</option>
        {options.map((d) => (
          <option key={d} value={d}>
            As of {formatMonth(d)}
          </option>
        ))}
      </select>
    </label>
  );
}
