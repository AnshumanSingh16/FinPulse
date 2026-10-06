import { Activity, BookOpen, FlaskConical, LayoutDashboard, Siren, Users } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

type NavItem = {
  label: string;
  icon: typeof Activity;
  href?: string;
  /** Development-plan phase that delivers this page. Items without an href aren't built yet. */
  plannedPhase?: number;
};

const NAV: NavItem[] = [
  { label: "Overview", icon: LayoutDashboard, href: "/" },
  { label: "Subjects", icon: Users, plannedPhase: 1 },
  { label: "Alerts", icon: Siren, plannedPhase: 4 },
  { label: "Methodology", icon: BookOpen, plannedPhase: 2 },
  { label: "Evaluation", icon: FlaskConical, plannedPhase: 4 },
];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <Activity className="size-4" aria-hidden />
      </span>
      FinPulse
    </Link>
  );
}

function Nav() {
  return (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV.map(({ label, icon: Icon, href, plannedPhase }) =>
        href ? (
          <Link
            key={label}
            href={href}
            className="flex items-center gap-2 rounded-md bg-accent px-2 py-1.5 text-sm font-medium text-accent-foreground"
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        ) : (
          <span
            key={label}
            aria-disabled
            title={`Planned for phase ${plannedPhase}`}
            className="flex cursor-not-allowed items-center gap-2 rounded-md px-2 py-1.5 text-sm text-muted-foreground/70"
          >
            <Icon className="size-4" aria-hidden />
            {label}
            <span className="ml-auto text-[10px] tracking-wide uppercase">
              Phase {plannedPhase}
            </span>
          </span>
        ),
      )}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh">
      <aside className="hidden w-60 shrink-0 flex-col gap-6 border-r bg-sidebar p-4 md:flex">
        <Brand />
        <Nav />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center border-b px-4 md:hidden">
          <Brand />
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-8">{children}</main>
      </div>
    </div>
  );
}
