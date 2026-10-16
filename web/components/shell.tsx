"use client";

import { BookUser, Languages, MessageCircle, Monitor, Moon, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { cx } from "./ui";

/** Munshi's mark: a ledger-green tile with a saffron "म". */
export function MunshiMark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const box = size === "sm" ? "size-8 text-base" : size === "lg" ? "size-14 text-2xl" : "size-10 text-lg";
  return (
    <span className={cx("grad-hero grid shrink-0 place-items-center rounded-2xl font-bold text-[#ffd27a] shadow-sm", box)} aria-hidden>
      म
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
  { href: "/", label: "Munshi", I: MessageCircle },
  { href: "/khata/", label: "Khata", I: BookUser },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname() || "/";
  const { t } = useT();
  const isChat = path === "/";
  const isPrint = path.startsWith("/reports");
  return (
    <div className={cx("mx-auto flex w-full max-w-3xl flex-col", isChat ? "h-dvh" : "min-h-dvh")}>
      <header className="no-print sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-canvas/90 px-3 backdrop-blur sm:px-4">
        <Link href="/" className="flex items-center gap-2" aria-label="Munshi">
          <MunshiMark size="sm" />
          <span className="hidden text-lg font-bold tracking-tight sm:inline">Munshi</span>
        </Link>
        <nav className="mx-auto inline-flex rounded-full border border-line bg-surface p-1" aria-label="Main">
          {TABS.map(({ href, label, I }) => {
            const on = href === "/" ? isChat : path.startsWith(href.replace(/\/$/, ""));
            return (
              <Link key={href} href={href} aria-current={on ? "page" : undefined}
                className={cx("inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-sm font-semibold transition", on ? "bg-brand text-on-brand shadow-sm" : "text-ink-2 hover:text-ink")}>
                <I className="size-4" aria-hidden /> {t(label)}
              </Link>
            );
          })}
        </nav>
        <Link href="/settings/" aria-label={t("Settings")}
          className={cx("grid size-10 place-items-center rounded-full transition hover:bg-surface-2", path.startsWith("/settings") ? "text-brand" : "text-ink-2")}>
          <Settings className="size-5" />
        </Link>
      </header>
      <main className={cx("flex w-full flex-1 flex-col", isChat ? "min-h-0" : "px-4 pt-5 pb-16 sm:px-5", isPrint && "max-w-none")}>{children}</main>
    </div>
  );
}
