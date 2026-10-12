import {
  Bot,
  Calculator,
  ClipboardCheck,
  FileText,
  FlaskConical,
  History,
  House,
  UserRound,
  type LucideIcon,
} from "lucide-react";

export type PersonalSection = {
  href: string;
  label: string;
  short: string;
  icon: LucideIcon;
  /** Shown in the mobile bottom bar (the rest live under "More"). */
  tab?: boolean;
};

/** The personal-finance product's sections, in the order of a typical session. */
export const PERSONAL_SECTIONS: PersonalSection[] = [
  { href: "/", label: "Home", short: "Home", icon: House, tab: true },
  { href: "/afford", label: "Can I afford this?", short: "Afford", icon: Calculator, tab: true },
  { href: "/copilot", label: "Ask FinPulse", short: "Ask", icon: Bot, tab: true },
  { href: "/actions", label: "Next steps", short: "Steps", icon: ClipboardCheck, tab: true },
  { href: "/scenarios", label: "What-if scenarios", short: "Scenarios", icon: FlaskConical },
  { href: "/profile", label: "My finances", short: "Profile", icon: UserRound },
  { href: "/documents", label: "Documents", short: "Docs", icon: FileText },
  { href: "/audit", label: "Activity log", short: "Activity", icon: History },
];

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
