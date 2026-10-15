"use client";

import { Bot, Brain, MessageCircleQuestion, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { get } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { AiStatus } from "@/lib/types";
import { AgentAnswer, type AgentResult, applyEvent, emptyLive, type Live, LiveCard, MemorySheet, streamAgent } from "./agent";
import { DataVersion } from "./data-version";
import { Button, cx } from "./ui";

interface AgentState {
  checkup: (AgentResult & { day: string; ran_at: string }) | null;
  stale: boolean;
  pending: number;
  memory: { id: number; text: string }[];
  ai: AiStatus;
}

/** Home's "Your agent" panel: the agent runs its own daily check-up (no question needed) and leaves a briefing with actions to approve. */
export function AgentInbox() {
  const { t, lang } = useT();
  const { state: app } = useContext(DataVersion);
  const [s, setS] = useState<AgentState | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [memory, setMemory] = useState(false);
  const started = useRef<string | null>(null);

  const run = useCallback(async () => {
    setErr(null);
    setLive(emptyLive());
    try {
      const c = await streamAgent<AgentState["checkup"]>("/api/agent/checkup/stream", {}, (e) => setLive((l) => (l ? applyEvent(l, e) : l)), lang, "/api/agent/checkup");
      setS((x) => (x ? { ...x, checkup: c, stale: false } : x));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLive(null);
    }
  }, [lang]);

  useEffect(() => {
    let alive = true;
    get<AgentState>("/api/agent").then((st) => {
      if (!alive) return;
      setS(st);
      const key = `${app?.source}:${lang}`;
      if (st.stale && started.current !== key) {
        started.current = key; // the agent does its check-up by itself, once a day
        run();
      }
    }).catch((e) => setErr(String(e)));
    return () => {
      alive = false;
    };
  }, [app?.source, lang, run]);

  const c = s?.checkup;
  const time = c?.ran_at ? new Date(c.ran_at).toLocaleTimeString(lang === "hi" ? "hi-IN" : "en-IN", { hour: "numeric", minute: "2-digit" }) : null;
  const pending = c?.actions.filter((a) => a.state === "pending").length ?? 0;

  return (
    <section className="rise space-y-3" aria-label={t("Your agent")}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="grad-hero relative grid size-11 place-items-center rounded-2xl text-[#ffd27a] shadow-md shadow-black/10">
          <Bot className="size-6" aria-hidden />
          {live && <span className="absolute -top-0.5 -right-0.5 size-3 animate-ping rounded-full bg-[#ffd27a]" />}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-bold tracking-tight">{t("Your agent")}</h2>
          <p className="text-xs text-muted">
            {live
              ? t("Doing today's check-up…")
              : c
                ? `${t("Checked your books today at {time}", { time: time ?? "" })} · ${c.mode === "ai" ? t("AI agent") : t("Built-in answers")}${pending ? " · " + t("{n} waiting for you", { n: pending }) : ""}`
                : t("Checks your books every day and prepares what needs doing.")}
          </p>
        </div>
        <div className="flex w-full items-center gap-2 sm:w-auto">
          <Button size="sm" variant="secondary" onClick={() => setMemory(true)} aria-label={t("Memory")}>
            <Brain className="size-4" /> <span className="hidden sm:inline">{t("Memory")}{s?.memory.length ? ` (${s.memory.length})` : ""}</span>
          </Button>
          <Button size="sm" variant="secondary" onClick={run} disabled={!!live} aria-label={t("Run check-up again")}>
            <RefreshCw className={cx("size-4", live && "animate-spin")} /> <span className="hidden sm:inline">{t("Run again")}</span>
          </Button>
          <Link href="/ask/" className="ml-auto sm:ml-0">
            <Button size="sm">
              <MessageCircleQuestion className="size-4" /> {t("Give it a task")}
            </Button>
          </Link>
        </div>
      </div>
      {live && <LiveCard live={live} title={live.mode === "ai" ? t("The AI agent is doing today's check-up…") : t("Doing today's check-up…")} />}
      {err && !live && <p className="rounded-2xl bg-bad-50 p-3 text-sm text-bad">{err}</p>}
      {!live && c && <AgentAnswer a={c} />}
      {!live && !c && !err && (
        <div className="card flex items-center gap-3 p-4 text-sm text-ink-2">
          <Sparkles className="size-5 text-brand" /> {t("Getting ready…")}
        </div>
      )}
      <MemorySheet open={memory} onClose={() => setMemory(false)} />
    </section>
  );
}
