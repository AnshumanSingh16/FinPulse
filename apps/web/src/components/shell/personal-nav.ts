import {
  Bot,
  Calculator,
  ClipboardCheck,
  FileText,
  FlaskConical,
  History,
  House,
  Route,
  Scale,
  UserRound,
  type LucideIcon,
} from "lucide-react";

export type PersonalSection = {
  href: string;
  label: string;
  short: string;
  icon: LucideIcon;
  group: "Plan" | "Assistant" | "Track" | "Your data";
  /** Shown in the mobile bottom bar (the rest live under "More"). */
  tab?: boolean;
};

/** Navigation, grouped by what people come to do. */
export const PERSONAL_SECTIONS: PersonalSection[] = [
  { href: "/", label: "Home", short: "Home", icon: House, group: "Plan", tab: true },
  { href: "/plan", label: "My plan", short: "Plan", icon: Route, group: "Plan", tab: true },
  {
    href: "/afford",
    label: "Can I afford this?",
    short: "Afford",
    icon: Calculator,
    group: "Plan",
    tab: true,
  },
  { href: "/decide", label: "Rent, buy or prepay?", short: "Decide", icon: Scale, group: "Plan" },
  {
    href: "/scenarios",
    label: "What-if scenarios",
    short: "What-if",
    icon: FlaskConical,
    group: "Plan",
  },
  {
    href: "/copilot",
    label: "Ask FinPulse",
    short: "Ask",
    icon: Bot,
    group: "Assistant",
    tab: true,
  },
  {
    href: "/actions",
    label: "Next steps",
    short: "Steps",
    icon: ClipboardCheck,
    group: "Track",
  },
  { href: "/audit", label: "Activity log", short: "Activity", icon: History, group: "Track" },
  {
    href: "/profile",
    label: "My finances",
    short: "Finances",
    icon: UserRound,
    group: "Your data",
  },
  { href: "/documents", label: "Documents", short: "Docs", icon: FileText, group: "Your data" },
];

export const NAV_GROUPS = ["Plan", "Assistant", "Track", "Your data"] as const;

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}
