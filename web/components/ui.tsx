"use client";

import { AlertTriangle, CheckCircle2, Info, Loader2, OctagonAlert, X } from "lucide-react";
import { useEffect } from "react";
import type { Tone } from "@/lib/types";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export const toneText: Record<Tone, string> = {
  good: "text-good",
  caution: "text-caution",
  bad: "text-bad",
  info: "text-info",
  neutral: "text-ink-2",
};
export const toneBg: Record<Tone, string> = {
  good: "bg-good-50",
  caution: "bg-caution-50",
  bad: "bg-bad-50",
  info: "bg-info-50",
  neutral: "bg-canvas",
};

export function ToneIcon({ tone, className = "size-5" }: { tone: Tone; className?: string }) {
  const I = tone === "good" ? CheckCircle2 : tone === "bad" ? OctagonAlert : tone === "caution" ? AlertTriangle : Info;
  return <I className={cx(className, toneText[tone])} aria-hidden />;
}

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cx("card p-5", className)} {...rest}>
      {children}
    </div>
  );
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <h2 className="text-[1.05rem] font-semibold tracking-tight text-ink">{children}</h2>
      {action}
    </div>
  );
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost"; size?: "sm" | "md" | "lg" };

export function Button({ variant = "primary", size = "md", className, ...rest }: BtnProps) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 font-semibold tracking-wide transition disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold",
        size === "sm" && "h-8 px-3.5 text-xs uppercase",
        size === "md" && "h-10 px-5 text-sm uppercase",
        size === "lg" && "h-12 px-6 text-sm uppercase",
        variant === "primary" && "neo bg-[#f4f2ee] text-black hover:bg-white [--neo-edge:#7d7a85]",
        variant === "secondary" && "neo border border-[#3a3a42] bg-surface-2 text-ink hover:bg-elevated [--neo-edge:#000]",
        variant === "ghost" && "rounded-full text-brand normal-case tracking-normal hover:bg-brand-50",
        className,
      )}
      {...rest}
    />
  );
}

export function Pill({ tone = "neutral", children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium", toneBg[tone], toneText[tone], className)}>{children}</span>;
}

export function Segmented<T extends string>({ value, options, onChange, className }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div role="tablist" className={cx("inline-flex rounded-full border border-line bg-surface p-1", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            "h-9 rounded-full px-4 text-sm font-medium whitespace-nowrap transition",
            o.value === value ? "bg-[#f4f2ee] text-black shadow-sm" : "text-ink-2 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-ink-2 justify-center">
      <Loader2 className="size-5 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function ErrorNote({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <Card className="flex items-start gap-3">
      <ToneIcon tone="bad" />
      <div className="flex-1">
        <p className="font-medium">Couldn&apos;t load this</p>
        <p className="text-sm text-ink-2">{message}</p>
      </div>
      {retry && (
        <Button size="sm" variant="secondary" onClick={retry}>
          Try again
        </Button>
      )}
    </Card>
  );
}

export function Sheet({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", k);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal aria-label={title}>
      <div className="absolute inset-0 bg-black/75 backdrop-blur-sm" onClick={onClose} />
      <div className={cx("sheet relative max-h-[88vh] w-full overflow-y-auto rounded-t-3xl border border-line bg-surface p-6 shadow-2xl sm:rounded-3xl", wide ? "sm:max-w-2xl" : "sm:max-w-lg")}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
          <button onClick={onClose} className="-m-1 rounded-full p-1.5 text-ink-2 hover:bg-canvas" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: React.ReactNode; tone?: Tone }) {
  return (
    <div>
      <p className="text-sm text-ink-2">{label}</p>
      <p className={cx("num mt-0.5 text-xl font-semibold", tone && toneText[tone])}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

export function MoneyInput({ value, onChange, placeholder, id, autoFocus }: { value: string; onChange: (v: string) => void; placeholder?: string; id?: string; autoFocus?: boolean }) {
  return (
    <div className="flex h-12 items-center rounded-2xl border border-line bg-surface px-4 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/15">
      <span className="mr-1.5 text-ink-2">₹</span>
      <input
        id={id}
        autoFocus={autoFocus}
        inputMode="numeric"
        className="num w-full bg-transparent text-lg outline-none placeholder:text-muted"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value.replace(/[^\d.]/g, ""))}
      />
    </div>
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: React.ReactNode; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}
