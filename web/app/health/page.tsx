"use client";

import { ArrowRight, Banknote, BarChart3, HandCoins, ReceiptText, TrendingUp } from "lucide-react";
import Link from "next/link";
import { ScoreHistory } from "@/components/charts";
import { EvidenceButton } from "@/components/evidence";
import { Gauge } from "@/components/gauge";
import { Card, cx, Loading, Pill, SectionTitle, toneBg, toneText } from "@/components/ui";
import { useApi } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Evidence, Tone } from "@/lib/types";

interface Comp {
  key: string;
  label: string;
  text: string;
  tip: string;
  href: string;
  points: number;
  max: number;
  status: Tone | "unknown";
}
interface Health {
  status: string;
  score: number;
  grade: string;
  change: number | null;
  components: Comp[];
  history: { label: string; score: number }[];
  evidence: Evidence;
}
const ICON: Record<string, React.ElementType> = { cash: Banknote, profit: BarChart3, collections: HandCoins, bills: ReceiptText, momentum: TrendingUp };

export default function HealthPage() {
  const { t } = useT();
  const { data } = useApi<Health>("/api/health");
  if (!data) return <Loading />;
  if (data.status !== "ok") return <Card className="text-ink-2">Add a few weeks of transactions to see your health score.</Card>;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">{t("Health score")}</h1>
      <section className="grad-hero flex flex-wrap items-center gap-6 rounded-[1.75rem] p-6 shadow-xl shadow-violet-300/40">
        <div className="rounded-3xl bg-white/95 p-3 text-ink">
          <Gauge score={data.score} size={220} />
        </div>
        <div>
          <p className="text-white/80">Your business health</p>
          <p className="text-4xl font-bold">{data.grade}</p>
          {data.change != null && (
            <p className="mt-1 text-white/90">
              {data.change > 0 ? "▲ up" : data.change < 0 ? "▼ down" : "No change"} {data.change ? Math.abs(data.change) : ""} points since last month
            </p>
          )}
          <p className="mt-3 max-w-md text-sm text-white/80">Five simple checks, 20 points each. Fix the weakest one first.</p>
        </div>
      </section>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {[...data.components].sort((a, b) => a.points - b.points).map((c) => {
          const I = ICON[c.key] ?? BarChart3;
          const tone: Tone = c.status === "unknown" ? "neutral" : (c.status as Tone);
          return (
            <Card key={c.key} className="flex flex-col gap-3">
              <div className="flex items-center gap-3">
                <span className={cx("grid size-11 place-items-center rounded-2xl", toneBg[tone])}>
                  <I className={cx("size-5", toneText[tone])} />
                </span>
                <div className="flex-1">
                  <p className="font-semibold">{c.label}</p>
                  <p className="text-xs text-ink-2">{c.text}</p>
                </div>
                <span className="num text-lg font-bold">
                  {Math.round(c.points)}
                  <span className="text-xs font-medium text-muted">/20</span>
                </span>
              </div>
              <div className="h-2 rounded-full bg-canvas">
                <div className={cx("h-2 rounded-full", tone === "good" ? "bg-good" : tone === "caution" ? "bg-[#f59e0b]" : tone === "bad" ? "bg-bad" : "bg-muted")} style={{ width: `${(c.points / 20) * 100}%` }} />
              </div>
              <p className="text-sm text-ink-2">{c.tip}</p>
              {c.status !== "good" && (
                <Link href={c.href} className="mt-auto inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
                  Fix this <ArrowRight className="size-4" />
                </Link>
              )}
              {c.status === "good" && <Pill tone="good" className="mt-auto w-fit">✓ {c.label}</Pill>}
            </Card>
          );
        })}
      </div>

      {data.history.length > 1 && (
        <Card>
          <SectionTitle>Score by month</SectionTitle>
          <ScoreHistory data={data.history} />
        </Card>
      )}
      <EvidenceButton evidence={data.evidence} />
    </div>
  );
}
