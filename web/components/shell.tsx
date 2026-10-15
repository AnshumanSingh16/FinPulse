"use client";

import { Database, House, MessageCircleQuestion, Sparkles, Target, Wallet } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useContext } from "react";
import { post } from "@/lib/api";
import { DataVersion } from "./data-version";
import { cx } from "./ui";

const NAV = [
  { href: "/", label: "Home", icon: House },
  { href: "/money/", label: "Money", icon: Wallet },
  { href: "/ask/", label: "Ask", icon: MessageCircleQuestion },
  { href: "/plan/", label: "Plan", icon: Target },
];

function active(path: string, href: string) {
  return href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
}

export function Logo({ compact }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5" aria-label="FinPilot home">
      <span className="grid size-9 place-items-center rounded-xl bg-brand text-white shadow-sm">
        <Sparkles className="size-5" aria-hidden />
      </span>
      {!compact && <span className="text-[1.15rem] font-semibold tracking-tight">FinPilot</span>}
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname() || "/";
  const { state, refresh } = useContext(DataVersion);
  const isAsk = active(path, "/ask/");

  const useMine = async () => {
    await post("/api/source", { source: "upload" });
    refresh();
  };

  return (
    <div className="min-h-dvh">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-line bg-surface px-4 py-6 lg:flex">
        <div className="px-2">
          <Logo />
        </div>
        <nav className="mt-8 space-y-1" aria-label="Main">
          {NAV.map(({ href, label, icon: I }) => (
            <Link
              key={href}
              href={href}
              className={cx(
                "flex h-11 items-center gap-3 rounded-xl px-3 text-[0.95rem] font-medium transition",
                active(path, href) ? "bg-brand-50 text-brand" : "text-ink-2 hover:bg-canvas hover:text-ink",
              )}
            >
              <I className="size-5" aria-hidden /> {label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          <Link
            href="/data/"
            className={cx(
              "flex h-11 items-center gap-3 rounded-xl px-3 text-[0.95rem] font-medium",
              active(path, "/data/") ? "bg-brand-50 text-brand" : "text-ink-2 hover:bg-canvas hover:text-ink",
            )}
          >
            <Database className="size-5" aria-hidden /> Your data
          </Link>
          {state && (
            <div className="rounded-2xl bg-canvas p-3 text-xs text-ink-2">
              <p className="font-medium text-ink">{state.business}</p>
              <p>Figures up to {state.as_of_label}</p>
            </div>
          )}
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-surface/90 px-4 backdrop-blur lg:hidden">
        <Logo />
        <Link href="/data/" className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-sm text-ink-2">
          <Database className="size-4" aria-hidden /> Your data
        </Link>
      </header>

      <div className="lg:pl-60">
        {state?.is_demo && !active(path, "/data/") && (
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-[#13201a] px-4 py-2 text-center text-sm text-white/90">
            <span>You&apos;re exploring a demo shop with made-up numbers.</span>
            {state.upload.ready ? (
              <button onClick={useMine} className="font-semibold text-white underline underline-offset-2">
                Switch to my business
              </button>
            ) : (
              <Link href="/data/" className="font-semibold text-white underline underline-offset-2">
                Add my own data
              </Link>
            )}
          </div>
        )}
        <main className={cx("mx-auto w-full max-w-5xl px-4 sm:px-6", isAsk ? "pb-0 pt-4" : "pb-28 pt-6 lg:pb-12")}>{children}</main>
      </div>

      {/* Mobile tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Main">
        {NAV.map(({ href, label, icon: I }) => (
          <Link key={href} href={href} className={cx("flex h-16 flex-col items-center justify-center gap-1 text-xs font-medium", active(path, href) ? "text-brand" : "text-muted")}>
            <I className="size-[22px]" aria-hidden /> {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
