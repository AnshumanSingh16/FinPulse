import {
  Bot,
  Calculator,
  ClipboardCheck,
  FileText,
  FlaskConical,
  History,
  LayoutDashboard,
  UserRound,
  type LucideIcon,
} from "lucide-react";

export type PersonalSection = { href: string; label: string; icon: LucideIcon; primary?: boolean };

/** The personal-finance product's sections, in the order of a typical session. */
export const PERSONAL_SECTIONS: PersonalSection[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/afford", label: "Can I Afford This?", icon: Calculator, primary: true },
  { href: "/copilot", label: "AI Financial Copilot", icon: Bot },
  { href: "/profile", label: "Financial Profile", icon: UserRound },
  { href: "/scenarios", label: "Scenarios", icon: FlaskConical },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/actions", label: "Action Center", icon: ClipboardCheck },
  { href: "/audit", label: "Audit Trail", icon: History },
];
