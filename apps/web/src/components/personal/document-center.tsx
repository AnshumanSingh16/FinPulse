"use client";

import { Download, FileText, FileUp, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import { PROFILE_LABELS, type ProfileField } from "@/lib/personal/schemas";
import type { DocumentRecord } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { usePersonal } from "./provider";
import { EmptyState, Loading, Notice, PageTitle, Section } from "./ui";

const SAMPLES = [
  {
    file: "salary-slip-demo.txt",
    label: "Salary slip (net pay differs from the demo profile, and contains a hidden instruction)",
  },
  { file: "bank-statement-demo.csv", label: "Bank statement, 3 months (CSV)" },
  { file: "loan-quote-demo.txt", label: "Home-loan quotation (fictional lender)" },
];

const STATUS: Record<DocumentRecord["extraction"]["status"], string> = {
  extracted: "Extracted — needs your review",
  partial: "Partly extracted — needs your review",
  not_extracted: "Not extracted",
  failed: "Extraction failed",
};

export function DocumentCenter() {
  const { state, setState } = usePersonal();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  if (!state) return <Loading />;

  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error("File too large (max 2 MB)");
      setState((await api.upload(file)).state);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        eyebrow="Check your documents"
        title="Documents"
        description="Upload salary slips, bank statements or loan quotes. FinPulse extracts figures, compares them with your profile and flags mismatches. Extracted values are proposals — nothing changes until you confirm. Documents are not verified with any bank, employer or government source."
      />

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]" aria-label="Upload">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void upload(e.dataTransfer.files?.[0]);
          }}
          className={cn(
            "flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed bg-surface px-6 py-10 text-center transition-colors",
            dragging ? "border-brand-600 bg-brand-50" : "border-line-strong",
          )}
        >
          <span className="flex size-12 items-center justify-center rounded-xl bg-surface-sunken text-ink-500">
            {busy ? (
              <Loader2 className="size-5 animate-spin" aria-hidden />
            ) : (
              <FileUp className="size-5" aria-hidden />
            )}
          </span>
          <div className="flex flex-col gap-1">
            <p className="text-[15px] font-semibold">
              {busy ? "Reading your document…" : "Drop a file here, or choose one"}
            </p>
            <p className="text-[13px] text-ink-500">
              .txt or .csv are parsed by deterministic rules. PDFs are read by the AI model when it
              is configured. Max 2 MB.
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.csv,.pdf,text/plain,text/csv,application/pdf"
            className="hidden"
            onChange={(e) => upload(e.target.files?.[0])}
          />
          <Button onClick={() => fileRef.current?.click()} disabled={busy}>
            <FileUp /> Choose a file
          </Button>
          {!state.status.ai.enabled ? (
            <span className="text-[12px] text-ink-400">
              AI is off: PDFs are stored but not read.
            </span>
          ) : null}
        </div>
        <aside className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-5 shadow-xs">
          <h2 className="text-[14px] font-semibold">Try a fictional sample</h2>
          <p className="text-[12.5px] text-ink-500">Download one, then upload it above.</p>
          <ul className="flex flex-col gap-2">
            {SAMPLES.map((s) => (
              <li key={s.file}>
                <a
                  href={`/samples/${s.file}`}
                  download
                  className="-mx-2 flex items-start gap-2 rounded-lg px-2 py-1.5 text-[13.5px] text-ink-700 hover:bg-surface-sunken"
                >
                  <Download className="mt-0.5 size-3.5 shrink-0 text-brand-600" aria-hidden />{" "}
                  {s.label}
                </a>
              </li>
            ))}
          </ul>
        </aside>
      </section>
      {error ? <Notice tone="error">{error}</Notice> : null}

      {state.documents.length === 0 ? (
        <EmptyState icon={FileText} title="No documents yet">
          Extracted figures will appear here for you to compare and confirm.
        </EmptyState>
      ) : (
        state.documents.map((d) => <DocumentCard key={d.id} doc={d} />)
      )}
    </div>
  );
}

function DocumentCard({ doc }: { doc: DocumentRecord }) {
  const { state, setState } = usePersonal();
  const applicable = doc.extraction.fields.filter(
    (f) => f.profileField && typeof f.value === "number",
  );
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const profile = state!.profile.values;

  async function act(body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      setState(await api.documentAction(doc.id, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section
      title={doc.name}
      description={`${doc.docType.replace("_", " ")} · ${(doc.size / 1024).toFixed(1)} KB · uploaded ${new Date(doc.uploadedAt).toLocaleString("en-IN")} · ${doc.extraction.method === "ai" ? "AI extraction" : doc.extraction.method === "rule_based_text" ? "rule-based extraction" : "not read"}`}
      actions={
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => act({ action: "delete" })}
          aria-label={`Delete ${doc.name}`}
        >
          <Trash2 />
        </Button>
      }
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className={cn(
            "rounded-md px-2 py-0.5 font-medium",
            doc.extraction.status === "extracted"
              ? "bg-primary/10 text-brand-700"
              : "bg-surface-sunken text-ink-500",
          )}
        >
          {STATUS[doc.extraction.status]}
        </span>
        <span
          className={cn(
            "rounded-md px-2 py-0.5",
            doc.review === "confirmed"
              ? "bg-brand-50 text-brand-700"
              : doc.review === "dismissed"
                ? "bg-surface-sunken text-ink-500"
                : "bg-caution-50 text-caution-text",
          )}
        >
          Review: {doc.review}
        </span>
        <span className="text-ink-500">{doc.extraction.note}</span>
      </div>
      {doc.flags.map((f) => (
        <Notice
          key={f.message}
          tone="warning"
          title={
            <span className="inline-flex items-center gap-1">
              <ShieldAlert className="size-4" /> Untrusted content flagged
            </span>
          }
        >
          {f.message}
        </Notice>
      ))}
      {doc.extraction.fields.length ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[600px] text-xs">
            <thead className="bg-surface-sunken text-ink-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Field</th>
                <th className="px-3 py-2 text-right font-medium">Extracted</th>
                <th className="px-3 py-2 text-left font-medium">Confidence</th>
                <th className="px-3 py-2 text-right font-medium">Your profile</th>
                <th className="px-3 py-2 text-left font-medium">Check</th>
                <th className="px-3 py-2 text-left font-medium">Apply</th>
              </tr>
            </thead>
            <tbody>
              {doc.extraction.fields.map((f) => {
                const pf = f.profileField as ProfileField | undefined;
                const current = pf ? profile[pf] : null;
                const isNum = typeof f.value === "number";
                const diff =
                  isNum && typeof current === "number" && current > 0
                    ? Math.abs((f.value as number) - current) / current
                    : null;
                const money =
                  !["rate", "tenure"].includes(f.key) &&
                  !f.key.includes("percent") &&
                  !f.key.includes("months");
                return (
                  <tr key={f.key} className="border-t align-top">
                    <td className="px-3 py-2">
                      <div className="font-medium">{f.label}</div>
                      <div className="max-w-xs truncate text-ink-500" title={f.evidence}>
                        “{f.evidence}”
                      </div>
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      {isNum ? (money ? formatINR(f.value as number) : f.value) : f.value}
                    </td>
                    <td className="px-3 py-2 text-ink-500">{f.confidence}</td>
                    <td className="tabular px-3 py-2 text-right">
                      {pf ? (
                        typeof current === "number" ? (
                          formatINR(current)
                        ) : (
                          "—"
                        )
                      ) : (
                        <span className="text-ink-500">n/a</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {diff === null ? (
                        <span className="text-ink-500">
                          {pf ? "No profile value" : "Reference only"}
                        </span>
                      ) : diff > 0.05 ? (
                        <span className="text-caution-text">
                          Differs by {Math.round(diff * 100)}%
                        </span>
                      ) : (
                        <span className="text-brand-700">Consistent</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {pf && isNum && doc.review === "pending" ? (
                        <label className="flex items-center gap-1.5">
                          <input
                            type="checkbox"
                            className="size-4 accent-[var(--primary)]"
                            checked={chosen.includes(f.key)}
                            onChange={(e) =>
                              setChosen(
                                e.target.checked
                                  ? [...chosen, f.key]
                                  : chosen.filter((k) => k !== f.key),
                              )
                            }
                          />
                          <span className="text-ink-500">→ {PROFILE_LABELS[pf]}</span>
                        </label>
                      ) : doc.appliedFields.includes(pf ?? "") ? (
                        <span className="text-brand-700">Applied</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      {error ? <Notice tone="error">{error}</Notice> : null}
      {doc.review === "pending" ? (
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => act({ action: "confirm", applyKeys: chosen })}>
            {chosen.length
              ? `Confirm & apply ${chosen.length} value(s) to profile`
              : "Confirm reviewed (apply nothing)"}
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => act({ action: "dismiss" })}>
            Dismiss extraction
          </Button>
          {applicable.length === 0 ? (
            <span className="self-center text-xs text-ink-500">
              No fields map to the profile; mismatches still feed the Verification Agent.
            </span>
          ) : null}
        </div>
      ) : null}
    </Section>
  );
}
