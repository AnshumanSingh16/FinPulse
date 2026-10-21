"use client";

import { ArrowRight, HelpCircle } from "lucide-react";
import Link from "next/link";
import { useContext, useEffect, useState } from "react";
import { DataVersion } from "@/components/data-version";
import { cx } from "@/components/ui";
import { get } from "@/lib/api";

interface Track { status: string; weeks: number; low_better_than_flat_pct: number | null; dips: number; dips_flagged: number; brier: number; range_coverage: number }
type QA = { q: string; a: React.ReactNode; show?: { href: string; label: string } };

const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

/** The questions judges (and owners) ask, answered plainly — with a link to see each answer working. */
export default function AboutPage() {
  const { state } = useContext(DataVersion);
  const [tr, setTr] = useState<Track | null>(null);
  useEffect(() => {
    get<Track>("/api/track-record").then(setTr).catch(() => setTr(null));
  }, [state?.business]);
  const biz = state?.business.replace(" (fictional)", "") ?? "this business";

  const groups: { title: string; items: QA[] }[] = [
    {
      title: "The problem",
      items: [
        { q: "What problem are you solving?", a: "Most small businesses that close aren't unprofitable — they run out of cash. A client pays late, salaries and rent land in the same week, a deposit comes due. FinPilot looks 90 days ahead, finds the crunch before it happens, and prepares the fix for the owner to approve." },
        { q: "Who is it for?", a: "Owners of India's small businesses — shops, manufacturers, agencies, cafés, clinics, online sellers — who have no finance person. It speaks English and Hindi, takes voice, and works on a phone or a laptop." },
        { q: "How big is the opportunity?", a: <>India has about <b>6.3 crore MSMEs</b> (Ministry of MSME, Annual Report 2020–21), and payments owed to MSMEs but delayed were estimated at about <b>₹10.7 lakh crore</b> (GAME &amp; FISME, 2022). Late money is exactly what FinPilot chases first.</> },
        { q: "Why now?", a: "UPI and GST have made small-business cash flows digital; RBI's Account Aggregator framework lets a business share its bank data with consent; and language models can finally explain money in plain words. A CFO in every small business's pocket is now possible." },
      ],
    },
    {
      title: "What makes it agentic",
      items: [
        { q: "What exactly is 'agentic' here — isn't it a chatbot?", a: "Eleven agents, each with one job (forecasting, risk, collections, payables, spending, tax, deals, planning, financing, auditing, strategy). They plan, act within limits (draft reminders, a supplier request, a bank letter), keep watching after you approve, learn from what customers actually do, and check each other's numbers. The chat is just how you talk to them.", show: { href: "/?do=fix", label: "Watch the agents work" } },
        { q: "Why many agents instead of one large language model?", a: "Money needs exact, repeatable arithmetic. Each specialist is small, deterministic and tested; the language model is used where language and creativity matter — explaining, and proposing new ideas — and every number it writes is checked against the agents' results. That makes it cheaper, explainable, and unable to invent money." },
        { q: "How does it choose a plan? Show me the reasoning.", a: "The planner scores every combination of possible moves exactly, plays the best ones out in 1,000 simulated futures built from each customer's own payment history, and picks the best odds — among plans that are about as safe, the one that asks least of you. An auditor re-runs the forecast to confirm the arithmetic. Open \"Why this plan?\" on the fix to see every alternative it compared.", show: { href: "/?do=fix", label: "See the fix and why" } },
        { q: "What happens after I approve — and if a customer still doesn't pay?", a: "Every move that depends on someone else gets a checkpoint and a Plan B. If the checkpoint is missed, the agents notice, prepare a firmer reminder, lower that customer's odds, re-plan with today's books and ask for your OK. On the demos you can fast-forward two weeks and watch it happen.", show: { href: "/?do=sim", label: "Fast-forward two weeks" } },
        { q: "Does it learn?", a: "Yes, from outcomes: each time a reminded customer pays (or doesn't), its chance of paying after a reminder is updated and the odds change. It also re-tests itself on your past weeks (the track record)." },
        { q: "Can it handle what the data can't know — Diwali, a big order, a planned purchase?", a: "Tell it. \"Tell me what's coming\" adds the event to every forecast, plan and affordability check from then on.", show: { href: "/?do=event", label: "Tell it what's coming" } },
      ],
    },
    {
      title: "Trust and safety",
      items: [
        { q: "How do we know it's accurate?", a: <>It tests itself: for every past week it rewinds the books, forecasts the next 30 days exactly as it does today, and compares with what really happened. For {biz}: {tr && tr.status === "ok" ? <><b>{pct(tr.low_better_than_flat_pct)}</b> closer on the tightest day than assuming the balance stays flat, <b>{tr.dips ? `${tr.dips_flagged} of ${tr.dips}` : "no"}</b> real dips flagged in advance, odds score <b>{tr.brier.toFixed(2)}</b> (0 is perfect) over {tr.weeks} weeks</> : "loading…"}. It also shows where it is weak — for example when its range of outcomes is too narrow.</>, show: { href: "/proof/", label: "Open the track record" } },
        { q: "Can the AI make up numbers?", a: "Every figure, date and record in an AI answer must match a result from the approved tools, or the answer is corrected or flagged — never shown as verified. Ideas the AI strategist proposes must be tested on your forecast before they are mentioned. Without an AI key, every answer comes from built-in, tested rules." },
        { q: "Will it move my money or contact my customers by itself?", a: "Never. It drafts — reminders, a supplier request, a letter to the bank — and you send them. It cannot pay, transfer or file anything. Every agent action and every decision you make is recorded; download the audit log any time from Settings.", show: { href: "/settings/", label: "Audit log and settings" } },
        { q: "Who is responsible if a suggestion is wrong?", a: "The owner decides; FinPilot shows its assumptions, its odds and its own track record so the owner can judge. It is decision support, not financial advice." },
      ],
    },
    {
      title: "Data and privacy",
      items: [
        { q: "Where does my data live?", a: "On your own computer. Nothing leaves it unless you switch AI on — and then only the figures needed for that one answer go to the AI provider you chose (Google Gemini or Anthropic Claude). Your files and full records are not sent. Remove your data or reset a demo in one tap." },
        { q: "Is it DPDP-ready (India's data protection law, 2023)?", a: "It is built around consent and data minimisation: AI is off until you agree to what is sent, data stays local by default, and deletion is one tap. That is a design choice, not a legal certification." },
        { q: "How does a business get its data in?", a: "Upload a bank statement (CSV or Excel) — columns are matched automatically; invoices and bills are optional. Or start from just today's balance and add sales and payments by chat or voice. Next: Account Aggregator consent and Tally import.", show: { href: "/data/", label: "Your data" } },
      ],
    },
    {
      title: "Business",
      items: [
        { q: "How does it make money?", a: "Proposed: free for a single business; a paid plan for accountants and multi-branch owners; and, with the owner's consent and costs shown side by side, referral fees when the Financing agent's backup (an overdraft, invoice discounting on platforms such as TReDS) is taken up with a partner lender. None of this is live yet." },
        { q: "How is it different from Khatabook, Vyapar, Tally or Zoho Books?", a: "Those record the past — a ledger or accounts for an accountant. FinPilot looks ahead and acts: it forecasts cash, finds the crunch, prepares the fix, and keeps watching. Western cash-forecasting tools (Float, Fathom) are built for accountants; FinPilot is built for the owner, in Hindi, with agents doing the work." },
        { q: "What does it cost to run?", a: "The engine — forecasts, simulations, planning, monitoring — runs locally with no AI cost. The language model is optional and only explains and proposes ideas; it works on a free Gemini key." },
      ],
    },
    {
      title: "Honest limits and what's next",
      items: [
        { q: "What doesn't it do yet?", a: "The demo businesses' histories are simulated and it hasn't been piloted with real businesses yet. There's no live bank connection or WhatsApp sending yet (messages open in your own WhatsApp). On some businesses its range of outcomes is too narrow — the track record says so. The AI paths are tested with a scripted model in the test suite." },
        { q: "What's next?", a: "A pilot with 20 businesses; Account Aggregator bank feeds; WhatsApp Business messages sent on approval; comparing lenders for the backup by cost; a GST-ready monthly pack for the CA." },
      ],
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl"><HelpCircle className="size-7 text-brand" /> Questions judges ask</h1>
        <p className="mt-1 text-ink-2">Plain answers about what FinPilot is, how its agents decide, and what it won&apos;t do — each with a link to see it working.</p>
      </div>
      {groups.map((g) => (
        <section key={g.title}>
          <h2 className="mb-2 text-xs font-semibold tracking-[0.14em] text-muted uppercase">{g.title}</h2>
          <div className="divide-y divide-line rounded-3xl border border-line bg-surface">
            {g.items.map((it, i) => <Item key={i} it={it} />)}
          </div>
        </section>
      ))}
    </div>
  );
}

function Item({ it }: { it: QA }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="px-5 py-4">
      <button onClick={() => setOpen(!open)} className="flex w-full items-start justify-between gap-3 text-left" aria-expanded={open}>
        <span className="serif text-lg leading-snug font-semibold">{it.q}</span>
        <span className={cx("mt-1 text-muted transition", open && "rotate-45")}>+</span>
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-[0.98rem] leading-relaxed text-ink-2">
          <p>{it.a}</p>
          {it.show && (
            <Link href={it.show.href} className="inline-flex items-center gap-1 text-sm font-semibold text-brand">
              {it.show.label} <ArrowRight className="size-4" />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
