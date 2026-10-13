"use client";

import { Ellipsis, Plus, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { PulseMark } from "@/components/personal/kit";
import { usePersonal } from "@/components/personal/provider";
import { cn } from "@/lib/utils";

import { NAV_GROUPS, PERSONAL_SECTIONS, isActive, type PersonalSection } from "./personal-nav";

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 rounded-lg" aria-label="FinPulse home">
      <PulseMark size="sm" />
      <span className="font-display text-[17px] font-extrabold tracking-tight">FinPulse</span>
    </Link>
  );
}

/** Plans waiting for the user's decision: a real count from the server state. */
function useReviewCount(): number {
  const { state } = usePersonal();
  return state?.actionPlans.filter((p) => p.status === "awaiting_review").length ?? 0;
}

function CountBadge({ n }: { n: number }) {
  if (!n) return null;
  return (
    <span
      className="tabular ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-caution-500 px-1.5 text-[11px] leading-5 font-semibold text-white"
      aria-label={`${n} waiting for review`}
    >
      {n}
    </span>
  );
}

function NavItem({ s, active, badge }: { s: PersonalSection; active: boolean; badge?: number }) {
  return (
    <Link
      href={s.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex min-h-9 items-center gap-2.5 rounded-lg px-2.5 text-[14px] transition-colors duration-150",
        active
          ? "bg-surface-sunken font-semibold text-ink-900"
          : "text-ink-500 hover:bg-surface-sunken/70 hover:text-ink-900",
      )}
    >
      {active ? (
        <span
          className="absolute top-1.5 bottom-1.5 -left-3 w-[3px] rounded-r-full bg-brand-600"
          aria-hidden
        />
      ) : null}
      <s.icon className={cn("size-[17px] shrink-0", active && "text-brand-600")} aria-hidden />
      <span className="truncate">{s.label}</span>
      {badge ? <CountBadge n={badge} /> : null}
    </Link>
  );
}

function AiStatus() {
  const { state } = usePersonal();
  if (!state) return null;
  const on = state.status.ai.enabled;
  return (
    <div className="flex items-start gap-2.5 rounded-xl bg-surface-sunken p-3 text-[12px] leading-snug">
      <span
        className={cn("mt-1 size-2 shrink-0 rounded-full", on ? "bg-brand-500" : "bg-ink-400")}
        aria-hidden
      />
      <span className="text-ink-500">
        <span className="font-semibold text-ink-900">{on ? "AI agents on" : "AI off"}</span>
        <br />
        {on ? "Live research and AI answers" : "Calculations and rule-based agents still work"}
        {" · "}
        {state.status.research.mode === "live" ? "live rates" : "rates are estimates"}
      </span>
    </div>
  );
}

function NavBody() {
  const pathname = usePathname();
  const reviews = useReviewCount();
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-5">
      <div className="px-2.5">
        <Brand />
      </div>
      <Link
        href="/afford"
        className="mx-0.5 flex h-10 items-center justify-center gap-2 rounded-xl bg-ink-900 text-sm font-semibold text-white shadow-xs transition hover:bg-ink-700 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <Plus className="size-4" aria-hidden /> New analysis
      </Link>
      <nav aria-label="Main" className="flex flex-col gap-4">
        {NAV_GROUPS.map((g) => (
          <div key={g} className="flex flex-col gap-0.5">
            <div className="px-2.5 pb-1 text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
              {g}
            </div>
            {PERSONAL_SECTIONS.filter((s) => s.group === g).map((s) => (
              <NavItem
                key={s.href}
                s={s}
                active={isActive(pathname, s.href)}
                badge={s.href === "/actions" ? reviews : undefined}
              />
            ))}
          </div>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-3">
        <AiStatus />
        <p className="px-1 text-[11px] leading-relaxed text-ink-400">
          Decision support, not financial advice. FinPulse never submits applications or moves
          money.
        </p>
      </div>
    </div>
  );
}

/** Desktop: a compact, grouped left rail. Mobile: a top bar plus a bottom tab bar. */
export function Sidebar() {
  const pathname = usePathname();
  const reviews = useReviewCount();
  const { state } = usePersonal();
  // "More" belongs to the page it was opened on: navigating closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const tabs = PERSONAL_SECTIONS.filter((s) => s.tab);
  const moreActive = !tabs.some((t) => isActive(pathname, t.href));

  return (
    <>
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-line bg-surface lg:block">
        <NavBody />
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur-md lg:hidden">
        <Brand />
        {state ? (
          <span className="ml-auto flex items-center gap-1.5 text-[12px] text-ink-500">
            <span
              className={cn(
                "size-2 rounded-full",
                state.status.ai.enabled ? "bg-brand-500" : "bg-ink-400",
              )}
              aria-hidden
            />
            {state.status.ai.enabled ? "AI on" : "AI off"}
          </span>
        ) : (
          <span className="ml-auto" />
        )}
        <Link
          href="/afford"
          aria-label="New analysis"
          className="flex size-9 items-center justify-center rounded-full bg-ink-900 text-white"
        >
          <Plus className="size-4" aria-hidden />
        </Link>
      </header>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
      >
        {tabs.map((t) => {
          const active = isActive(pathname, t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex min-h-[60px] flex-col items-center justify-center gap-1 text-[11px]",
                active ? "font-semibold text-brand-700" : "text-ink-500",
              )}
            >
              <span className="relative">
                <t.icon className="size-[22px]" aria-hidden />
                {t.href === "/actions" && reviews ? (
                  <span className="absolute -top-1 -right-2 flex size-4 items-center justify-center rounded-full bg-caution-500 text-[10px] font-bold text-white">
                    {reviews}
                  </span>
                ) : null}
              </span>
              {t.short}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => setOpenOn(pathname)}
          className={cn(
            "flex min-h-[60px] flex-col items-center justify-center gap-1 text-[11px]",
            moreActive ? "font-semibold text-brand-700" : "text-ink-500",
          )}
          aria-haspopup="dialog"
          aria-label={reviews ? `More (${reviews} awaiting review)` : "More"}
        >
          <span className="relative">
            <Ellipsis className="size-[22px]" aria-hidden />
            {reviews ? (
              <span className="absolute -top-1 -right-2 flex size-4 items-center justify-center rounded-full bg-caution-500 text-[10px] font-bold text-white">
                {reviews}
              </span>
            ) : null}
          </span>
          More
        </button>
      </nav>

      {open ? (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Menu"
        >
          <button
            type="button"
            className="absolute inset-0 bg-ink-900/40"
            aria-label="Close menu"
            onClick={() => setOpenOn(null)}
          />
          <div className="fp-rise absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] shadow-md">
            <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-line-strong" aria-hidden />
            <button
              type="button"
              onClick={() => setOpenOn(null)}
              className="absolute top-3 right-3 rounded-full p-2 hover:bg-surface-sunken"
              aria-label="Close menu"
            >
              <X className="size-5" />
            </button>
            <NavBody />
          </div>
        </div>
      ) : null}
    </>
  );
}
