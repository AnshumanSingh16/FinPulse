"use client";

import { Bot, ExternalLink, KeyRound, Lock, PauseCircle, PlayCircle, ShieldCheck, Trash2 } from "lucide-react";
import { useContext, useState } from "react";
import { del, post } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { AiStatus } from "@/lib/types";
import { DataVersion } from "./data-version";
import { useToast } from "./fx";
import { Button, cx, Pill, Segmented, Sheet } from "./ui";

/** Turn the AI agent on with the owner's own Anthropic key. The key is stored only in the local .env file. */
export function AiSetupSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useT();
  const { state, refresh } = useContext(DataVersion);
  const toast = useToast();
  const ai = state?.ai;
  const [provider, setProvider] = useState<"gemini" | "anthropic">("gemini");
  const [key, setKey] = useState("");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      await post<AiStatus>("/api/ai/key", { key: key.trim(), provider, consent: agree });
      setKey("");
      refresh();
      toast.show({ text: t("AI agent is on"), tone: "good" });
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const pause = async (paused: boolean) => {
    await post<AiStatus>("/api/ai/pause", { paused });
    refresh();
  };
  const remove = async () => {
    await del<AiStatus>("/api/ai/key");
    refresh();
    toast.show({ text: t("Key removed from this computer") });
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("AI agent")}>
      {ai?.has_key ? (
        <div className="space-y-4">
          <div className={cx("flex items-start gap-3 rounded-2xl p-4", ai.enabled ? "bg-good-50" : "bg-caution-50")}>
            <Bot className={cx("mt-0.5 size-5 shrink-0", ai.enabled ? "text-good" : "text-caution")} />
            <div className="text-sm">
              <p className="font-semibold text-ink">{ai.enabled ? t("The AI agent is on") : t("The AI agent is paused")}</p>
              <p className="text-ink-2">
                {ai.source === "app" ? t("Key {hint} is saved on this computer only.", { hint: ai.key_hint ?? "" }) : t("Using the key from your computer's settings ({hint}).", { hint: ai.key_hint ?? "" })}{" "}
                {t("{provider} · model {model}", { provider: ai.provider_label, model: ai.model })}
              </p>
            </div>
          </div>
          <Privacy provider={ai.provider} />
          <div className="flex flex-wrap gap-2">
            {ai.enabled ? (
              <Button variant="secondary" onClick={() => pause(true)}>
                <PauseCircle className="size-4" /> {t("Pause AI (use built-in answers)")}
              </Button>
            ) : (
              <Button onClick={() => pause(false)}>
                <PlayCircle className="size-4" /> {t("Turn AI back on")}
              </Button>
            )}
            {ai.source === "app" && (
              <Button variant="ghost" className="text-bad hover:bg-bad-50" onClick={remove}>
                <Trash2 className="size-4" /> {t("Remove key")}
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-ink-2">
            {t("Without AI, Ask uses FinPilot's built-in rules — they work offline and cover common questions. With an API key, an AI agent plans each question, uses 28 tools on your records, checks every figure and can prepare entries, reminders, goals and budgets for you to confirm.")}
          </p>
          <Segmented
            value={provider}
            onChange={(v) => { setProvider(v); setErr(null); }}
            options={[
              { value: "gemini", label: t("Google Gemini (free)") },
              { value: "anthropic", label: t("Anthropic Claude") },
            ]}
            className="flex w-full [&>button]:flex-1"
          />
          <ol className="space-y-3 text-sm">
            <li className="flex gap-3">
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand">1</span>
              <span>
                {provider === "gemini"
                  ? t("Get a free key from Google AI Studio: sign in with your Google account and click “Create API key”.")
                  : t("Get a key from the Anthropic Console (usage is billed by Anthropic to your account).")}{" "}
                <a href={provider === "gemini" ? "https://aistudio.google.com/apikey" : "https://console.anthropic.com/settings/keys"} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 font-semibold text-brand underline underline-offset-2">
                  {provider === "gemini" ? "aistudio.google.com/apikey" : "console.anthropic.com"} <ExternalLink className="size-3.5" />
                </a>
              </span>
            </li>
            <li className="flex gap-3">
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand">2</span>
              <div className="flex-1 space-y-2">
                <span>{t("Paste it here:")}</span>
                <div className="flex h-12 items-center gap-2 rounded-2xl border border-line bg-surface px-4 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/15">
                  <KeyRound className="size-4 text-muted" />
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    placeholder={provider === "gemini" ? "AIza…" : "sk-ant-…"}
                    className="w-full bg-transparent font-mono text-sm outline-none placeholder:text-muted"
                    aria-label={t("API key")}
                  />
                </div>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand">3</span>
              <div className="flex-1 space-y-2">
                <Privacy provider={provider} />
                <label className="flex cursor-pointer items-start gap-2.5 rounded-2xl border border-line p-3">
                  <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-0.5 size-4 accent-[var(--color-brand)]" />
                  <span>{provider === "gemini" ? t("I understand what is sent to Google when AI is on.") : t("I understand what is sent to Anthropic when AI is on.")}</span>
                </label>
              </div>
            </li>
          </ol>
          {err && <p className="rounded-2xl bg-bad-50 p-3 text-sm text-bad">{err}</p>}
          <Button size="lg" className="w-full" disabled={!key.trim() || !agree || busy} onClick={save}>
            <ShieldCheck className="size-5" /> {busy ? t("Checking the key…") : t("Check key and turn on AI")}
          </Button>
          <p className="flex items-center justify-center gap-1.5 text-xs text-muted">
            <Lock className="size-3.5" /> {t("The key is checked with a free call and saved in the .env file on this computer — never in the app's code.")}
          </p>
        </div>
      )}
    </Sheet>
  );
}

function Privacy({ provider }: { provider: "gemini" | "anthropic" }) {
  const { t } = useT();
  return (
    <div className="rounded-2xl bg-surface-2 p-3 text-xs leading-relaxed text-ink-2">
      <p className="mb-1 font-semibold text-ink">{t("What leaves this computer when AI is on")}</p>
      <p>
        {provider === "gemini"
          ? t("Your question and the results of the tools the agent runs — amounts, dates, and customer and supplier names — are sent to Google to write the answer. Your uploaded files and full records are not sent. With AI off, nothing leaves this computer.")
          : t("Your question and the results of the tools the agent runs — amounts, dates, and customer and supplier names — are sent to Anthropic to write the answer. Your uploaded files and full records are not sent. With AI off, nothing leaves this computer.")}
      </p>
      {provider === "gemini" && (
        <p className="mt-2 rounded-xl bg-caution-50 p-2 text-caution">
          {t("Free tier: Google's terms allow it to use what you send on the free tier to improve its products, and people may review it. Try it on the demo shop; for your real books, consider a paid (billing-enabled) key.")}
        </p>
      )}
    </div>
  );
}

export function AiModeChip({ onClick }: { onClick: () => void }) {
  const { t } = useT();
  const { state } = useContext(DataVersion);
  const on = !!state?.ai.enabled;
  return (
    <button onClick={onClick} className="inline-flex items-center gap-1.5" aria-label={t("AI agent")}>
      <Pill tone={on ? "good" : "neutral"} className="border border-line">
        <span className={cx("size-1.5 rounded-full", on ? "bg-good" : "bg-muted")} />
        {on ? t("AI agent on") : t("Built-in answers")}
      </Pill>
    </button>
  );
}
