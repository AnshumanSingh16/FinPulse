"use client";

import { useId, useState, type ReactNode } from "react";

import { formatINR } from "@/lib/format";
import { inrWords, parseINRAmount } from "@/lib/personal/finance/parse-inr";
import { cn } from "@/lib/utils";

import { inputClass } from "./ui";

/** Parse what a person types for money: "2,00,000", "200000", "75 lakh", "1.2cr", "50k". */
export function parseMoneyInput(text: string): number | null {
  const t = text.trim();
  if (!t) return null;
  const plain = Number(t.replace(/[₹,\s]/g, ""));
  if (Number.isFinite(plain)) return plain >= 0 ? Math.round(plain) : null;
  const parsed = parseINRAmount(t);
  return parsed !== null && parsed >= 0 ? parsed : null;
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
  badge,
  error,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  htmlFor?: string;
  badge?: ReactNode;
  error?: string | null;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
          {label}
        </label>
        {badge}
      </div>
      {children}
      {error ? (
        <span className="text-xs text-text-critical">{error}</span>
      ) : hint ? (
        <span className="text-xs text-muted-foreground">{hint}</span>
      ) : null}
    </div>
  );
}

/** Rupee input that accepts Indian shorthand and shows the parsed value. Empty = not provided. */
export function MoneyInput({
  label,
  value,
  onChange,
  placeholder,
  hint,
  badge,
  required,
  highlight,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  placeholder?: string;
  hint?: ReactNode;
  badge?: ReactNode;
  required?: boolean;
  highlight?: boolean;
}) {
  const id = useId();
  const show = (n: number | null) => (n === null ? "" : n.toLocaleString("en-IN"));
  const [text, setText] = useState(show(value));
  const [lastValue, setLastValue] = useState(value);
  // Resync when the value changes from outside (e.g. "Try Demo").
  if (value !== lastValue) {
    setLastValue(value);
    if (parseMoneyInput(text) !== value) setText(show(value));
  }
  const parsed = parseMoneyInput(text);
  const invalid = text.trim() !== "" && parsed === null;
  return (
    <Field
      label={`${label}${required ? " *" : ""}`}
      htmlFor={id}
      badge={badge}
      error={
        invalid
          ? "Enter an amount like 200000, 2,00,000 or 75 lakh"
          : highlight && parsed === null
            ? "Required for the analysis"
            : null
      }
      hint={
        parsed !== null
          ? `${formatINR(parsed)}${parsed >= 1e5 ? ` · ${inrWords(parsed)}` : ""}`
          : hint
      }
    >
      <input
        id={id}
        inputMode="text"
        value={text}
        placeholder={placeholder ?? "e.g. 2,00,000 or 2 lakh"}
        onChange={(e) => {
          setText(e.target.value);
          const p = parseMoneyInput(e.target.value);
          if (e.target.value.trim() === "" || p !== null) {
            setLastValue(p);
            onChange(p);
          }
        }}
        className={cn(
          inputClass,
          (invalid || (highlight && parsed === null)) && "border-text-critical/60",
        )}
      />
    </Field>
  );
}

export function NumberInput({
  label,
  value,
  onChange,
  suffix,
  min,
  max,
  step,
  placeholder,
  hint,
  badge,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  suffix?: string;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  hint?: ReactNode;
  badge?: ReactNode;
}) {
  const id = useId();
  return (
    <Field label={label} htmlFor={id} hint={hint} badge={badge}>
      <div className="relative">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          value={value ?? ""}
          min={min}
          max={max}
          step={step ?? "any"}
          placeholder={placeholder}
          onChange={(e) => {
            const v = e.target.value === "" ? null : Number(e.target.value);
            onChange(v === null || Number.isFinite(v) ? v : null);
          }}
          className={cn(inputClass, suffix && "pr-14")}
        />
        {suffix ? (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground">
            {suffix}
          </span>
        ) : null}
      </div>
    </Field>
  );
}
