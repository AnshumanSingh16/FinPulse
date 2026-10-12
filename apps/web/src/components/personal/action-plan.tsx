"use client";

import { Check, FileText, Lock, PlugZap } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import type { ActionPlan } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { usePersonal } from "./provider";
import { ApprovalBadge, Notice } from "./ui";

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

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <ApprovalBadge status={plan.status} />
        <span className="text-xs text-muted-foreground">
          Prepared by the Action Agent · {new Date(plan.createdAt).toLocaleString("en-IN")}
        </span>
      </div>

      {plan.savingsPlan ? (
        <div className="rounded-lg border bg-background/40 p-3 text-sm">
          <div className="font-medium">Savings plan</div>
          <div className="text-muted-foreground">
            Save{" "}
            <span className="tabular font-medium text-foreground">
              {formatINR(plan.savingsPlan.monthlySaving)}
            </span>{" "}
            a month for{" "}
            <span className="tabular font-medium text-foreground">
              {plan.savingsPlan.months} months
            </span>{" "}
            to add{" "}
            <span className="tabular font-medium text-foreground">
              {formatINR(plan.savingsPlan.targetAmount)}
            </span>
            . {plan.savingsPlan.rationale}
          </div>
        </div>
      ) : null}

      <ul className="flex flex-col gap-1.5">
        {plan.items.map((item) => (
          <li key={item.id} className="flex gap-3 rounded-lg border bg-background/30 p-3">
            <button
              type="button"
              disabled={!canTick || item.requiresIntegration || busy !== null}
              onClick={() => act({ action: "toggle_item", itemId: item.id }, item.id)}
              aria-label={
                item.done ? `Mark "${item.title}" as not done` : `Mark "${item.title}" as done`
              }
              className={cn(
                "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded border transition disabled:cursor-not-allowed",
                item.done ? "border-primary bg-primary text-primary-foreground" : "bg-background",
                !canTick && "opacity-50",
              )}
            >
              {item.requiresIntegration ? (
                <Lock className="size-3 text-muted-foreground" />
              ) : item.done ? (
                <Check className="size-3.5" />
              ) : null}
            </button>
            <div className="flex min-w-0 flex-col gap-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "text-sm font-medium",
                    item.done && "text-muted-foreground line-through",
                  )}
                >
                  {item.title}
                </span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground uppercase">
                  {CATEGORY[item.category]}
                </span>
                {item.requiresIntegration ? (
                  <span className="inline-flex items-center gap-1 rounded bg-status-warning/10 px-1.5 py-0.5 text-[10px] text-status-warning">
                    <PlugZap className="size-3" /> No integration — not executable here
                  </span>
                ) : null}
              </div>
              {item.detail ? (
                <span className="text-xs text-pretty text-muted-foreground">{item.detail}</span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      {!compact && plan.documentsNeeded.length ? (
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-medium">Documents lenders typically ask for</div>
          <ul className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
            {plan.documentsNeeded.map((d) => (
              <li key={d} className="flex gap-1.5">
                <FileText className="mt-0.5 size-3 shrink-0" /> {d}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!compact && plan.draftAnswers.length ? (
        <div className="flex flex-col gap-1.5">
          <div className="text-sm font-medium">Draft application answers</div>
          <p className="text-xs text-muted-foreground">
            Drafted from your profile for you to copy into a lender&apos;s form. FinPulse does not
            submit anything.
          </p>
          <dl className="grid gap-x-4 gap-y-1 rounded-lg border p-3 text-xs sm:grid-cols-[auto_1fr_auto]">
            {plan.draftAnswers.map((d) => (
              <div key={d.question} className="contents">
                <dt className="text-muted-foreground">{d.question}</dt>
                <dd className="tabular font-medium">{d.answer}</dd>
                <dd className="text-muted-foreground">{d.source}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="flex flex-col gap-2 border-t pt-3">
        {plan.status === "awaiting_review" ? (
          <>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={300}
              placeholder="Optional note (e.g. why you are rejecting)"
              className="h-9 rounded-md border bg-background/60 px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => act({ action: "approve", note: note || undefined }, "approve")}
                disabled={busy !== null}
              >
                {busy === "approve" ? "Approving…" : "Approve checklist"}
              </Button>
              <Button
                variant="outline"
                onClick={() => act({ action: "reject", note: note || undefined }, "reject")}
                disabled={busy !== null}
              >
                {busy === "reject" ? "Rejecting…" : "Reject"}
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Approving lets you track these steps here. It does not contact any lender or move
              money.
            </p>
          </>
        ) : null}
        {plan.status === "approved" ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={() => act({ action: "complete" }, "complete")}
              disabled={busy !== null || openItems > 0}
            >
              Mark plan completed
            </Button>
            <span className="text-xs text-muted-foreground">
              {openItems ? `${openItems} item(s) still open` : "All trackable items are done"}
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
          Download checklist (.md)
        </Button>
      </div>
    </div>
  );
}
