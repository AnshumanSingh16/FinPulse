import {
  Activity,
  BrainCircuit,
  FileSearch,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  Siren,
  type LucideIcon,
} from "lucide-react";

export type Section = { slug: string; label: string; icon: LucideIcon };

/** Entity-scoped sections, in workflow order. */
export const SECTIONS: Section[] = [
  { slug: "", label: "Overview", icon: LayoutDashboard },
  { slug: "passport", label: "Financial Passport", icon: Gauge },
  { slug: "warnings", label: "Early Warning Center", icon: Siren },
  { slug: "health", label: "Financial Health", icon: Activity },
  { slug: "stress", label: "Stress Test", icon: FlaskConical },
  { slug: "investigation", label: "AI Investigation", icon: BrainCircuit },
  { slug: "evidence", label: "Evidence", icon: FileSearch },
];

export function sectionHref(entityId: string, slug: string, asOf?: string | null): string {
  const base = `/entities/${entityId}${slug ? `/${slug}` : ""}`;
  return asOf ? `${base}?asOf=${asOf}` : base;
}

/** The section slug of a pathname under /entities/{id}. */
export function currentSection(pathname: string): string {
  const parts = pathname.split("/").filter(Boolean);
  return parts[0] === "entities" ? (parts[2] ?? "") : "";
}
