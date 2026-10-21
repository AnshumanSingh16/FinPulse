"use client";

import {
  Banknote, Bot, CheckCheck, Clock, Dices, HandCoins, Landmark, Loader2, PauseCircle, Route, ShieldCheck, Sparkles, Telescope,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { streamAgent } from "@/components/agent";
import { useToast } from "@/components/fx";
import { Button, cx, Pill, Sheet } from "@/components/ui";
import { post } from "@/lib/api";
import { useT } from "@/lib/i18n";

export const CREW: Record<string, { I: React.ElementType; grad: string }> = {
  forecaster: { I: Telescope, grad: "grad-ocean" },
  risk: { I: Dices, grad: "grad-berry" },
  collections: { I: HandCoins, grad: "grad-mint" },
  payables: { I: Clock, grad: "grad-ocean" },
  spending: { I: PauseCircle, grad: "grad-sunset" },
  tax: { I: Landmark, grad: "grad-violet" },
  planner: { I: Route, grad: "grad-night" },
  financing: { I: Banknote, grad: "grad-sunset" },
  auditor: { I: ShieldCheck, grad: "grad-mint" },
  cfo: { I: Sparkles, grad: "grad-hero" },
};

interface Row {
  agent: string;
  name: string;
  doing: string;
  text?: string;
  tone?: string;
  done: boolean;
}
interface Final {
  status: string;
  message?: string;
  brief?: string;
  mode?: "ai" | "rule-based";
  verified?: boolean;
  warnings?: string[];
  suggested?: string[];
}

/** "Fix it for me": the crew of agents works through the books live, then FinPilot sums up and offers the plan. */
export function CrewSheet({ open, onClose, onApproved, canApprove }: { open: boolean; onClose: () => void; onApproved: () => void; canApprove: boolean }) {
  const { t, lang } = useT();
  const toast = useToast();
  const [rows, setRows] = useState<Row[]>([]);
  const [final, setFinal] = useState<Final | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!open) {
      started.current = false;
      return;
    }
    if (started.current) return;
    started.current = true;
    setRows([]);
    setFinal(null);
    setErr(null);
    streamAgent<Final>("/api/crew/stream", {}, (e) => {
      if (e.type !== "agent") return;
      const agent = String(e.agent);
      if (e.phase === "start") {
        setRows((r) => (r.some((x) => x.agent === agent) ? r : [...r, { agent, name: String(e.name), doing: String(e.doing), done: false }]));
      } else if (e.phase === "done") {
        setRows((r) => r.map((x) => (x.agent === agent ? { ...x, text: String(e.text), tone: String(e.tone), done: true } : x)));
      }
    }, lang)
      .then((f) => {
        setRows((r) => r.map((x) => ({ ...x, done: true })));
        setFinal(f);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [open, lang]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [rows, final]);

  const approve = async () => {
    setBusy(true);
    try {
      const r = await post<{ approved: string[] }>("/api/autopilot/approve-suggested", {});
      toast.show({ text: t("Approved {n} moves", { n: r.approved.length }), tone: "good" });
      onApproved();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("Your agents at work")}>
      <ol className="space-y-3" aria-live="polite">
        {rows.map((r) => {
          const C = CREW[r.agent] ?? { I: Bot, grad: "grad-night" };
          return (
            <li key={r.agent} className="rise flex gap-3">
              <span className={cx("grid size-9 shrink-0 place-items-center rounded-xl", C.grad)}><C.I className="size-4.5" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold tracking-wide text-muted uppercase">{r.name}</p>
                {r.done && r.text ? (
                  <p className="text-sm leading-relaxed text-ink">
                    {r.tone && r.tone !== "info" && <span className={cx("mr-1 inline-block size-2 rounded-full align-middle", r.tone === "good" ? "bg-good" : r.tone === "bad" ? "bg-bad" : "bg-caution")} />}
                    {r.text}
                  </p>
                ) : (
                  <p className="flex items-center gap-2 text-sm text-ink-2"><Loader2 className="size-4 animate-spin" /> {r.doing}</p>
                )}
              </div>
            </li>
          );
        })}
        {rows.length === 0 && !err && <li className="flex items-center gap-2 text-sm text-ink-2"><Loader2 className="size-4 animate-spin" /> {t("Waking up your agents…")}</li>}
      </ol>
      {err && <p className="mt-4 rounded-2xl bg-bad-50 p-3 text-sm text-bad">{err}</p>}
      {final && final.status === "ok" && (
        <div className="rise mt-5 rounded-3xl border border-brand/30 bg-brand-50 p-4">
          <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-brand uppercase"><Sparkles className="size-4" /> FinPilot</p>
          <p className="mt-1 leading-relaxed text-ink">{final.brief}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Pill tone="good"><ShieldCheck className="size-3.5" /> {t("Every figure checked against your records")}</Pill>
            <Pill>{final.mode === "ai" ? t("Written by AI") : t("Built-in answer (no AI)")}</Pill>
          </div>
          {canApprove && (final.suggested ?? []).length > 0 && (
            <Button className="mt-4 w-full" onClick={approve} disabled={busy}><CheckCheck className="size-4" /> {t("Approve the plan")}</Button>
          )}
        </div>
      )}
      {final && final.status !== "ok" && <p className="mt-4 text-sm text-ink-2">{final.message}</p>}
      <div ref={end} />
    </Sheet>
  );
}
