"use client";

import { Check, Download, FileText, Lock, PiggyBank, PlugZap } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import type { ActionPlan } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { usePersonal } from "./provider";
import { ApprovalBadge, ConfirmDialog, Notice, inputClass } from "./ui";

const CATEGORY: Record<string, string> = {
  savings: "Savings",
  documents: "Documents",
  research: "Research",
  protection: "Protection",
  application: "Application",
};

function exportText(plan: ActionPlan): string {
  const lines = [`# ${plan.title}`, `Status: ${plan.status}`, ""];
  for (const i of plan.items)
    lines.push(
      `- [${i.done ? "x" : " "}] ${i.title}${i.requiresIntegration ? " (do this directly with the provider)" : ""}\n  ${i.detail}`,
    );
  if (plan.documentsNeeded.length)
    lines.push("", "## Documents", ...plan.documentsNeeded.map((d) => `- ${d}`));
  if (plan.draftAnswers.length)
    lines.push(
      "",
      "## Draft application answers (review before use)",
      ...plan.draftAnswers.map((d) => `- ${d.question}: ${d.answer} (${d.source})`),
    );
  lines.push("", "Prepared by FinPulse. Decision support, not financial advice.");
  return lines.join("\n");
}

export function ActionPlanCard({ plan, compact = false }: { plan: ActionPlan; compact?: boolean }) {
  const { setState } = usePersonal();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState<"approve" | "reject" | "complete" | null>(null);

  async function act(body: Record<string, unknown>, key: string) {
    setBusy(key);
    setError(null);
    try {
      setState(await api.action(plan.id, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  function download() {
    const blob = new Blob([exportText(plan)], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `finpulse-next-steps-${plan.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const canTick = plan.status === "approved";
  const openItems = plan.items.filter((i) => !i.done && !i.requiresIntegration).length;

  const trackable = plan.items.filter((i) => !i.requiresIntegration);
  const done = trackable.filter((i) => i.done).length;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <ApprovalBadge status={plan.status} />
        <span className="text-[12.5px] text-ink-500">
          Prepared by the Action Agent ·{" "}
          {new Date(plan.createdAt).toLocaleString("en-IN", {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        {trackable.length ? (
          <span className="ml-auto flex items-center gap-2 text-[12.5px] text-ink-500">
            <span
              className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-sunken"
              role="progressbar"
              aria-label="Steps done"
              aria-valuemin={0}
              aria-valuemax={trackable.length}
              aria-valuenow={done}
            >
              <span
                className="block h-full rounded-full bg-brand-600 transition-[width] duration-300"
                style={{ width: `${(done / trackable.length) * 100}%` }}
              />
            </span>
            <span className="tabular">
              {done}/{trackable.length} done
            </span>
          </span>
        ) : null}
      </div>

      {plan.savingsPlan ? (
        <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface-sunken/60 p-4">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-ink-900">
            <PiggyBank className="size-4 text-brand-600" aria-hidden /> Savings plan
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              ["Each month", formatINR(plan.savingsPlan.monthlySaving)],
              ["For", `${plan.savingsPlan.months} months`],
              ["Adds", formatINR(plan.savingsPlan.targetAmount)],
            ].map(([k, v]) => (
              <div key={k} className="flex flex-col">
                <span className="text-[12px] text-ink-500">{k}</span>
                <span className="tabular font-display text-[16px] font-bold whitespace-nowrap sm:text-[18px]">
                  {v}
                </span>
              </div>
            ))}
          </div>
          <p className="text-[13px] text-pretty text-ink-500">{plan.savingsPlan.rationale}</p>
        </div>
      ) : null}

      <ul className="flex flex-col">
        {plan.items.map((item) => (
          <li key={item.id} className="flex gap-3 border-b border-line py-3 last:border-0">
            <button
              type="button"
              disabled={!canTick || item.requiresIntegration || busy !== null}
              onClick={() => act({ action: "toggle_item", itemId: item.id }, item.id)}
              aria-label={
                item.done ? `Mark "${item.title}" as not done` : `Mark "${item.title}" as done`
              }
              title={
                !canTick && !item.requiresIntegration
                  ? "Approve the plan to tick steps off"
                  : undefined
              }
              className={cn(
                "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors disabled:cursor-not-allowed",
                item.done
                  ? "border-brand-600 bg-brand-600 text-white"
                  : "border-line-strong bg-surface hover:border-brand-600",
                !canTick && "opacity-50",
              )}
            >
              {item.requiresIntegration ? (
                <Lock className="size-3 text-ink-400" />
              ) : item.done ? (
                <Check className="size-3.5" />
              ) : null}
            </button>
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "text-[14px] font-medium text-ink-900",
                    item.done && "text-ink-400 line-through",
                  )}
                >
                  {item.title}
                </span>
                <span className="rounded-md bg-surface-sunken px-1.5 py-0.5 text-[11px] font-medium text-ink-500">
                  {CATEGORY[item.category]}
                </span>
                {item.requiresIntegration ? (
                  <span className="inline-flex items-center gap-1 rounded-md bg-caution-50 px-1.5 py-0.5 text-[11px] font-medium text-caution-text">
                    <PlugZap className="size-3" aria-hidden /> Do this with the provider
                  </span>
                ) : null}
              </div>
              {item.detail ? (
                <span className="text-[13px] text-pretty text-ink-500">{item.detail}</span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      {!compact && plan.documentsNeeded.length ? (
        <div className="flex flex-col gap-2">
          <h4 className="text-[14px] font-semibold">Documents lenders typically ask for</h4>
          <ul className="grid gap-1.5 text-[13px] text-ink-700 sm:grid-cols-2">
            {plan.documentsNeeded.map((d) => (
              <li key={d} className="flex gap-2">
                <FileText className="mt-0.5 size-3.5 shrink-0 text-ink-400" aria-hidden /> {d}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!compact && plan.draftAnswers.length ? (
        <div className="flex flex-col gap-2">
          <h4 className="text-[14px] font-semibold">Draft application answers</h4>
          <p className="text-[13px] text-ink-500">
            Drafted from your profile for you to copy into a lender&apos;s form. FinPulse does not
            submit anything.
          </p>
          <dl className="overflow-hidden rounded-xl border border-line text-[13px]">
            {plan.draftAnswers.map((d) => (
              <div
                key={d.question}
                className="grid gap-x-4 gap-y-0.5 border-b border-line px-3 py-2 last:border-0 sm:grid-cols-[1fr_auto_auto]"
              >
                <dt className="text-ink-500">{d.question}</dt>
                <dd className="tabular font-semibold text-ink-900">{d.answer}</dd>
                <dd className="text-[12px] text-ink-400">{d.source}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="flex flex-col gap-3 border-t border-line pt-4">
        {plan.status === "awaiting_review" ? (
          <div className="flex flex-col gap-3 rounded-xl bg-caution-50 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[13px] text-pretty text-ink-700">
              <span className="font-semibold text-ink-900">Waiting for you.</span> Approving lets
              you track these steps here. It does not contact any lender or move money.
            </p>
            <div className="flex shrink-0 gap-2">
              <Button onClick={() => setConfirm("approve")} disabled={busy !== null}>
                Approve steps
              </Button>
              <Button
                variant="outline"
                onClick={() => setConfirm("reject")}
                disabled={busy !== null}
              >
                Not now
              </Button>
            </div>
          </div>
        ) : null}
        {plan.status === "approved" ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={() => setConfirm("complete")}
              disabled={busy !== null || openItems > 0}
            >
              Mark all done
            </Button>
            <span className="text-[13px] text-ink-500">
              {openItems
                ? `${openItems} step(s) still to tick off`
                : "Every trackable step is done"}
            </span>
          </div>
        ) : null}
        {plan.status === "rejected" ? (
          <Button
            variant="outline"
            className="w-fit"
            onClick={() => act({ action: "reopen" }, "reopen")}
            disabled={busy !== null}
          >
            Reopen for review
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" className="w-fit" onClick={download}>
          <Download /> Download checklist (.md)
        </Button>
      </div>
      <ConfirmDialog
        open={confirm === "approve"}
        title="Approve these next steps?"
        confirmLabel="Approve"
        busy={busy === "approve"}
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          await act({ action: "approve" }, "approve");
          setConfirm(null);
        }}
      >
        You&apos;ll be able to tick steps off as you do them. FinPulse won&apos;t contact lenders,
        submit applications or move money — steps marked “do it with the provider” stay with you.
      </ConfirmDialog>
      <ConfirmDialog
        open={confirm === "reject"}
        title="Set these steps aside?"
        confirmLabel="Set aside"
        busy={busy === "reject"}
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          await act({ action: "reject", note: note || undefined }, "reject");
          setConfirm(null);
        }}
      >
        <span className="mb-3 block">You can reopen them later from Next steps.</span>
        <label className="flex flex-col gap-1.5 text-ink-900">
          <span className="text-sm font-medium">Why? (optional)</span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={300}
            placeholder="e.g. waiting for a better rate"
            className={inputClass}
          />
        </label>
      </ConfirmDialog>
      <ConfirmDialog
        open={confirm === "complete"}
        title="Mark this plan as done?"
        confirmLabel="Mark done"
        busy={busy === "complete"}
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          await act({ action: "complete" }, "complete");
          setConfirm(null);
        }}
      >
        Steps that need a bank or lender are not done by FinPulse; make sure you&apos;ve handled
        them directly.
      </ConfirmDialog>
    </div>
  );
}
