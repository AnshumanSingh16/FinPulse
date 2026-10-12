"use client";

import { Download, FileUp, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import { PROFILE_LABELS, type ProfileField } from "@/lib/personal/schemas";
import type { DocumentRecord } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { usePersonal } from "./provider";
import { Loading, Notice, Section } from "./ui";

const SAMPLES = [
  { file: "salary-slip-demo.txt", label: "Salary slip (net pay differs from the demo profile, and contains a hidden instruction)" },
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
      <header className="flex flex-col gap-1">
        <div className="text-xs font-medium tracking-wide text-primary uppercase">Document intelligence</div>
        <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Upload salary slips, bank statements or loan quotes. FinPulse extracts figures, compares them with your profile and flags mismatches. Extracted values are proposals — nothing changes until you confirm. Documents are not verified with any bank, employer or government source.
        </p>
      </header>

      <Section title="Upload" description=".txt or .csv are parsed by deterministic rules. PDFs are read by the AI model when it is configured. Max 2 MB.">
        <div className="flex flex-col gap-4 md:flex-row md:items-start">
          <div className="flex flex-col gap-2">
            <input ref={fileRef} type="file" accept=".txt,.csv,.pdf,text/plain,text/csv,application/pdf" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
            <Button onClick={() => fileRef.current?.click()} disabled={busy} className="w-fit">
              {busy ? <Loader2 className="animate-spin" /> : <FileUp />} Choose a file
            </Button>
            {!state.status.ai.enabled ? <span className="text-[11px] text-muted-foreground">AI not configured: PDFs are stored but not read.</span> : null}
          </div>
          <div className="flex flex-col gap-1.5 text-sm md:border-l md:pl-4">
            <span className="text-xs font-medium text-muted-foreground">Fictional sample documents — download one, then upload it:</span>
            {SAMPLES.map((s) => (
              <a key={s.file} href={`/samples/${s.file}`} download className="inline-flex items-center gap-1.5 text-primary hover:underline">
                <Download className="size-3.5" /> {s.label}
              </a>
            ))}
          </div>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
      </Section>

      {state.documents.length === 0 ? (
        <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
      ) : (
        state.documents.map((d) => <DocumentCard key={d.id} doc={d} />)
      )}
    </div>
  );
}

function DocumentCard({ doc }: { doc: DocumentRecord }) {
  const { state, setState } = usePersonal();
  const applicable = doc.extraction.fields.filter((f) => f.profileField && typeof f.value === "number");
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
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => act({ action: "delete" })} aria-label={`Delete ${doc.name}`}>
          <Trash2 />
        </Button>
      }
    >
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={cn("rounded-md px-2 py-0.5 font-medium", doc.extraction.status === "extracted" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>{STATUS[doc.extraction.status]}</span>
        <span className={cn("rounded-md px-2 py-0.5", doc.review === "confirmed" ? "bg-status-good/10 text-text-good" : doc.review === "dismissed" ? "bg-muted text-muted-foreground" : "bg-status-warning/10 text-status-warning")}>
          Review: {doc.review}
        </span>
        <span className="text-muted-foreground">{doc.extraction.note}</span>
      </div>
      {doc.flags.map((f) => (
        <Notice key={f.message} tone="warning" title={<span className="inline-flex items-center gap-1"><ShieldAlert className="size-4" /> Untrusted content flagged</span>}>
          {f.message}
        </Notice>
      ))}
      {doc.extraction.fields.length ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[600px] text-xs">
            <thead className="bg-muted/60 text-muted-foreground">
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
                const diff = isNum && typeof current === "number" && current > 0 ? Math.abs((f.value as number) - current) / current : null;
                const money = !["rate", "tenure"].includes(f.key) && !f.key.includes("percent") && !f.key.includes("months");
                return (
                  <tr key={f.key} className="border-t align-top">
                    <td className="px-3 py-2">
                      <div className="font-medium">{f.label}</div>
                      <div className="max-w-xs truncate text-muted-foreground" title={f.evidence}>“{f.evidence}”</div>
                    </td>
                    <td className="tabular px-3 py-2 text-right">{isNum ? (money ? formatINR(f.value as number) : f.value) : f.value}</td>
                    <td className="px-3 py-2 text-muted-foreground">{f.confidence}</td>
                    <td className="tabular px-3 py-2 text-right">{pf ? (typeof current === "number" ? formatINR(current) : "—") : <span className="text-muted-foreground">n/a</span>}</td>
                    <td className="px-3 py-2">
                      {diff === null ? (
                        <span className="text-muted-foreground">{pf ? "No profile value" : "Reference only"}</span>
                      ) : diff > 0.05 ? (
                        <span className="text-status-warning">Differs by {Math.round(diff * 100)}%</span>
                      ) : (
                        <span className="text-text-good">Consistent</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {pf && isNum && doc.review === "pending" ? (
                        <label className="flex items-center gap-1.5">
                          <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={chosen.includes(f.key)} onChange={(e) => setChosen(e.target.checked ? [...chosen, f.key] : chosen.filter((k) => k !== f.key))} />
                          <span className="text-muted-foreground">→ {PROFILE_LABELS[pf]}</span>
                        </label>
                      ) : doc.appliedFields.includes(pf ?? "") ? (
                        <span className="text-text-good">Applied</span>
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
            {chosen.length ? `Confirm & apply ${chosen.length} value(s) to profile` : "Confirm reviewed (apply nothing)"}
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => act({ action: "dismiss" })}>
            Dismiss extraction
          </Button>
          {applicable.length === 0 ? <span className="self-center text-xs text-muted-foreground">No fields map to the profile; mismatches still feed the Verification Agent.</span> : null}
        </div>
      ) : null}
    </Section>
  );
}
