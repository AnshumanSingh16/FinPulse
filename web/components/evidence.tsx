"use client";

import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { get } from "@/lib/api";
import { dayFull, inr } from "@/lib/format";
import type { Evidence, Rec } from "@/lib/types";
import { Button, cx, Sheet } from "./ui";

export function EvidenceButton({ evidence, label = "How do we know?", className }: { evidence?: Evidence | null; label?: string; className?: string }) {
  const [open, setOpen] = useState(false);
  if (!evidence) return null;
  return (
    <>
      <button onClick={() => setOpen(true)} className={cx("inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline", className)}>
        <ShieldCheck className="size-4" aria-hidden /> {label}
      </button>
      <EvidenceSheet evidence={evidence} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

export function EvidenceSheet({ evidence, open, onClose }: { evidence: Evidence; open: boolean; onClose: () => void }) {
  const [records, setRecords] = useState<Rec[] | null>(null);
  const [loading, setLoading] = useState(false);
  const loadRecords = () => {
    setLoading(true);
    get<Rec[]>(`/api/records?ids=${encodeURIComponent(evidence.record_ids.slice(0, 200).join(","))}`)
      .then(setRecords)
      .finally(() => setLoading(false));
  };
  return (
    <Sheet open={open} onClose={onClose} title={evidence.title} wide>
      <div className="space-y-5 text-[0.95rem] leading-relaxed">
        <p className="rounded-2xl bg-brand-50 p-4 text-ink">
          Every figure is calculated by FinPilot&apos;s tested formulas directly from your records — not estimated by AI.
        </p>
        <section>
          <h4 className="mb-1 text-sm font-semibold text-ink-2 uppercase tracking-wide">How it&apos;s calculated</h4>
          <p>{evidence.method}</p>
        </section>
        {evidence.assumptions.length > 0 && (
          <section>
            <h4 className="mb-1 text-sm font-semibold text-ink-2 uppercase tracking-wide">What we assumed</h4>
            <ul className="list-disc space-y-1 pl-5">
              {evidence.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </section>
        )}
        {evidence.limitations.length > 0 && (
          <section>
            <h4 className="mb-1 text-sm font-semibold text-ink-2 uppercase tracking-wide">Good to know</h4>
            <ul className="list-disc space-y-1 pl-5">
              {evidence.limitations.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </section>
        )}
        {evidence.record_count > 0 && (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-ink-2 uppercase tracking-wide">Records used ({evidence.record_count})</h4>
            {!records ? (
              <Button variant="secondary" size="sm" onClick={loadRecords} disabled={loading}>
                {loading ? "Loading…" : "Show the records"}
              </Button>
            ) : (
              <RecordList records={records} />
            )}
            {records && evidence.record_count > records.length && <p className="mt-2 text-xs text-muted">Showing the first {records.length}.</p>}
          </section>
        )}
      </div>
    </Sheet>
  );
}

export function RecordList({ records }: { records: Rec[] }) {
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line">
      {records.map((r) => (
        <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
          <div className="min-w-0">
            <p className="truncate font-medium">{r.title || r.party}</p>
            <p className="truncate text-xs text-muted">
              {r.type === "transaction" ? dayFull(r.date) : `${r.type === "invoice" ? "Invoice" : "Bill"} due ${dayFull(r.date)} · ${r.status}`} · {r.party} · {r.id}
            </p>
          </div>
          <span className={cx("num shrink-0 font-medium", r.direction === "in" ? "text-good" : "text-ink")}>
            {r.direction === "in" ? "+" : "−"}
            {inr(r.amount).replace("₹", "₹")}
          </span>
        </li>
      ))}
    </ul>
  );
}
