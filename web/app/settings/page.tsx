"use client";

import { Bot, Brain, Briefcase, ChevronRight, Database, Download, FileText, IndianRupee, Languages, MessageSquareX, Palette, Target } from "lucide-react";
import Link from "next/link";
import { useContext, useEffect, useState } from "react";
import { MemorySheet } from "@/components/agent";
import { AiSetupSheet } from "@/components/ai-setup";
import { DataVersion } from "@/components/data-version";
import { useToast } from "@/components/fx";
import { BrandMark, LangToggle, ThemeToggle } from "@/components/shell";
import { cx } from "@/components/ui";
import { API, del, get, post } from "@/lib/api";
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
        <BrandMark size="lg" />
        <div>
          <h1 className="text-2xl">{t("Settings")}</h1>
          <p className="text-sm text-ink-2">{state?.business.replace(" (fictional)", "")}{state?.type_info ? ` · ${t(state.type_info.label)}` : ""}{state?.is_demo ? ` · ${t("demo")}` : ""}</p>
        </div>
      </div>

      <div className="card divide-y divide-line overflow-hidden p-0">
        <Row I={Database} title={t("Your books")} sub={state?.is_demo ? t("You're trying a demo — add your bank statement or start fresh") : t("Uploads, bank balance, GST settings")} href="/data/" />
        {state && !state.is_demo && (
          <Row I={Briefcase} title={t("Type of business")} sub={t("FinPilot adapts its words and checks to it")}
            right={
              <select value={state.business_type} aria-label={t("Type of business")}
                onChange={async (e) => { await post("/api/settings", { business_type: e.target.value }); refresh(); }}
                className="h-9 max-w-44 rounded-full border border-line bg-surface px-3 text-sm">
                <option value="">{t("Choose…")}</option>
                {state.types.map((x) => <option key={x.key} value={x.key}>{t(x.label)}</option>)}
              </select>
            } />
        )}
        <Row I={Bot} title={t("FinPilot's brain")} sub={state?.ai.enabled ? t("AI on — {provider}", { provider: state.ai.provider_label }) : t("Built-in answers (offline). Add a free Gemini key to understand anything.")} onClick={() => setAi(true)} />
        <Row I={Brain} title={t("What FinPilot remembers")} sub={t("Preferences you told it, like who not to remind")} onClick={() => setMemory(true)} />
        <UpiRow />
        <Row I={Download} title={t("Download the audit log")} sub={t("Every agent action and every decision you made, as a spreadsheet for your accountant")}
          onClick={() => { window.location.href = `${API}/api/audit.csv`; }} />
        <Row I={Target} title={t("Track record")} sub={t("How accurate FinPilot would have been on your past weeks")} href="/proof/" />
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

      <p className="text-center text-xs text-muted">{t("FinPilot prepares, you approve. It never pays, sends or files anything by itself. Not financial advice.")}</p>
      <AiSetupSheet open={ai} onClose={() => setAi(false)} />
      <MemorySheet open={memory} onClose={() => setMemory(false)} />
    </div>
  );
}

function UpiRow() {
  const { t } = useT();
  const toast = useToast();
  const [v, setV] = useState("");
  const [saved, setSaved] = useState("");
  useEffect(() => {
    get<{ upi_id?: string }>("/api/settings").then((x) => { setV(x.upi_id ?? ""); setSaved(x.upi_id ?? ""); }).catch(() => {});
  }, []);
  const save = async () => {
    try {
      await post("/api/settings", { upi_id: v.trim() });
      setSaved(v.trim());
      toast.show({ text: t("UPI ID saved — reminders now include a pay link"), tone: "good" });
    } catch (e) {
      toast.show({ text: e instanceof Error ? e.message : String(e), tone: "bad" });
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3.5">
      <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-brand-50 text-brand"><IndianRupee className="size-5" /></span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold">{t("Your UPI ID")}</span>
        <span className="block text-sm text-ink-2">{t("Added to every payment reminder as a one-tap pay link")}</span>
      </span>
      <input value={v} onChange={(e) => setV(e.target.value)} placeholder="yourshop@okhdfc" aria-label={t("Your UPI ID")} className="h-9 w-44 rounded-full border border-line bg-surface px-3 text-sm" />
      <button onClick={save} disabled={v.trim() === saved} className="h-9 rounded-full bg-ink px-3 text-sm font-semibold text-canvas disabled:opacity-30">{t("Save")}</button>
    </div>
  );
}
