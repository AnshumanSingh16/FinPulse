"use client";

import { ArrowDownLeft, CalendarHeart, Crown, HandCoins, PartyPopper, ShoppingBag, TrendingDown, TrendingUp, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { cx } from "./ui";

export interface StoryCard {
  kind: string;
  title: string;
  body: string;
  change?: number | null;
  positive?: boolean;
}

const LOOK: Record<string, { grad: string; I: React.ElementType }> = {
  sales: { grad: "grad-hero", I: TrendingUp },
  best_day: { grad: "grad-sunset", I: CalendarHeart },
  top_customer: { grad: "grad-ocean", I: Crown },
  collected: { grad: "grad-mint", I: ArrowDownLeft },
  spend: { grad: "grad-berry", I: ShoppingBag },
  udhaar: { grad: "grad-violet", I: HandCoins },
  net: { grad: "grad-night", I: PartyPopper },
  empty: { grad: "grad-night", I: CalendarHeart },
};

/** Instagram-style "Your week" — tap to advance, auto-plays. */
export function StoryViewer({ cards, title, range, onClose }: { cards: StoryCard[]; title: string; range: string; onClose: () => void }) {
  const [i, setI] = useState(0);
  const next = useCallback(() => (i < cards.length - 1 ? setI(i + 1) : onClose()), [i, cards.length, onClose]);
  const prev = () => setI((x) => Math.max(0, x - 1));
  useEffect(() => {
    const tmr = setTimeout(next, 4500);
    const k = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", k);
    return () => {
      clearTimeout(tmr);
      window.removeEventListener("keydown", k);
    };
  }, [i, next, onClose]);
  const c = cards[i];
  const look = LOOK[c.kind] ?? LOOK.net;
  const Icon = c.kind === "net" && c.positive === false ? TrendingDown : look.I;
  return (
    <div className="fixed inset-0 z-[70] grid place-items-center bg-black/70 p-0 sm:p-6" role="dialog" aria-modal aria-label={title}>
      <div className={cx("relative flex h-full w-full flex-col overflow-hidden sm:h-[640px] sm:max-w-sm sm:rounded-[2rem]", look.grad)}>
        <div className="flex gap-1 p-3">
          {cards.map((_, n) => (
            <div key={n} className="h-1 flex-1 overflow-hidden rounded-full bg-white/30">
              {n < i && <div className="h-full w-full bg-white" />}
              {n === i && <div key={i} className="story-bar h-full bg-white" style={{ animationDuration: "4.5s" }} />}
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between px-4">
          <div>
            <p className="text-sm font-semibold">{title}</p>
            <p className="text-xs text-white/70">{range}</p>
          </div>
          <button onClick={onClose} className="rounded-full p-2 hover:bg-white/15" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        <div className="flex flex-1 flex-col justify-center px-8 pb-16">
          <span className="float glass mb-8 grid size-20 place-items-center rounded-3xl">
            <Icon className="size-10" aria-hidden />
          </span>
          <h3 key={i} className="rise text-3xl leading-tight font-bold tracking-tight">{c.title}</h3>
          {c.body && <p key={`b${i}`} className="rise rise-1 mt-3 text-lg text-white/85">{c.body}</p>}
          {c.change != null && (
            <span className="rise rise-2 glass mt-5 inline-flex w-fit items-center gap-1 rounded-full px-3 py-1 text-sm font-semibold">
              {c.change >= 0 ? <TrendingUp className="size-4" /> : <TrendingDown className="size-4" />} {c.change >= 0 ? "+" : ""}
              {c.change.toFixed(0)}%
            </span>
          )}
        </div>
        <button className="absolute inset-y-24 left-0 w-1/3" onClick={prev} aria-label="Previous" />
        <button className="absolute inset-y-24 right-0 w-2/3" onClick={next} aria-label="Next" />
      </div>
    </div>
  );
}
