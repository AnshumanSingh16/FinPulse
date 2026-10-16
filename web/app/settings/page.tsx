"use client";

import { Bot, Brain, ChevronRight, Database, FileText, Languages, MessageSquareX, Palette } from "lucide-react";
import Link from "next/link";
import { useContext, useState } from "react";
import { MemorySheet } from "@/components/agent";
import { AiSetupSheet } from "@/components/ai-setup";
import { DataVersion } from "@/components/data-version";
import { useToast } from "@/components/fx";
import { LangToggle, MunshiMark, ThemeToggle } from "@/components/shell";
import { cx } from "@/components/ui";
import { del } from "@/lib/api";
import { useT } from "@/lib/i18n";

function Row({ I, title, sub, right, onClick, href, danger }: { I: React.ElementType; title: string; sub?: string; right?: React.ReactNode; onClick?: () => void; href?: string; danger?: boolean }) {
  const inner = (
    <>
      <span className={cx("grid size-10 shrink-0 place-items-center rounded-2xl", danger ? "bg-bad-50 text-bad" : "bg-brand-50 text-brand")}>
        <I className="size-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className={cx("block font-semibold", danger && "text-bad")}>{title}</span>
        {sub && <span className="block text-sm text-ink-2">{sub}</span>}
      </span>
      {right ?? ((onClick || href) && <ChevronRight className="size-5 text-muted" />)}
    </>
  );
  const cls = "flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:bg-surface-2";
  if (href) return <Link href={href} className={cls}>{inner}</Link>;
  if (onClick) return <button onClick={onClick} className={cls}>{inner}</button>;
  return <div className={cls}>{inner}</div>;
}

export default function SettingsPage() {
  const { t } = useT();
  const toast = useToast();
  const { state, refresh } = useContext(DataVersion);
  const [ai, setAi] = useState(false);
  const [memory, setMemory] = useState(false);
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <MunshiMark size="lg" />
        <div>
          <h1 className="text-2xl">{t("Settings")}</h1>
          <p className="text-sm text-ink-2">{state?.business.replace(" (fictional)", "")}{state?.is_demo ? ` · ${t("demo shop")}` : ""}</p>
        </div>
      </div>

      <div className="card divide-y divide-line overflow-hidden p-0">
        <Row I={Database} title={t("Your books")} sub={state?.is_demo ? t("Using the demo shop — add your bank statement or start fresh") : t("Uploads, bank balance, GST settings")} href="/data/" />
        <Row I={Bot} title={t("Munshi's brain")} sub={state?.ai.enabled ? t("AI on — {provider}", { provider: state.ai.provider_label }) : t("Built-in answers (offline). Add a free Gemini key to understand anything.")} onClick={() => setAi(true)} />
        <Row I={Brain} title={t("What Munshi remembers")} sub={t("Preferences you told it, like who not to remind")} onClick={() => setMemory(true)} />
        <Row I={FileText} title={t("Monthly report for your CA")} sub={t("Profit, costs, GST estimate — print or save as PDF")} href="/reports/" />
      </div>

      <div className="card divide-y divide-line overflow-hidden p-0">
        <Row I={Languages} title={t("Language")} right={<LangToggle />} />
        <Row I={Palette} title={t("Theme")} right={<ThemeToggle />} />
      </div>

      <div className="card overflow-hidden p-0">
        <Row I={MessageSquareX} danger title={t("Clear the chat")} sub={t("Removes the conversation only — your khata entries stay.")}
          onClick={async () => {
            if (!window.confirm(t("Clear the whole chat? Your khata entries stay."))) return;
            await del("/api/chat");
            refresh();
            toast.show({ text: t("Chat cleared") });
          }} />
      </div>

      <p className="text-center text-xs text-muted">{t("Munshi prepares, you approve. It never pays, sends or files anything by itself. Not financial advice.")}</p>
      <AiSetupSheet open={ai} onClose={() => setAi(false)} />
      <MemorySheet open={memory} onClose={() => setMemory(false)} />
    </div>
  );
}
