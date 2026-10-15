"use client";

import { ArrowDownLeft, ArrowUpRight, HandCoins, Mic, ReceiptText, Sparkles, Store, Wand2 } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { get, post } from "@/lib/api";
import { inr, words } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { DataVersion } from "./data-version";
import { confetti, useToast } from "./fx";
import { CatIcon } from "./cat";
import { Button, cx, Sheet } from "./ui";

export type Kind = "sale" | "expense" | "credit_sale" | "payment_in" | "bill" | "payment_out";

export interface Draft {
  kind?: Kind;
  amount?: number | string | null;
  party?: string;
  category?: string;
  mode?: string;
  date?: string;
  due_date?: string | null;
  note?: string;
}

const KINDS: { kind: Kind; label: string; I: React.ElementType; grad: string; ring: string }[] = [
  { kind: "sale", label: "Sale", I: Store, grad: "grad-mint", ring: "ring-emerald-400" },
  { kind: "payment_in", label: "Payment received", I: ArrowDownLeft, grad: "grad-ocean", ring: "ring-sky-400" },
  { kind: "credit_sale", label: "Udhaar given", I: HandCoins, grad: "grad-violet", ring: "ring-violet-400" },
  { kind: "expense", label: "Expense", I: ArrowUpRight, grad: "grad-sunset", ring: "ring-orange-400" },
  { kind: "bill", label: "Supplier bill", I: ReceiptText, grad: "grad-berry", ring: "ring-pink-400" },
  { kind: "payment_out", label: "Paid supplier", I: ArrowUpRight, grad: "grad-night", ring: "ring-indigo-400" },
];
const NEEDS_PARTY: Kind[] = ["credit_sale", "payment_in", "bill", "payment_out"];
const HAS_DUE: Kind[] = ["credit_sale", "bill"];
const HAS_CAT: Kind[] = ["expense", "bill"];
const COMMON_OUT = ["Raw materials", "Salaries", "Rent", "Electricity", "Logistics", "Packaging", "Marketing", "Staff Welfare", "Repairs & Maintenance", "Travel", "Owner Drawings", "GST Payment"];

interface Meta {
  parties: string[];
  categories: { name: string; type: string }[];
  today: string;
}

const Ctx = createContext<{ open: (d?: Draft) => void }>({ open: () => {} });

export function useQuickEntry() {
  return useContext(Ctx);
}

function addDays(iso: string, n: number) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function QuickEntryProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [initial, setInitial] = useState<Draft>({});
  const openWith = useCallback((d?: Draft) => {
    setInitial(d ?? {});
    setOpen(true);
  }, []);
  return (
    <Ctx.Provider value={{ open: openWith }}>
      {children}
      {open && <QuickEntry initial={initial} onClose={() => setOpen(false)} />}
    </Ctx.Provider>
  );
}

function QuickEntry({ initial, onClose }: { initial: Draft; onClose: () => void }) {
  const { t, lang } = useT();
  const { refresh } = useContext(DataVersion);
  const toast = useToast();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [f, setF] = useState<Draft>({ kind: "sale", mode: "cash", ...initial });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const rec = useRef<{ stop: () => void } | null>(null);
  const set = (k: keyof Draft, v: unknown) => setF((s) => ({ ...s, [k]: v }));
  const kind = f.kind ?? "sale";

  useEffect(() => {
    get<Meta>("/api/entries").then((m) => {
      setMeta(m);
      setF((s) => ({ ...s, date: s.date ?? m.today }));
    });
  }, []);
  useEffect(() => {
    if (HAS_DUE.includes(kind) && meta && !f.due_date) set("due_date", addDays(f.date ?? meta.today, 15));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, meta]);

  const fillFromText = async (s: string) => {
    if (!s.trim()) return;
    const d = await post<Draft & { missing: string[] }>("/api/entries/parse", { text: s });
    setF((cur) => ({ ...cur, ...Object.fromEntries(Object.entries(d).filter(([k, v]) => v != null && v !== "" && k !== "missing")) }));
  };

  const voice = () => {
    const W = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
    const SR = W.SpeechRecognition ?? W.webkitSpeechRecognition;
    if (!SR) {
      setErr("Voice input isn't supported in this browser — try Chrome.");
      return;
    }
    if (listening) {
      rec.current?.stop();
      return;
    }
    const r = new SR();
    r.lang = lang === "hi" ? "hi-IN" : "en-IN";
    r.interimResults = false;
    r.onresult = (e) => {
      const said = e.results[0][0].transcript;
      setText(said);
      fillFromText(said);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await post<{ id: string; message: string; cleared_all: boolean }>("/api/entries", { ...f, amount: Number(f.amount) });
      refresh();
      onClose();
      if (r.cleared_all) confetti();
      toast.show({
        text: r.message,
        undo: async () => {
          await post(`/api/entries/${r.id}/undo`, {});
          refresh();
          toast.show({ text: t("Undone") });
        },
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const k = KINDS.find((x) => x.kind === kind)!;
  const amount = Number(f.amount) || 0;
  const outCats = Array.from(new Set([...COMMON_OUT, ...(meta?.categories.filter((c) => c.type !== "in").map((c) => c.name) ?? [])]));
  const valid = amount > 0 && (!NEEDS_PARTY.includes(kind) || (f.party ?? "").trim().length > 0);

  return (
    <Sheet open onClose={onClose} title={t("New entry")} wide>
      <div className="space-y-5">
        <div className="flex items-center gap-2 rounded-2xl border border-line bg-canvas p-1.5 pl-3 focus-within:border-brand">
          <Wand2 className="size-4 shrink-0 text-brand" aria-hidden />
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fillFromText(text)}
            placeholder={t("Type or speak: “sold masala to Ravi 2500 cash”")}
            className="min-w-0 flex-1 bg-transparent py-2 text-sm outline-none"
            aria-label="Describe the entry"
          />
          <button onClick={voice} className={cx("grid size-9 place-items-center rounded-xl transition", listening ? "bg-bad text-white animate-pulse" : "text-ink-2 hover:bg-elevated")} aria-label={listening ? t("Listening") : "Speak"}>
            <Mic className="size-4" />
          </button>
          <Button size="sm" variant="secondary" onClick={() => fillFromText(text)} disabled={!text.trim()}>
            <Sparkles className="size-3.5" /> {t("Fill from text")}
          </Button>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {KINDS.map(({ kind: kk, label, I, grad, ring }) => (
            <button
              key={kk}
              onClick={() => set("kind", kk)}
              aria-pressed={kind === kk}
              className={cx(
                "flex flex-col items-start gap-2 rounded-2xl p-3 text-left text-sm font-medium transition",
                kind === kk ? `${grad} shadow-lg ring-2 ring-offset-2 ring-offset-surface ${ring}` : "border border-line bg-surface-2 text-ink hover:bg-elevated",
              )}
            >
              <I className="size-5" aria-hidden />
              <span className="leading-tight">{t(label)}</span>
            </button>
          ))}
        </div>

        <div>
          <label htmlFor="qe-amt" className="text-sm font-medium text-ink-2">
            {t("Amount")}
          </label>
          <div className={cx("mt-1 flex items-baseline gap-2 rounded-2xl px-4 py-3", k.grad)}>
            <span className="text-2xl font-semibold opacity-80">₹</span>
            <input
              id="qe-amt"
              autoFocus
              inputMode="decimal"
              value={f.amount ?? ""}
              onChange={(e) => set("amount", e.target.value.replace(/[^\d.]/g, ""))}
              placeholder="0"
              className="num w-full bg-transparent text-4xl font-semibold text-white outline-none placeholder:text-white/50"
            />
          </div>
          {amount > 0 && <p className="mt-1 text-xs text-muted">{inr(amount)}{words(amount) && ` · ₹${words(amount)}`}</p>}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="qe-party" className="text-sm font-medium text-ink-2">
              {NEEDS_PARTY.includes(kind) ? t(kind === "bill" || kind === "payment_out" ? "Supplier name" : "Customer name") : t("Name (optional)")}
            </label>
            <input id="qe-party" list="qe-parties" value={f.party ?? ""} onChange={(e) => set("party", e.target.value)} className="mt-1 h-11 w-full rounded-xl border border-line px-3 outline-none focus:border-brand" />
            <datalist id="qe-parties">{meta?.parties.map((p) => <option key={p} value={p} />)}</datalist>
          </div>
          <div>
            <label htmlFor="qe-date" className="text-sm font-medium text-ink-2">
              {t("Date")}
            </label>
            <input id="qe-date" type="date" value={f.date ?? ""} max={meta?.today} onChange={(e) => set("date", e.target.value)} className="mt-1 h-11 w-full rounded-xl border border-line px-3" />
          </div>
        </div>

        {HAS_CAT.includes(kind) && (
          <div>
            <p className="text-sm font-medium text-ink-2">{t("Category")}</p>
            <div className="no-scrollbar -mx-1 mt-1.5 flex gap-2 overflow-x-auto px-1 pb-1">
              {outCats.slice(0, 16).map((c) => (
                <button key={c} onClick={() => set("category", c)} className={cx("flex shrink-0 items-center gap-2 rounded-full border py-1 pr-3 pl-1 text-sm", f.category === c ? "border-brand bg-brand-50 text-brand" : "border-line")}>
                  <CatIcon category={c} size="sm" className="!size-7 !rounded-full" /> {c}
                </button>
              ))}
            </div>
          </div>
        )}

        {HAS_DUE.includes(kind) ? (
          <div>
            <label htmlFor="qe-due" className="text-sm font-medium text-ink-2">
              {t("Due date")}
            </label>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <input id="qe-due" type="date" value={f.due_date ?? ""} onChange={(e) => set("due_date", e.target.value)} className="h-10 rounded-xl border border-line px-3" />
              {[7, 15, 30].map((n) => (
                <button key={n} onClick={() => set("due_date", addDays(f.date ?? meta?.today ?? "", n))} className="h-10 rounded-full border border-line px-3 text-sm hover:border-brand">
                  +{n}d
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div>
            <p className="text-sm font-medium text-ink-2">{t("Paid with")}</p>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {["cash", "upi", "bank", "card"].map((m) => (
                <button key={m} onClick={() => set("mode", m)} className={cx("h-9 rounded-full border px-4 text-sm", f.mode === m ? "border-brand bg-brand text-on-brand" : "border-line")}>
                  {t(m === "upi" ? "UPI" : m[0].toUpperCase() + m.slice(1))}
                </button>
              ))}
            </div>
          </div>
        )}

        <input value={f.note ?? ""} onChange={(e) => set("note", e.target.value)} placeholder={t("Note")} className="h-11 w-full rounded-xl border border-line px-3 text-sm outline-none focus:border-brand" aria-label={t("Note")} />

        {err && <p className="rounded-xl bg-bad-50 p-3 text-sm text-bad">{err}</p>}
        <button onClick={save} disabled={!valid || busy} className="h-13 w-full rounded-full bg-brand py-3.5 text-[0.95rem] font-semibold text-on-brand shadow-md shadow-brand/20 hover:bg-brand-600 disabled:opacity-40">
          {busy ? "…" : `${t("Save")} · ${t(k.label)}${amount ? " " + inr(amount) : ""}`}
        </button>
      </div>
    </Sheet>
  );
}

interface SpeechRec {
  lang: string;
  interimResults: boolean;
  onresult: (e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void;
  onend: () => void;
  onerror: () => void;
  start: () => void;
  stop: () => void;
}
