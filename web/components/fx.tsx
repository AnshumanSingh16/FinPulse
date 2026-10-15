"use client";

import { CheckCircle2, Undo2, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

/** Animate a number from its previous value to the new one. */
export function useCountUp(target: number | null | undefined, ms = 700) {
  const [v, setV] = useState(target ?? 0);
  const from = useRef(target ?? 0);
  useEffect(() => {
    if (target == null) return;
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setV(target);
      from.current = target;
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      const e = 1 - Math.pow(1 - p, 3);
      setV(a + (target - a) * e);
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const v = useCountUp(value);
  return <>{format(v)}</>;
}

/** A small canvas confetti burst — for cleared udhaar and reached goals. */
export function confetti() {
  if (typeof window === "undefined" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  const c = document.createElement("canvas");
  c.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:100";
  c.width = window.innerWidth;
  c.height = window.innerHeight;
  document.body.appendChild(c);
  const ctx = c.getContext("2d")!;
  const colors = ["#6a44ff", "#ff7a59", "#22c3a6", "#ffd166", "#f25fa0", "#2a78d6"];
  const parts = Array.from({ length: 140 }, () => ({
    x: c.width / 2 + (Math.random() - 0.5) * 120,
    y: c.height * 0.35,
    vx: (Math.random() - 0.5) * 14,
    vy: -Math.random() * 14 - 4,
    s: Math.random() * 6 + 4,
    r: Math.random() * Math.PI,
    vr: (Math.random() - 0.5) * 0.3,
    col: colors[Math.floor(Math.random() * colors.length)],
  }));
  let frame = 0;
  const draw = () => {
    ctx.clearRect(0, 0, c.width, c.height);
    for (const p of parts) {
      p.vy += 0.35;
      p.x += p.vx;
      p.y += p.vy;
      p.r += p.vr;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.r);
      ctx.fillStyle = p.col;
      ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2);
      ctx.restore();
    }
    if (++frame < 150) requestAnimationFrame(draw);
    else c.remove();
  };
  draw();
}

// ---------------------------------------------------------------- toasts

interface Toast {
  id: number;
  text: string;
  undo?: () => void;
  tone?: "good" | "bad";
}

const ToastCtx = createContext<{ show: (t: Omit<Toast, "id">) => void }>({ show: () => {} });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback((t: Omit<Toast, "id">) => {
    if (timer.current) clearTimeout(timer.current);
    setToast({ ...t, id: Date.now() });
    timer.current = setTimeout(() => setToast(null), t.undo ? 6000 : 3500);
  }, []);
  return (
    <ToastCtx.Provider value={{ show }}>
      {children}
      {toast && (
        <div key={toast.id} role="status" className="toast fixed bottom-24 left-1/2 z-[60] flex max-w-[92vw] items-center gap-3 rounded-2xl border border-line bg-elevated px-4 py-3 text-sm text-ink shadow-2xl lg:bottom-8">
          {toast.tone === "bad" ? <X className="size-4 shrink-0 text-red-300" /> : <CheckCircle2 className="size-4 shrink-0 text-emerald-300" />}
          <span className="min-w-0">{toast.text}</span>
          {toast.undo && (
            <button
              onClick={() => {
                toast.undo?.();
                setToast(null);
              }}
              className="ml-1 inline-flex shrink-0 items-center gap-1 rounded-full bg-white/15 px-3 py-1 font-semibold hover:bg-white/25"
            >
              <Undo2 className="size-3.5" /> Undo
            </button>
          )}
        </div>
      )}
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
