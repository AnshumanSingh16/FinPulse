"use client";

import { Calculator, FileText, HelpCircle, ListChecks, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { dayFull, inr } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Evidence, Rec } from "@/lib/types";
import { cx, Sheet } from "./ui";

export function EvidenceButton({ evidence, label, className }: { evidence?: Evidence | null; label?: string; className?: string }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  if (!evidence) return null;
  return (
    <>
      <button onClick={() => setOpen(true)} className={cx("inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline", className)}>
        <ShieldCheck className="size-4" aria-hidden /> {label ?? t("Prove it")}
      </button>
      <EvidenceSheet evidence={evidence} open={open} onClose={() => setOpen(false)} />
    </>
  );
}

/** "Show me why" for one recommendation: asks the server for its proof (records, arithmetic, assumptions, what can't be verified). */
export function ProveButton({ moveId, className, dark }: { moveId: string; className?: string; dark?: boolean }) {
  const { t } = useT();
  const [ev, setEv] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const open = async () => {
    setBusy(true);
    try {
      setEv(await get<Evidence>(`/api/prove?move=${encodeURIComponent(moveId)}`));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button onClick={open} disabled={busy}
        className={cx("inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold transition",
          dark ? "border-pit-line text-pit-muted hover:text-pit-ink" : "border-line text-ink-2 hover:border-brand hover:text-brand", className)}>
        <ShieldCheck className="size-3.5" aria-hidden /> {busy ? t("Checking…") : t("Show me why")}
      </button>
      {ev && <EvidenceSheet evidence={ev} open={!!ev} onClose={() => setEv(null)} />}
    </>
  );
}

function Section({ icon: Icon, title, children }: { icon: typeof ShieldCheck; title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-[0.12em] text-ink-2 uppercase"><Icon className="size-4 text-brand" /> {title}</h4>
      {children}
    </section>
  );
}

/** The proof behind a result: 1 the records used, 2 the calculation, 3 the assumptions, 4 what couldn't be verified. */
export function EvidenceSheet({ evidence, open, onClose }: { evidence: Evidence; open: boolean; onClose: () => void }) {
  const { t } = useT();
  const [records, setRecords] = useState<Rec[] | null>(evidence.records ?? null);
  useEffect(() => {
    if (!open || records || !evidence.record_ids.length) return;
    get<Rec[]>(`/api/records?ids=${encodeURIComponent(evidence.record_ids.slice(0, 60).join(","))}`).then(setRecords).catch(() => setRecords([]));
  }, [open, records, evidence.record_ids]);
  const formula = typeof evidence.formula === "string" ? [evidence.formula] : evidence.formula ?? [];
  const unverified = evidence.unverified ?? [];
  const span = evidence.period && evidence.period[0] && evidence.period[1] ? `${dayFull(evidence.period[0])} – ${dayFull(evidence.period[1])}` : null;
  return (
    <Sheet open={open} onClose={onClose} title={evidence.title} wide>
      <div className="space-y-6 text-[0.95rem] leading-relaxed">
        {evidence.claim && <p className="serif text-xl leading-snug font-semibold">{evidence.claim}</p>}
        <p className="rounded-2xl bg-brand-50 p-4 text-sm text-ink">
          {t("Every figure here is calculated by FinPilot's tested formulas from your own records — not written by AI.")}
        </p>

        <Section icon={FileText} title={t("1 · The records used ({n})", { n: evidence.record_count })}>
          {span && <p className="mb-2 text-xs text-muted">{t("Date range: {span}", { span })}</p>}
          {!evidence.record_count ? (
            <p className="text-sm text-muted">{t("No individual records — this rests on the forecast and the assumptions below.")}</p>
          ) : !records ? (
            <p className="text-sm text-muted">{t("Loading…")}</p>
          ) : (
            <>
              <RecordList records={records} />
              {evidence.record_count > records.length && <p className="mt-2 text-xs text-muted">{t("Showing the first {n}.", { n: records.length })}</p>}
            </>
          )}
        </Section>

        <Section icon={Calculator} title={t("2 · The calculation")}>
          {formula.length > 0 && (
            <ol className="mb-2 space-y-1.5 rounded-2xl border border-line bg-surface-2 p-4 font-mono text-[0.82rem] leading-relaxed">
              {formula.map((f, i) => <li key={i}>{f}</li>)}
            </ol>
          )}
          {evidence.method && <p className="text-sm text-ink-2">{evidence.method}</p>}
        </Section>

        {evidence.assumptions.length > 0 && (
          <Section icon={ListChecks} title={t("3 · What I assumed")}>
            <ul className="list-disc space-y-1 pl-5 text-sm">{evidence.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          </Section>
        )}

        {(unverified.length > 0 || evidence.limitations.length > 0) && (
          <Section icon={HelpCircle} title={t("4 · What I couldn't verify")}>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {unverified.map((a) => <li key={a}>{a}</li>)}
              {evidence.limitations.map((a) => <li key={a} className="text-ink-2">{a}</li>)}
            </ul>
          </Section>
        )}
      </div>
    </Sheet>
  );
}

export function RecordList({ records }: { records: Rec[] }) {
  const { t } = useT();
  return (
    <ul className="max-h-80 divide-y divide-line overflow-y-auto rounded-2xl border border-line">
      {records.map((r) => (
        <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
          <div className="min-w-0">
            <p className="truncate font-medium">{r.title || r.party}</p>
            <p className="truncate text-xs text-muted">
              {r.type === "transaction" ? dayFull(r.date) : `${r.type === "invoice" ? t("Invoice") : t("Bill")} ${t("due")} ${dayFull(r.date)} · ${r.status}`} · {r.party} · {r.id}
            </p>
          </div>
          <span className={cx("num shrink-0 font-medium", r.direction === "in" ? "text-good" : "text-ink")}>
            {r.direction === "in" ? "+" : "−"}
            {inr(r.amount)}
          </span>
        </li>
      ))}
    </ul>
  );
}
