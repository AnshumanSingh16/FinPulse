"use client";

import { CheckCircle2, FileSpreadsheet, Landmark, Lock, ReceiptText, Store, Trash2, UploadCloud } from "lucide-react";
import { useContext, useRef, useState } from "react";
import { DataVersion } from "@/components/data-version";
import { Button, Card, cx, Field, MoneyInput, Pill, SectionTitle } from "@/components/ui";
import { del, post, postForm } from "@/lib/api";
import { inr } from "@/lib/format";
import type { AppState } from "@/lib/types";

type Kind = "bank" | "invoices" | "balances";

const FIELD_LABELS: Record<string, string> = {
  date: "Date",
  description: "Description / narration",
  counterparty: "Name (customer or supplier)",
  category: "Category",
  amount: "Amount",
  debit: "Money out (debit / withdrawal)",
  credit: "Money in (credit / deposit)",
  direction: "In or out (Dr/Cr)",
  item_id: "Invoice / bill number",
  kind: "Type (sale or purchase)",
  due_date: "Due date",
  status: "Paid or unpaid",
  paid_date: "Date paid",
  issue_date: "Invoice date",
  as_of: "Date",
  balance: "Balance",
};
const SHOWN: Record<Kind, string[]> = {
  bank: ["date", "description", "counterparty", "category", "amount", "debit", "credit", "direction"],
  invoices: ["item_id", "counterparty", "amount", "due_date", "status", "kind", "paid_date"],
  balances: ["as_of", "balance"],
};

interface Inspect {
  columns: string[];
  mapping: Record<string, string | null>;
  missing: string[];
  rows: number;
  preview: Record<string, string>[];
}

export default function DataPage() {
  const { state, refresh } = useContext(DataVersion);
  const switchTo = async (source: "demo" | "upload") => {
    await post("/api/source", { source });
    refresh();
  };
  const clear = async () => {
    if (!confirm("Delete all your uploaded data from this computer? The demo stays available.")) return;
    await del("/api/upload");
    refresh();
  };
  if (!state) return null;
  const up = state.upload;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Your data</h1>
        <p className="flex items-center gap-1.5 text-ink-2">
          <Lock className="size-4" aria-hidden /> Your files stay on this computer. FinPilot never uploads them anywhere.
        </p>
      </div>

      <Card>
        <SectionTitle>Which business are you looking at?</SectionTitle>
        <div className="grid gap-3 sm:grid-cols-2">
          <SourceCard active={state.is_demo} title="Demo shop" sub="Annapurna Masala Works — made-up numbers to explore" onClick={() => switchTo("demo")} />
          <SourceCard
            active={!state.is_demo}
            title={up.ready ? up.name : "My business"}
            sub={up.ready ? `${up.bank_rows.toLocaleString("en-IN")} transactions · ${up.invoice_rows} invoices & bills` : "Upload your bank transactions below"}
            onClick={() => up.ready && switchTo("upload")}
            disabled={!up.ready}
          />
        </div>
      </Card>

      <Upload
        kind="bank"
        n={1}
        icon={FileSpreadsheet}
        title="Bank transactions"
        sub="Download a statement from your net banking as Excel or CSV, or export from Tally / Zoho / your billing app."
        done={up.bank_rows ? `${up.bank_rows.toLocaleString("en-IN")} transactions added` : null}
        onDone={refresh}
      />
      <Balance done={up.balance_rows ? `${up.balance_rows} balance${up.balance_rows > 1 ? "s" : ""} added` : null} onDone={refresh} state={state} />
      <Upload
        kind="invoices"
        n={3}
        icon={ReceiptText}
        title="Invoices and bills (optional)"
        sub="Unpaid sales invoices and supplier bills. Lets FinPilot track who owes you, what's due, and forecast your cash."
        done={up.invoice_rows ? `${up.invoice_rows} invoices & bills added` : null}
        onDone={refresh}
      />

      {up.ready && (
        <Card className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-medium">Delete my data</p>
            <p className="text-sm text-ink-2">Removes everything you uploaded from this computer.</p>
          </div>
          <Button variant="secondary" onClick={clear}>
            <Trash2 className="size-4" /> Delete
          </Button>
        </Card>
      )}
    </div>
  );
}

function SourceCard({ active, title, sub, onClick, disabled }: { active: boolean; title: string; sub: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={cx("flex gap-3 rounded-2xl border-2 p-4 text-left transition disabled:opacity-60", active ? "border-brand bg-brand-50" : "border-line hover:border-ink-2")}
    >
      <Store className={cx("mt-0.5 size-5 shrink-0", active ? "text-brand" : "text-ink-2")} />
      <span>
        <span className="flex items-center gap-2 font-semibold">
          {title} {active && <Pill tone="good">Showing</Pill>}
        </span>
        <span className="block text-sm text-ink-2">{sub}</span>
      </span>
    </button>
  );
}

function Step({ n, icon: I, title, sub, done, children }: { n: number; icon: React.ElementType; title: string; sub: string; done: string | null; children: React.ReactNode }) {
  return (
    <Card id={n === 2 ? "balance" : undefined} className="scroll-mt-20">
      <div className="mb-4 flex items-start gap-3">
        <span className={cx("grid size-10 shrink-0 place-items-center rounded-full", done ? "bg-good-50 text-good" : "bg-canvas text-ink-2")}>{done ? <CheckCircle2 className="size-5" /> : <I className="size-5" />}</span>
        <div className="flex-1">
          <p className="text-xs font-medium text-muted">Step {n}</p>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          <p className="text-sm text-ink-2">{sub}</p>
          {done && <p className="mt-1 text-sm font-medium text-good">✓ {done}</p>}
        </div>
      </div>
      {children}
    </Card>
  );
}

function Upload({ kind, n, icon, title, sub, done, onDone }: { kind: Kind; n: number; icon: React.ElementType; title: string; sub: string; done: string | null; onDone: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [info, setInfo] = useState<Inspect | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [business, setBusiness] = useState("");
  const [invoiceKind, setInvoiceKind] = useState("customers");
  const [sales, setSales] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<{ summary: string; notes: string[] } | null>(null);
  const [drag, setDrag] = useState(false);

  const pick = async (f: File) => {
    setFile(f);
    setErr(null);
    setResult(null);
    setBusy(true);
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", f);
    try {
      const r = await postForm<Inspect>("/api/upload/inspect", fd);
      setInfo(r);
      setMapping(r.mapping);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setInfo(null);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", file);
    fd.append("mapping", JSON.stringify(mapping));
    fd.append("business", business);
    fd.append("invoice_kind", mapping.kind ? "" : invoiceKind);
    fd.append("incoming_is_sales", String(sales));
    try {
      const r = await postForm<{ summary: string; notes: string[] }>("/api/upload/import", fd);
      setResult(r);
      setInfo(null);
      setFile(null);
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const shown = SHOWN[kind];
  return (
    <Step n={n} icon={icon} title={title} sub={sub} done={done}>
      {!info && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files?.[0];
            if (f) pick(f);
          }}
          onClick={() => input.current?.click()}
          className={cx("flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center transition", drag ? "border-brand bg-brand-50" : "border-line hover:border-ink-2")}
        >
          <UploadCloud className="size-7 text-ink-2" aria-hidden />
          <p className="font-medium">{busy ? "Reading file…" : done ? "Upload a new file to replace it" : "Drop a file here or click to choose"}</p>
          <p className="text-xs text-muted">Excel (.xlsx) or CSV, up to 25 MB</p>
          <input ref={input} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(e) => e.target.files?.[0] && pick(e.target.files[0])} />
        </div>
      )}

      {info && (
        <div className="space-y-4">
          <p className="text-sm">
            <span className="font-medium">{file?.name}</span> · {info.rows.toLocaleString("en-IN")} rows. We matched the columns below — check they look right.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {shown.map((f) => (
              <label key={f} className="block text-sm">
                <span className="mb-1 block text-ink-2">{FIELD_LABELS[f] ?? f}</span>
                <select
                  value={mapping[f] ?? ""}
                  onChange={(e) => setMapping((m) => ({ ...m, [f]: e.target.value || null }))}
                  className={cx("h-10 w-full rounded-xl border bg-surface px-3", mapping[f] ? "border-line" : "border-dashed border-line text-muted")}
                >
                  <option value="">— not in my file —</option>
                  {info.columns.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <div className="overflow-x-auto rounded-2xl border border-line">
            <table className="w-full text-xs">
              <thead className="bg-canvas text-left text-ink-2">
                <tr>
                  {info.columns.map((c) => (
                    <th key={c} className="px-3 py-2 font-medium whitespace-nowrap">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {info.preview.map((r, i) => (
                  <tr key={i}>
                    {info.columns.map((c) => (
                      <td key={c} className="px-3 py-1.5 whitespace-nowrap">
                        {r[c]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {kind === "bank" && (
            <>
              <Field label="Business name" htmlFor="biz">
                <input id="biz" value={business} onChange={(e) => setBusiness(e.target.value)} placeholder="e.g. Sharma General Store" className="h-10 w-full rounded-xl border border-line px-3 outline-none focus:border-brand" />
              </Field>
              {!mapping.category && (
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={sales} onChange={(e) => setSales(e.target.checked)} className="mt-1" />
                  <span>
                    Count money coming in as <b>sales</b>. Your file has no category column. Untick if lots of it is loans or transfers between your own accounts.
                  </span>
                </label>
              )}
            </>
          )}
          {kind === "invoices" && !mapping.kind && (
            <Field label="These are…">
              <div className="flex flex-wrap gap-2">
                {[
                  ["customers", "Invoices to my customers"],
                  ["suppliers", "Bills from my suppliers"],
                ].map(([v, l]) => (
                  <button key={v} onClick={() => setInvoiceKind(v)} className={cx("h-10 rounded-full border px-4 text-sm", invoiceKind === v ? "border-brand bg-brand-50 text-brand" : "border-line")}>
                    {l}
                  </button>
                ))}
              </div>
            </Field>
          )}
          {info.missing.length > 0 && <p className="text-sm text-caution">Please choose a column for: {info.missing.join(", ")}.</p>}
          <div className="flex gap-2">
            <Button onClick={save} disabled={busy}>
              {busy ? "Importing…" : "Looks right — import"}
            </Button>
            <Button variant="secondary" onClick={() => setInfo(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {err && <p className="mt-3 rounded-xl bg-bad-50 p-3 text-sm text-bad">{err}</p>}
      {result && (
        <div className="mt-3 rounded-xl bg-good-50 p-3 text-sm">
          <p className="font-medium text-good">{result.summary}</p>
          {result.notes.map((n) => (
            <p key={n} className="mt-1 text-ink-2">
              {n}
            </p>
          ))}
        </div>
      )}
    </Step>
  );
}

function Balance({ done, onDone, state }: { done: string | null; onDone: () => void; state: AppState }) {
  const [date, setDate] = useState(state.is_demo ? new Date().toISOString().slice(0, 10) : state.as_of);
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await post("/api/balance", { date, amount });
      setMsg(`Saved: ${inr(Number(amount))} on ${date}.`);
      setAmount("");
      onDone();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Step n={2} icon={Landmark} title="Your bank balance" sub="The closing balance on any date from your statement or banking app. FinPilot uses it to work out your real cash — it never guesses it from sales." done={done}>
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr_auto] sm:items-end">
        <Field label="On date" htmlFor="bdate">
          <input id="bdate" type="date" value={date} onChange={(e) => setDate(e.target.value)} className="h-12 w-full rounded-2xl border border-line px-3" />
        </Field>
        <Field label="Balance">
          <MoneyInput value={amount} onChange={setAmount} placeholder="5,00,000" />
        </Field>
        <Button size="lg" onClick={save} disabled={!amount || busy}>
          Save
        </Button>
      </div>
      {msg && <p className="mt-2 text-sm text-ink-2">{msg}</p>}
    </Step>
  );
}
