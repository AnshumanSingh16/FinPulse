"use client";

import { AlertTriangle, ArrowUp, BookUser, Bot, Brain, Coins, Lightbulb, Mic, Plus, Scissors, Sparkles, Stethoscope, Store, Target, TrendingUp, Wallet } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useContext, useEffect, useRef, useState } from "react";
import { AgentAnswer, type AgentResult, applyEvent, emptyLive, type Live, LiveCard, MemorySheet, streamAgent } from "@/components/agent";
import { AiModeChip, AiSetupSheet } from "@/components/ai-setup";
import { DataVersion } from "@/components/data-version";
import { Button, cx } from "@/components/ui";
import { useT } from "@/lib/i18n";

type Answer = AgentResult & { conversation_id: string };
type Msg = { role: "user"; text: string } | { role: "assistant"; data: Answer } | { role: "error"; text: string };

const MISSIONS = [
  { I: Stethoscope, grad: "grad-hero", title: "Daily check-up", sub: "I review everything and prepare today's actions", q: "Run my daily check-up", q_hi: "मेरा रोज़ का चेक-अप करो" },
  { I: Coins, grad: "grad-violet", title: "Collect my money", sub: "I find who owes you and draft reminders", q: "Help me collect my money", q_hi: "मेरी उधारी वसूलने में मदद करो" },
  { I: Scissors, grad: "grad-sunset", title: "Cut my costs", sub: "I find what's rising and set budgets", q: "Help me cut my costs", q_hi: "मेरा खर्च कम करने में मदद करो" },
];

const CAPABILITIES = [
  { I: Lightbulb, grad: "grad-ocean", title: "Plan my day", q: "What should I do today?", q_hi: "आज मुझे क्या करना चाहिए?" },
  { I: BookUser, grad: "grad-violet", title: "Khata & udhaar", q: "Who owes me money, and who pays late?", q_hi: "किस पर उधारी बाकी है, और कौन देर से चुकाता है?" },
  { I: TrendingUp, grad: "grad-mint", title: "Profit & costs", q: "Am I making money? Why did costs go up last month?", q_hi: "क्या मैं मुनाफ़ा कमा रहा हूँ? पिछले महीने खर्च क्यों बढ़ा?" },
  { I: Wallet, grad: "grad-ocean", title: "Cash ahead", q: "Will I have enough cash for the next 3 months?", q_hi: "अगले 90 दिन का कैश अनुमान बताओ" },
  { I: Target, grad: "grad-sunset", title: "What-ifs", q: "Can I raise prices by 5%?", q_hi: "दाम 5% बढ़ाऊँ तो?" },
  { I: Store, grad: "grad-berry", title: "Do it for me", q: "Add a sale of ₹500 cash", q_hi: "₹500 की नकद बिक्री जोड़ो" },
];

const MORE = [
  "Who are my best customers?",
  "How did this week go?",
  "What's my health score?",
  "How much GST should I keep aside?",
  "Should I hire a helper for ₹15,000 a month?",
  "Shree Ganesh promised to pay ₹89,000 by 10 Oct",
  "Remember that Ramesh is my brother — never remind him",
  "Save ₹60,000 for a new fridge by March",
];
const MORE_HI = [
  "मेरे सबसे अच्छे ग्राहक कौन हैं?",
  "इस हफ़्ते कैसा रहा?",
  "मेरा सेहत स्कोर क्या है?",
  "GST के लिए कितना अलग रखूँ?",
  "₹15,000 महीने पर हेल्पर रखूँ?",
  "Metro Foods को याद दिलाओ",
];

export default function AskPage() {
  return (
    <Suspense>
      <Ask />
    </Suspense>
  );
}

function Ask() {
  const { t, lang } = useT();
  const [listening, setListening] = useState(false);
  const params = useSearchParams();
  const { state } = useContext(DataVersion);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [live, setLive] = useState<Live | null>(null);
  const [setup, setSetup] = useState(false);
  const [memory, setMemory] = useState(false);
  const conv = useRef<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const sentQ = useRef(false);
  const busy = live !== null;

  // a new chat when the owner switches between the demo and their own books
  useEffect(() => {
    setMsgs([]);
    conv.current = null;
  }, [state?.source]);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [msgs, live]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setLive(emptyLive());
    try {
      const a = await streamAgent<Answer>("/api/ask/stream", { question: q, conversation_id: conv.current }, (e) => setLive((l) => (l ? applyEvent(l, e) : l)), lang, "/api/ask");
      conv.current = a.conversation_id;
      setMsgs((m) => [...m, { role: "assistant", data: a }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setLive(null);
    }
  };

  useEffect(() => {
    const q = params.get("q");
    if (q && !sentQ.current) {
      sentQ.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const lastAssistant = [...msgs].reverse().find((m) => m.role === "assistant") as { role: "assistant"; data: Answer } | undefined;

  return (
    <div className="flex min-h-[calc(100dvh-8.5rem)] flex-col lg:min-h-[calc(100dvh-3rem)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="grad-hero grid size-9 place-items-center rounded-xl text-[#ffd27a]">
            <Sparkles className="size-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-lg leading-tight">{t("Ask FinPilot")}</h1>
            <p className="text-xs text-muted">{t("Your shop assistant")}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <AiModeChip onClick={() => setSetup(true)} />
          <Button size="sm" variant="secondary" onClick={() => setMemory(true)} aria-label={t("Memory")}>
            <Brain className="size-4" /> <span className="hidden sm:inline">{t("Memory")}</span>
          </Button>
          {msgs.length > 0 && (
            <Button size="sm" variant="secondary" onClick={() => { setMsgs([]); conv.current = null; }} disabled={busy} aria-label={t("New chat")}>
              <Plus className="size-4" /> <span className="hidden sm:inline">{t("New chat")}</span>
            </Button>
          )}
        </div>
      </div>

      <div className="flex-1 space-y-5 pb-6">
        {msgs.length === 0 && !busy && <Welcome onAsk={send} onSetup={() => setSetup(true)} />}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <p className="max-w-[85%] rounded-3xl rounded-br-lg bg-brand px-4 py-2.5 text-on-brand shadow-sm sm:max-w-[70%]">{m.text}</p>
            </div>
          ) : m.role === "error" ? (
            <div key={i} className="flex items-start gap-2 rounded-2xl bg-bad-50 p-4 text-sm text-bad">
              <AlertTriangle className="size-5 shrink-0" /> {m.text}
            </div>
          ) : (
            <AgentAnswer key={i} a={m.data} conversation={m.data.conversation_id} />
          ),
        )}
        {live && <LiveCard live={live} />}
        {!busy && lastAssistant && lastAssistant.data.suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2 pl-1">
            {lastAssistant.data.suggestions.map((s) => (
              <button key={s} onClick={() => send(s)} className="rounded-full border border-brand/30 bg-brand-50 px-3.5 py-1.5 text-sm font-medium text-brand transition hover:border-brand">
                {s}
              </button>
            ))}
          </div>
        )}
        <div ref={end} />
      </div>

      <div className="sticky bottom-16 z-20 -mx-4 bg-gradient-to-t from-canvas via-canvas to-canvas/0 px-4 pt-4 pb-4 sm:-mx-6 sm:px-6 lg:bottom-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="card flex items-end gap-2 rounded-3xl p-2 pl-5"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder={t("Ask anything…")}
            className="max-h-36 min-h-10 flex-1 resize-none bg-transparent py-2.5 outline-none placeholder:text-muted"
            aria-label={t("Your question")}
          />
          <button
            type="button"
            onClick={() => {
              const W = window as unknown as { SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any }; // eslint-disable-line @typescript-eslint/no-explicit-any
              const SR = W.SpeechRecognition ?? W.webkitSpeechRecognition;
              if (!SR) return;
              const r = new SR();
              r.lang = lang === "hi" ? "hi-IN" : "en-IN";
              r.onresult = (e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => send(e.results[0][0].transcript);
              r.onend = () => setListening(false);
              setListening(true);
              r.start();
            }}
            className={cx("grid size-10 shrink-0 place-items-center rounded-full transition", listening ? "animate-pulse bg-bad text-white" : "text-ink-2 hover:bg-surface-2")}
            aria-label={t("Speak your question")}
          >
            <Mic className="size-5" />
          </button>
          <button type="submit" disabled={!input.trim() || busy} className="grid size-10 shrink-0 place-items-center rounded-full bg-brand text-on-brand transition disabled:opacity-40" aria-label={t("Send")}>
            <ArrowUp className="size-5" />
          </button>
        </form>
        <p className="mt-2 text-center text-xs text-muted">
          {t(state?.ai.enabled
            ? "AI agent: your question and the figures its tools work out are sent to the AI provider. Your files are not."
            : "Built-in answers: nothing leaves this computer.")}{" "}
          {t("Nothing is saved or sent until you confirm.")} {t("Not financial advice.")}
        </p>
      </div>
      <AiSetupSheet open={setup} onClose={() => setSetup(false)} />
      <MemorySheet open={memory} onClose={() => setMemory(false)} />
    </div>
  );
}

function Welcome({ onAsk, onSetup }: { onAsk: (q: string) => void; onSetup: () => void }) {
  const { t, lang } = useT();
  const { state } = useContext(DataVersion);
  return (
    <div className="mx-auto max-w-3xl pt-4 sm:pt-6">
      {state && !state.ai.enabled && (
        <div className="mb-6 flex flex-wrap items-center gap-4 rounded-3xl border border-dashed border-brand/40 bg-brand-50 p-4">
          <span className="grid size-10 place-items-center rounded-2xl bg-surface text-brand shadow-sm">
            <Bot className="size-5" />
          </span>
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-semibold text-ink">{state.ai.has_key ? t("The AI agent is paused") : t("Answers now come from built-in rules")}</p>
            <p className="hidden text-ink-2 sm:block">{t("They work offline for common questions. Turn on the AI agent to ask anything in your own words — it plans, uses 28 tools and checks every figure.")}</p>
          </div>
          <Button size="sm" onClick={onSetup}>
            <Sparkles className="size-4" /> {state.ai.has_key ? t("Turn AI back on") : t("Set up AI")}
          </Button>
        </div>
      )}
      <div className="text-center">
        <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("What can I help with today?")}</h2>
        <p className="mx-auto mt-2 max-w-xl text-ink-2">
          {t("I look through your khata, bank and bills, run the numbers with tested calculations, check every figure, and can prepare entries and reminders for you to confirm.")}
        </p>
      </div>
      <p className="mt-6 mb-2 text-xs font-semibold tracking-wide text-ink-2 uppercase">{t("Give me a mission")}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        {MISSIONS.map(({ I, grad, title, sub, q, q_hi }) => (
          <button key={title} onClick={() => onAsk(lang === "hi" ? q_hi : q)} className={cx("group flex flex-col gap-3 rounded-3xl p-4 text-left shadow-md shadow-black/10 transition hover:-translate-y-0.5", grad)}>
            <span className="glass grid size-10 place-items-center rounded-2xl">
              <I className="size-5" aria-hidden />
            </span>
            <span>
              <span className="block font-semibold">{t(title)}</span>
              <span className="mt-0.5 block text-sm text-white/80">{t(sub)}</span>
            </span>
          </button>
        ))}
      </div>
      <p className="mt-6 mb-2 text-xs font-semibold tracking-wide text-ink-2 uppercase">{t("Or ask")}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {CAPABILITIES.map(({ I, grad, title, q, q_hi }) => (
          <button key={title} onClick={() => onAsk(lang === "hi" ? q_hi : q)} className="card group flex flex-col gap-3 p-4 text-left transition hover:-translate-y-0.5 hover:border-brand/40">
            <span className={cx("grid size-10 place-items-center rounded-2xl", grad)}>
              <I className="size-5" aria-hidden />
            </span>
            <span>
              <span className="block font-semibold text-ink">{t(title)}</span>
              <span className="mt-0.5 block text-sm text-ink-2">“{lang === "hi" ? q_hi : t(q)}”</span>
            </span>
          </button>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {(lang === "hi" ? MORE_HI : MORE).map((s) => (
          <button key={s} onClick={() => onAsk(s)} className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-left text-sm text-ink-2 transition hover:border-brand hover:text-brand">
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

