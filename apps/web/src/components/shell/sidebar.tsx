"use client";

import { Activity, Briefcase, Ellipsis, Presentation, ServerCog, X } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";

import { cn } from "@/lib/utils";

import { SECTIONS, currentSection, sectionHref } from "./nav";
import { PERSONAL_SECTIONS, isActive } from "./personal-nav";

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
      <span className="flex size-8 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <Activity className="size-4" aria-hidden />
      </span>
      <span className="text-[17px]">FinPulse</span>
    </Link>
  );
}

function NavLink({
  href,
  active,
  icon: Icon,
  children,
}: {
  href: string;
  active: boolean;
  icon: typeof Activity;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition-colors",
        active
          ? "bg-accent font-medium text-accent-foreground"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon className="size-[18px] shrink-0" aria-hidden />
      <span className="truncate">{children}</span>
    </Link>
  );
}

function NavBody() {
  const pathname = usePathname();
  const params = useParams<{ entityId?: string }>();
  const asOf = useSearchParams().get("asOf");
  const entityId = params.entityId;
  const section = currentSection(pathname);
  const inBusiness =
    pathname.startsWith("/business") || pathname.startsWith("/entities") || pathname === "/demo";

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto px-3 py-5">
      <div className="px-2">
        <Brand />
      </div>
      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {PERSONAL_SECTIONS.map((s) => (
          <NavLink key={s.href} href={s.href} active={isActive(pathname, s.href)} icon={s.icon}>
            {s.label}
          </NavLink>
        ))}
      </nav>
      <nav aria-label="Business module" className="flex flex-col gap-0.5">
        <div className="mb-1 px-3 text-[11px] font-medium text-muted-foreground">
          For businesses
        </div>
        <NavLink href="/business" active={pathname === "/business"} icon={Briefcase}>
          Business risk
        </NavLink>
        {inBusiness ? (
          <NavLink href="/demo" active={pathname === "/demo"} icon={Presentation}>
            Business demo
          </NavLink>
        ) : null}
        {entityId
          ? SECTIONS.map((s) => (
              <NavLink
                key={s.slug}
                href={sectionHref(entityId, s.slug, asOf)}
                active={section === s.slug}
                icon={s.icon}
              >
                {s.label}
              </NavLink>
            ))
          : null}
      </nav>
      <div className="mt-auto flex flex-col gap-3">
        <NavLink href="/system" active={pathname === "/system"} icon={ServerCog}>
          System status
        </NavLink>
        <p className="px-3 text-[11px] leading-relaxed text-muted-foreground">
          Decision support, not financial advice. FinPulse never submits applications or moves
          money.
        </p>
      </div>
    </div>
  );
}

/** Desktop: a quiet left rail. Mobile: a top bar plus a thumb-reachable bottom tab bar. */
export function Sidebar() {
  const pathname = usePathname();
  // "More" belongs to the page it was opened on: navigating closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const tabs = PERSONAL_SECTIONS.filter((s) => s.tab);
  const moreActive = !tabs.some((t) => isActive(pathname, t.href));

  return (
    <>
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 border-r bg-sidebar lg:block">
        <NavBody />
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center border-b bg-background/95 px-4 backdrop-blur lg:hidden">
        <Brand />
      </header>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {tabs.map((t) => {
          const active = isActive(pathname, t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px]",
                active ? "font-medium text-primary" : "text-muted-foreground",
              )}
            >
              <t.icon className="size-5" aria-hidden />
              {t.short}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => setOpenOn(pathname)}
          className={cn(
            "flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px]",
            moreActive ? "font-medium text-primary" : "text-muted-foreground",
          )}
          aria-haspopup="dialog"
        >
          <Ellipsis className="size-5" aria-hidden />
          More
        </button>
      </nav>

      {open ? (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="More"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            aria-label="Close menu"
            onClick={() => setOpenOn(null)}
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-2xl bg-background shadow-xl">
            <button
              type="button"
              onClick={() => setOpenOn(null)}
              className="absolute top-4 right-4 rounded-full p-2 hover:bg-muted"
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
