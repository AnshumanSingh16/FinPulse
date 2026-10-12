"use client";

import { Activity, Briefcase, Menu, Presentation, ServerCog, X } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useSearchParams } from "next/navigation";
import { useState } from "react";

import { cn } from "@/lib/utils";

import { SECTIONS, currentSection, sectionHref } from "./nav";
import { PERSONAL_SECTIONS } from "./personal-nav";

function Brand() {
  return (
    <Link
      href="/"
      className="flex items-center gap-2.5 font-semibold tracking-tight text-sidebar-foreground"
    >
      <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <Activity className="size-4" aria-hidden />
      </span>
      <span className="flex flex-col leading-none">
        <span>FinPulse</span>
        <span className="mt-1 text-[10px] font-medium tracking-[0.12em] text-sidebar-muted uppercase">
          On autopilot
        </span>
      </span>
    </Link>
  );
}

function NavLink({
  href,
  active,
  icon: Icon,
  children,
  highlight,
}: {
  href: string;
  active: boolean;
  icon: typeof Activity;
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
        active
          ? "bg-sidebar-accent font-medium text-sidebar-foreground"
          : highlight
            ? "text-primary hover:bg-sidebar-accent/60"
            : "text-sidebar-muted hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      <span className="truncate">{children}</span>
    </Link>
  );
}

function SidebarBody() {
  const pathname = usePathname();
  const params = useParams<{ entityId?: string }>();
  const asOf = useSearchParams().get("asOf");
  const entityId = params.entityId;
  const section = currentSection(pathname);
  const inBusiness =
    pathname.startsWith("/business") || pathname.startsWith("/entities") || pathname === "/demo";

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      <Brand />
      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {PERSONAL_SECTIONS.map((s) => (
          <NavLink
            key={s.href}
            href={s.href}
            active={s.href === "/" ? pathname === "/" : pathname.startsWith(s.href)}
            icon={s.icon}
            highlight={s.primary}
          >
            {s.label}
          </NavLink>
        ))}
      </nav>
      <nav aria-label="Business module" className="flex flex-col gap-0.5">
        <div className="mb-1 px-2.5 text-[10px] font-semibold tracking-[0.12em] text-sidebar-muted uppercase">
          Business module
        </div>
        <NavLink href="/business" active={pathname === "/business"} icon={Briefcase}>
          Business risk portfolio
        </NavLink>
        {inBusiness ? (
          <NavLink href="/demo" active={pathname === "/demo"} icon={Presentation}>
            Business demo walkthrough
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
        <p className="px-2.5 text-[11px] leading-relaxed text-sidebar-muted">
          Decision support, not financial advice. Demo data is fictional. FinPulse never submits
          applications or moves money.
        </p>
      </div>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  // The menu belongs to the page it was opened on: navigating closes it.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const setOpen = (value: boolean) => setOpenOn(value ? pathname : null);

  return (
    <>
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 bg-sidebar lg:block">
        <SidebarBody />
      </aside>
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-sidebar px-4 lg:hidden">
        <Brand />
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-md p-2 text-sidebar-foreground hover:bg-sidebar-accent"
          aria-label="Open navigation"
        >
          <Menu className="size-5" />
        </button>
      </header>
      {open ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-72 bg-sidebar shadow-xl">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="absolute top-3 right-3 rounded-md p-2 text-sidebar-foreground hover:bg-sidebar-accent"
              aria-label="Close navigation"
            >
              <X className="size-5" />
            </button>
            <SidebarBody />
          </div>
        </div>
      ) : null}
    </>
  );
}
