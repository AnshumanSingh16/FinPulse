"use client";

import { CalendarRange, ChevronDown, HelpCircle, Languages, Menu, MessageCircle, Monitor, Moon, Navigation2, Settings, Sun, Target, Users, X } from "lucide-react";
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

const LINKS = [
  { href: "/", label: "Desk", I: MessageCircle },
  { href: "/timeline/", label: "Timeline", I: CalendarRange },
  { href: "/khata/", label: "People", I: Users },
  { href: "/proof/", label: "Track record", I: Target },
  { href: "/about/", label: "Q&A", I: HelpCircle },
];

function isOn(path: string, href: string) {
  return href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
}

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname() || "/";
  const { t } = useT();
  const { state } = useContext(DataVersion);
  const [pick, setPick] = useState(false);
  const [menu, setMenu] = useState(false);
  const desk = path === "/";
  const isChat = path.startsWith("/ask");
  useEffect(() => {
    setMenu(false);
  }, [path]);
  return (
    <div className={cx("flex w-full flex-col", desk || isChat ? "h-dvh" : "min-h-dvh")}>
      <header className="no-print sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-canvas/90 px-3 backdrop-blur sm:px-5">
        <Link href="/" className="flex items-center gap-2" aria-label="FinPilot">
          <BrandMark size="sm" />
          <span className="serif hidden text-xl font-semibold tracking-tight sm:inline">FinPilot</span>
        </Link>
        <button onClick={() => setPick(true)} className="ml-1 inline-flex min-w-0 items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-semibold hover:border-brand" aria-label={t("Switch business")}>
          <span className="truncate">{state?.business.replace(" (fictional)", "") ?? "…"}</span>
          {state?.is_demo && <span className="rounded-full bg-caution-50 px-1.5 text-[0.65rem] font-bold text-caution uppercase">{t("demo")}</span>}
          <ChevronDown className="size-4 shrink-0 text-muted" />
        </button>
        <nav className="ml-auto hidden items-center gap-1 md:flex" aria-label="Main">
          {LINKS.map(({ href, label }) => (
            <Link key={href} href={href} aria-current={isOn(path, href) ? "page" : undefined}
              className={cx("rounded-full px-3 py-1.5 text-sm font-medium transition", isOn(path, href) ? "bg-ink text-canvas" : "text-ink-2 hover:text-ink")}>
              {t(label)}
            </Link>
          ))}
        </nav>
        <LangToggle className="ml-auto hidden sm:inline-flex md:ml-2" />
        <Link href="/settings/" aria-label={t("Settings")}
          className={cx("hidden size-10 shrink-0 place-items-center rounded-full transition hover:bg-surface-2 md:grid", path.startsWith("/settings") ? "text-brand" : "text-ink-2")}>
          <Settings className="size-5" />
        </Link>
        <button onClick={() => setMenu(!menu)} aria-label={t("Menu")} aria-expanded={menu} className="ml-auto grid size-10 place-items-center rounded-full text-ink-2 hover:bg-surface-2 sm:ml-1 md:hidden">
          {menu ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
        {menu && (
          <div className="absolute top-14 right-3 z-40 w-56 rounded-2xl border border-line bg-surface p-1.5 shadow-xl md:hidden">
            {[...LINKS, { href: "/settings/", label: "Settings", I: Settings }].map(({ href, label, I }) => (
              <Link key={href} href={href} className={cx("flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium", isOn(path, href) ? "bg-brand-50 text-brand" : "text-ink hover:bg-surface-2")}>
                <I className="size-4" /> {t(label)}
              </Link>
            ))}
            <div className="px-3 py-2 sm:hidden"><LangToggle /></div>
          </div>
        )}
      </header>
      <main className={cx("flex w-full flex-1 flex-col", desk ? "min-h-0" : isChat ? "mx-auto min-h-0 max-w-3xl" : "mx-auto max-w-4xl px-4 pt-5 pb-16 sm:px-5")}>{children}</main>
      <BusinessSheet open={pick} onClose={() => setPick(false)} />
    </div>
  );
}
