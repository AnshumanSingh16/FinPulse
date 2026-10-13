"use client";

import { RotateCcw, Save, Wand2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/personal/client";
import { PROFILE_LABELS, type ProfileField, type ProfileValues } from "@/lib/personal/schemas";

import { Field, MoneyInput, NumberInput } from "./fields";
import { usePersonal } from "./provider";
import { ConfirmDialog, Loading, Notice, PageTitle, Section, SourceBadge, inputClass } from "./ui";

export function ProfileEditor() {
  const { state, setState } = usePersonal();
  const [draft, setDraft] = useState<ProfileValues | null>(null);
  const [baseline, setBaseline] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  // (Re)seed the draft whenever the stored profile changes (save, demo, reset, document import).
  const stored = state ? JSON.stringify(state.profile.values) : null;
  if (state && stored !== baseline) {
    setBaseline(stored);
    setDraft({ ...state.profile.values });
  }
  if (!state || !draft) return <Loading label="Loading your profile…" />;

  const set = <K extends ProfileField>(k: K, val: ProfileValues[K]) =>
    setDraft({ ...draft, [k]: val });
  const badge = (k: ProfileField) => {
    const s = state.profile.sources[k];
    return s ? (
      <span title={s.note}>
        <SourceBadge kind={s.kind} />
      </span>
    ) : null;
  };
  const dirty = JSON.stringify(draft) !== stored;

  async function run(fn: () => Promise<typeof state>, ok: string) {
    setBusy(true);
    setMessage(null);
    try {
      setState((await fn())!);
      setMessage({ tone: "success", text: ok });
    } catch (e) {
      setMessage({ tone: "error", text: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        title="My finances"
        description="The facts FinPulse works from. Each value shows where it came from. FinPulse never asks for bank passwords, card PINs or OTPs."
        actions={
          <>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => run(api.loadDemo, "Fictional demo profile loaded.")}
            >
              <Wand2 /> Use demo profile
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setConfirmReset(true)}>
              <RotateCcw /> Reset
            </Button>
          </>
        }
      />
      <ConfirmDialog
        open={confirmReset}
        title="Reset all your data?"
        tone="danger"
        confirmLabel="Reset everything"
        busy={busy}
        onClose={() => setConfirmReset(false)}
        onConfirm={async () => {
          await run(api.reset, "All session data was reset.");
          setConfirmReset(false);
        }}
      >
        This clears your profile, analyses, next steps, documents and activity log for this browser
        session. It can&apos;t be undone.
      </ConfirmDialog>

      {message ? <Notice tone={message.tone}>{message.text}</Notice> : null}
      <Notice tone="info">
        Stored in server memory for this browser session only ({state.status.storage.toLowerCase()}
        ). No bank accounts are connected — figures are entered by you, loaded from the demo, or
        imported from documents you confirm.
      </Notice>

      <Section title="About you">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field
            label={PROFILE_LABELS.name}
            htmlFor="name"
            badge={badge("name")}
            hint="Optional — only used to greet you on Home"
          >
            <input
              id="name"
              className={inputClass}
              maxLength={40}
              autoComplete="given-name"
              value={draft.name ?? ""}
              onChange={(e) => set("name", e.target.value.trim() ? e.target.value : null)}
            />
          </Field>
        </div>
      </Section>

      <Section title="Income and spending">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(
            ["monthlyIncome", "monthlyExpenses", "existingEmis", "otherMonthlyObligations"] as const
          ).map((k) => (
            <MoneyInput
              key={k}
              label={PROFILE_LABELS[k]}
              value={draft[k]}
              onChange={(x) => set(k, x)}
              badge={badge(k)}
            />
          ))}
          <Field
            label={PROFILE_LABELS.incomeVariability}
            htmlFor="var"
            badge={badge("incomeVariability")}
          >
            <select
              id="var"
              className={inputClass}
              value={draft.incomeVariability ?? ""}
              onChange={(e) =>
                set(
                  "incomeVariability",
                  (e.target.value || null) as ProfileValues["incomeVariability"],
                )
              }
            >
              <option value="">Not specified</option>
              <option value="stable">Stable (salaried)</option>
              <option value="variable">Variable (freelance, commission, business)</option>
            </select>
          </Field>
        </div>
      </Section>

      <Section title="Savings, assets & obligations">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(["liquidSavings", "investments", "upcomingExpenses"] as const).map((k) => (
            <MoneyInput
              key={k}
              label={PROFILE_LABELS[k]}
              value={draft[k]}
              onChange={(x) => set(k, x)}
              badge={badge(k)}
              hint={
                k === "liquidSavings"
                  ? "Bank balance, FDs, liquid funds you could use quickly"
                  : k === "investments"
                    ? "Not counted as emergency money"
                    : undefined
              }
            />
          ))}
          <NumberInput
            label={PROFILE_LABELS.dependents}
            min={0}
            max={20}
            step={1}
            value={draft.dependents}
            onChange={(x) => set("dependents", x === null ? null : Math.round(x))}
            badge={badge("dependents")}
          />
          <NumberInput
            label={PROFILE_LABELS.emergencyBufferMonths}
            suffix="months"
            min={0}
            max={36}
            value={draft.emergencyBufferMonths}
            onChange={(x) => set("emergencyBufferMonths", x)}
            badge={badge("emergencyBufferMonths")}
          />
        </div>
        <Field label={PROFILE_LABELS.goals} htmlFor="goals" badge={badge("goals")}>
          <textarea
            id="goals"
            maxLength={500}
            rows={2}
            className={`${inputClass} h-auto py-2`}
            value={draft.goals ?? ""}
            onChange={(e) => set("goals", e.target.value || null)}
          />
        </Field>
      </Section>

      <div className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] flex justify-end lg:bottom-4">
        <Button
          disabled={!dirty || busy}
          className="h-10 px-5 shadow-lg"
          onClick={() => {
            const changed = Object.fromEntries(
              Object.entries(draft).filter(
                ([k, val]) => val !== state.profile.values[k as ProfileField],
              ),
            );
            void run(
              () => api.saveProfile(changed),
              "Profile saved. Changed fields are marked as entered by you.",
            );
          }}
        >
          <Save /> {dirty ? "Save profile" : "Saved"}
        </Button>
      </div>
      <p className="text-[12px] text-ink-400">
        Money fields accept 2,00,000 · 200000 · 2 lakh · 1.2 crore.
      </p>
    </div>
  );
}
