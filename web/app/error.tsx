"use client";

import { useEffect } from "react";

/** Shown instead of Next's generic "This page couldn't load": the real error, and two ways out. */
export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  const startOver = () => {
    try {
      localStorage.removeItem("finpilot-lang");
      localStorage.removeItem("finpilot.theme");
    } catch {}
    window.location.href = "/";
  };
  return (
    <div className="mx-auto max-w-lg space-y-4 px-5 py-16">
      <h1 className="text-2xl">FinPilot hit a problem</h1>
      <p className="text-ink-2">Something broke while showing this page. Please send this message to whoever set up FinPilot:</p>
      <pre className="overflow-x-auto rounded-2xl bg-surface-2 p-4 text-sm whitespace-pre-wrap text-bad">{error.message || String(error)}{error.digest ? `\n(${error.digest})` : ""}</pre>
      <div className="flex flex-wrap gap-2">
        <button onClick={reset} className="h-10 rounded-full bg-brand px-5 text-sm font-semibold text-on-brand">Try again</button>
        <button onClick={startOver} className="h-10 rounded-full border border-line bg-surface px-5 text-sm font-semibold">Start over</button>
      </div>
    </div>
  );
}
