"use client";

import { CalendarRange, ChevronDown, Gauge, Languages, MessageCircle, Monitor, Moon, Navigation2, Settings, Sun, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useContext, useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { BusinessSheet } from "./business";
import { DataVersion } from "./data-version";
import { cx } from "./ui";

/** FinPilot's mark: a pilot's arrow on the brand tile. */
export function BrandMark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const box = size === "sm" ? "size-8" : size === "lg" ? "size-14" : "size-10";
  const ic = size === "sm" ? "size-4" : size === "lg" ? "size-7" : "size-5";
  return (
    <span className={cx("grad-hero grid shrink-0 place-items-center rounded-2xl text-[#ffd27a] shadow-sm", box)} aria-hidden>
      <Navigation2 className={cx(ic, "rotate-45 fill-current")} />
    </span>
  );
}

export function LangToggle({ className }: { className?: string }) {
  const { lang, setLang } = useT();
  return (
    <div className={cx("inline-flex items-center rounded-full border border-line bg-surface p-0.5 text-xs font-semibold", className)} role="group" aria-label="Language">
      <Languages className="mx-1.5 size-3.5 text-ink-2" aria-hidden />
      {(["en", "hi"] as const).map((l) => (
        <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l} className={cx("rounded-full px-2.5 py-1 transition", lang === l ? "bg-brand text-on-brand shadow-sm" : "text-ink-2")}>
          {l === "en" ? "EN" : "हिं"}
        </button>
      ))}
    </div>
  );
}

type Theme = "auto" | "light" | "dark";

export function ThemeToggle({ className }: { className?: string }) {
  const { t } = useT();
  const [theme, setTheme] = useState<Theme>("auto");
  useEffect(() => {
    try {
      const v = localStorage.getItem("finpilot.theme");
      if (v === "light" || v === "dark") setTheme(v);
    } catch {}
  }, []);
  const choose = (v: Theme) => {
    setTheme(v);
    try {
      if (v === "auto") localStorage.removeItem("finpilot.theme");
      else localStorage.setItem("finpilot.theme", v);
    } catch {}
    if (v === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = v;
  };
  const opts: [Theme, React.ElementType, string][] = [["light", Sun, "Light"], ["auto", Monitor, "Auto"], ["dark", Moon, "Dark"]];
  return (
    <div className={cx("inline-flex items-center rounded-full border border-line bg-surface p-0.5", className)} role="group" aria-label={t("Theme")}>
      {opts.map(([v, I, label]) => (
        <button key={v} onClick={() => choose(v)} aria-pressed={theme === v} title={t(label)} aria-label={t(label)}
          className={cx("grid size-7 place-items-center rounded-full transition", theme === v ? "bg-brand text-on-brand shadow-sm" : "text-ink-2 hover:text-ink")}>
          <I className="size-3.5" aria-hidden />
        </button>
      ))}
    </div>
  );
}

const TABS = [
  { href: "/", label: "Today", I: Gauge },
  { href: "/timeline/", label: "Timeline", I: CalendarRange },
  { href: "/ask/", label: "Ask", I: MessageCircle },
  { href: "/khata/", label: "People", I: Users },
];

function isOn(path: string, href: string) {
  return href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname() || "/";
  const { t } = useT();
  const { state } = useContext(DataVersion);
  const [pick, setPick] = useState(false);
  const isChat = path.startsWith("/ask");
  return (
    <div className={cx("mx-auto flex w-full max-w-4xl flex-col", isChat ? "h-dvh" : "min-h-dvh")}>
      <header className="no-print sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-canvas/90 px-3 backdrop-blur sm:px-4">
        <Link href="/" className="flex items-center gap-2" aria-label="FinPilot">
          <BrandMark size="sm" />
          <span className="hidden text-lg font-bold tracking-tight md:inline">FinPilot</span>
        </Link>
        <button onClick={() => setPick(true)} className="ml-1 inline-flex min-w-0 items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-semibold shadow-sm hover:border-brand" aria-label={t("Switch business")}>
          <span className="truncate">{state?.business.replace(" (fictional)", "") ?? "…"}</span>
          {state?.is_demo && <span className="rounded-full bg-caution-50 px-1.5 text-[0.65rem] font-bold text-caution uppercase">{t("demo")}</span>}
          <ChevronDown className="size-4 shrink-0 text-muted" />
        </button>
        <nav className="mx-auto hidden rounded-full border border-line bg-surface p-1 sm:inline-flex" aria-label="Main">
          {TABS.map(({ href, label, I }) => (
            <Link key={href} href={href} aria-current={isOn(path, href) ? "page" : undefined}
              className={cx("inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-sm font-semibold transition", isOn(path, href) ? "bg-brand text-on-brand shadow-sm" : "text-ink-2 hover:text-ink")}>
              <I className="size-4" aria-hidden /> {t(label)}
            </Link>
          ))}
        </nav>
        <Link href="/settings/" aria-label={t("Settings")}
          className={cx("ml-auto grid size-10 shrink-0 place-items-center rounded-full transition hover:bg-surface-2 sm:ml-0", path.startsWith("/settings") ? "text-brand" : "text-ink-2")}>
          <Settings className="size-5" />
        </Link>
      </header>
      <main className={cx("flex w-full flex-1 flex-col", isChat ? "min-h-0 pb-16 sm:pb-0" : "px-4 pt-5 pb-24 sm:px-5 sm:pb-16")}>{children}</main>
      <nav className="no-print fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden" aria-label="Main">
        {TABS.map(({ href, label, I }) => (
          <Link key={href} href={href} aria-current={isOn(path, href) ? "page" : undefined}
            className={cx("flex h-14 flex-col items-center justify-center gap-0.5 text-[0.7rem] font-semibold", isOn(path, href) ? "text-brand" : "text-muted")}>
            <I className="size-5" aria-hidden /> {t(label)}
          </Link>
        ))}
      </nav>
      <BusinessSheet open={pick} onClose={() => setPick(false)} />
    </div>
  );
}
