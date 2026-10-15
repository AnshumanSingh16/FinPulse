"use client";

import {
  BookUser, CalendarDays, Database, FileText, Gauge, House, Languages, LayoutGrid, MessageCircleQuestion, Plus, Sparkles, Target, Wallet, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useContext, useState } from "react";
import { post } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { DataVersion } from "./data-version";
import { useQuickEntry } from "./quick-entry";
import { cx } from "./ui";

const MAIN = [
  { href: "/", label: "Home", icon: House },
  { href: "/khata/", label: "Khata", icon: BookUser },
  { href: "/money/", label: "Money", icon: Wallet },
  { href: "/ask/", label: "Ask", icon: MessageCircleQuestion },
  { href: "/plan/", label: "Plan", icon: Target },
];
const EXTRA = [
  { href: "/calendar/", label: "Calendar", icon: CalendarDays },
  { href: "/goals/", label: "Goals & budgets", icon: LayoutGrid },
  { href: "/health/", label: "Health score", icon: Gauge },
  { href: "/reports/", label: "Reports", icon: FileText },
  { href: "/data/", label: "Your data", icon: Database },
];

function active(path: string, href: string) {
  return href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
}

export function Logo({ light }: { light?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5" aria-label="FinPilot home">
      <span className="grid size-9 place-items-center rounded-xl border border-[#3a3157] bg-gradient-to-br from-[#2a2342] to-[#0f0f12] text-gold">
        <Sparkles className="size-5" aria-hidden />
      </span>
      <span className={cx("display text-[1.3rem]", light && "text-white")}>FinPilot</span>
    </Link>
  );
}

export function LangToggle({ className }: { className?: string }) {
  const { lang, setLang } = useT();
  return (
    <div className={cx("inline-flex items-center rounded-full border border-line bg-surface p-0.5 text-xs font-semibold", className)} role="group" aria-label="Language">
      <Languages className="mx-1.5 size-3.5 text-ink-2" aria-hidden />
      {(["en", "hi"] as const).map((l) => (
        <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l} className={cx("rounded-full px-2.5 py-1 transition", lang === l ? "bg-[#f4f2ee] text-black shadow-sm" : "text-ink-2")}>
          {l === "en" ? "EN" : "हिं"}
        </button>
      ))}
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname() || "/";
  const { state, refresh } = useContext(DataVersion);
  const { t } = useT();
  const qe = useQuickEntry();
  const [more, setMore] = useState(false);
  const isAsk = active(path, "/ask/");
  const isReport = active(path, "/reports/");

  const useMine = async () => {
    await post("/api/source", { source: "upload" });
    refresh();
  };

  const navItem = (href: string, label: string, I: React.ElementType) => (
    <Link
      key={href}
      href={href}
      className={cx(
        "flex h-11 items-center gap-3 rounded-xl px-3 text-[0.95rem] font-medium transition",
        active(path, href) ? "bg-surface-2 text-ink shadow-[inset_2px_0_0_0_var(--color-gold)]" : "text-ink-2 hover:bg-surface hover:text-ink",
      )}
    >
      <I className="size-5" aria-hidden /> {t(label)}
    </Link>
  );

  return (
    <div className="min-h-dvh">
      <aside className="no-print fixed inset-y-0 left-0 hidden w-64 flex-col overflow-y-auto border-r border-line bg-[#0f0f11] px-4 py-6 lg:flex">
        <div className="flex items-center justify-between px-2">
          <Logo />
        </div>
        <button onClick={() => qe.open()} className="neo mt-6 flex h-12 items-center justify-center gap-2 bg-[#f4f2ee] text-sm font-bold tracking-wider text-black uppercase [--neo-edge:#7d7a85] hover:bg-white">
          <Plus className="size-5" /> {t("New entry")}
        </button>
        <nav className="mt-6 space-y-1" aria-label="Main">
          {MAIN.map(({ href, label, icon }) => navItem(href, label, icon))}
          <div className="my-3 h-px bg-line" />
          {EXTRA.map(({ href, label, icon }) => navItem(href, label, icon))}
        </nav>
        <div className="mt-auto space-y-3 pt-6">
          <LangToggle />
          {state && (
            <div className="rounded-2xl border border-line bg-surface p-3 text-xs text-ink-2">
              <p className="font-semibold text-ink">{state.business}</p>
              <p>{t("Figures up to {date}", { date: state.as_of_label })}</p>
            </div>
          )}
        </div>
      </aside>

      <header className="no-print sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-[#0b0b0d]/90 px-4 backdrop-blur lg:hidden">
        <Logo />
        <LangToggle />
      </header>

      <div className="lg:pl-64">
        {state?.is_demo && !active(path, "/data/") && !isReport && (
          <div className="no-print flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-line bg-[#111114] px-4 py-2 text-center text-xs tracking-wide text-ink-2">
            <span>{t("You're exploring a demo shop with made-up numbers.")}</span>
            {state.upload.ready ? (
              <button onClick={useMine} className="font-semibold text-gold underline underline-offset-2">
                {t("Switch to my business")}
              </button>
            ) : (
              <Link href="/data/" className="font-semibold text-gold underline underline-offset-2">
                {t("Add my own data")}
              </Link>
            )}
          </div>
        )}
        <main className={cx("mx-auto w-full max-w-6xl px-4 sm:px-6", isAsk ? "pb-0 pt-4" : "pb-32 pt-6 lg:pb-12")}>{children}</main>
      </div>

      {/* Mobile tab bar with the big + */}
      <nav className="no-print fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-[#0f0f11]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden" aria-label="Main">
        {[MAIN[0], MAIN[1]].map(({ href, label, icon: I }) => (
          <Link key={href} href={href} className={cx("flex h-16 flex-col items-center justify-center gap-1 text-[0.7rem] font-medium", active(path, href) ? "text-gold" : "text-muted")}>
            <I className="size-[22px]" aria-hidden /> {t(label)}
          </Link>
        ))}
        <div className="grid place-items-center">
          <button onClick={() => qe.open()} className="neo -mt-7 grid size-14 place-items-center bg-[#f4f2ee] text-black [--neo-edge:#7d7a85]" aria-label={t("New entry")}>
            <Plus className="size-7" />
          </button>
        </div>
        <Link href="/ask/" className={cx("flex h-16 flex-col items-center justify-center gap-1 text-[0.7rem] font-medium", active(path, "/ask/") ? "text-gold" : "text-muted")}>
          <MessageCircleQuestion className="size-[22px]" aria-hidden /> {t("Ask")}
        </Link>
        <button onClick={() => setMore(true)} className={cx("flex h-16 flex-col items-center justify-center gap-1 text-[0.7rem] font-medium", more ? "text-gold" : "text-muted")}>
          <LayoutGrid className="size-[22px]" aria-hidden /> {t("More")}
        </button>
      </nav>

      {more && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal aria-label={t("More")}>
          <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={() => setMore(false)} />
          <div className="sheet absolute inset-x-0 bottom-0 rounded-t-3xl border-t border-line bg-surface p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))]">
            <div className="mb-4 flex items-center justify-between">
              <p className="font-semibold">{t("More")}</p>
              <button onClick={() => setMore(false)} aria-label={t("Close")} className="rounded-full p-1.5 hover:bg-canvas">
                <X className="size-5" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {[MAIN[2], MAIN[4], ...EXTRA].map(({ href, label, icon: I }, i) => (
                <Link key={href} href={href} onClick={() => setMore(false)} className="flex flex-col items-center gap-2 rounded-2xl border border-line bg-surface-2 p-3 text-center text-xs font-medium">
                  <span className={cx("grid size-11 place-items-center rounded-2xl", ["grad-violet", "grad-sunset", "grad-mint", "grad-ocean", "grad-berry", "grad-night", "grad-violet"][i % 7])}>
                    <I className="size-5" aria-hidden />
                  </span>
                  {t(label)}
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
