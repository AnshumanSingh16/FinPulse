# The FinPulse demo: Sharma Electricals

A deterministic, resettable demo of the whole product on one story. Every figure on screen is
computed live by the deterministic engines from seeded synthetic data; the same data always gives
the same figures, and `make demo-reset` restores the exact starting state.

## The story

Sharma Electricals is an electrical goods shop in Lucknow that also supplies builders. It has
**limited traditional credit history**: one small equipment loan from its bank, always paid on
time, is all a credit bureau would see.

At first it looks healthy: revenue is growing, every bill and instalment is paid on time, and its
Financial Health is in the Sound band. Underneath, its largest customer, Shree Ganesh Builders,
has been scaling up a housing project — buying more and more, and paying a little later every two
months. So:

- revenue is **still growing** (+10.9% over the last three months);
- **receivables are increasing** (₹10.2 lakh → ₹14.8 lakh in three months; more than double since
  January);
- **collection time is increasing** (36.1 → 45.8 receivable days);
- **cash reserves are declining** (30-day average ₹8,13,593 → ₹6,98,191);
- **one customer is a large share of revenue** (36.7%, up from 26.5% in March).

FinPulse flags it before anything has gone wrong.

## What the demo shows

```
Financial Passport     Financial Health: 79.0/100 (Sound) — a prototype profile, not a credit score
Current risk           MEDIUM (early-warning index 22/100)
Early warning          Liquidity deterioration
Main evidence          revenue +10.9% · receivables ₹14,82,538 (was ₹10,18,669) · 45.8 receivable
                       days (was 36.1) · average cash ₹6,98,191 (was ₹8,13,593) · Shree Ganesh
                       Builders 36.7% of revenue · repayment record 100% on time (the other side)
Stress test            Largest customer delays payment by 60 days
                       (₹9,25,725 withheld from Oct 2026, received in Dec 2026)
Result                 Six-month risk Low → High · lowest cash ₹5.5 lakh → −₹2.5 lakh (Nov 2026)
                       · projected Financial Health 77.7 → 76.2 · a 90-day delay exhausts the
                       overdraft (funds run out ~16 Dec 2026)
Recommended actions    (from the AI investigation) ask the builder for a payment schedule and
                       confirm its project's status · set a credit limit or ask for part-advances ·
                       keep the ₹5 lakh overdraft as a buffer and track cash weekly · re-run monthly
```

These figures are pinned by `apps/api/tests/demo/test_story.py`; if a change to the generator, a
rule or the scenario moves them, the tests fail.

## Running it

```bash
make dev           # API on :8000, web on :3000
make demo-reset    # restore the exact demo state (also: the "Reset demo" button on /demo)
```

Open **http://localhost:3000/demo**. It shows the story, a six-step walkthrough (each step opens
the right view), and the brief above.

`make demo-reset` (`scripts/demo-reset.sh` → `finpulse demo reset`) re-seeds every synthetic
entity from its spec and seed — the printed fingerprints are pinned by the tests — and asks the
running API to forget its investigations. The **Reset demo** button calls the same reset through
`POST /api/v1/demo/reset`. Both refuse in production (`FINPULSE_ENV=production`) or when
`DEMO_ENABLED=false`.

## The walkthrough

1. **At first, a healthy business** — Financial Passport: 79.0 (Sound); repayment capacity 99.4.
2. **FinPulse looks underneath** — Financial Health: revenue up, receivables, receivable days and
   customer concentration up, cash down.
3. **The early warning** — Early Warning Center: medium risk, led by *Liquidity deterioration*.
   Point out the last sentence of the warning: the liquidity ratio (1.33×) counts the unpaid
   invoices as liquid, so it does not show the problem.
4. **Stress test** — opens with *Largest customer delays payment by 60 days* selected and run:
   Low → High, and the account goes overdrawn in Nov 2026.
5. **AI investigation** — *Run demo investigation*. The eight-step timeline fills in live:
   evidence collection, four specialists (in parallel), red-team challenge, evidence verification,
   final assessment. Then the Investigation Report.
   - The **Credit Intelligence Agent** rates the risk *low* (a spotless repayment record); the
     others rate it *elevated*. The orchestrator detects the disagreement deterministically.
   - The **Red-Team Agent** must challenge the significant assessments. It brings the evidence
     that weakens the risk conclusion: every obligation paid on time, nothing more than a month
     overdue (₹11,14,304 of the ₹14,82,538 is not yet due), a 1.33× liquidity ratio, and a
     low-risk six-month outlook without a shock. It also challenges the credit view: a clean record
     shows willingness to pay, not capacity under stress.
   - The **Senior Financial Intelligence Agent** rules on each challenge (risk challenge
     *partially upheld*: medium, not high; credit challenge *upheld*) and writes the assessment and
     the recommended actions.
6. **The brief** — back on /demo: everything above on one page.

## The AI part in the demo: a script, clearly labelled

There is no API key in a demo environment, and a demo must be repeatable, so the investigation
runs in **demo mode** (`POST …/investigations` with `{"mode": "demo"}`, or `finpulse investigate
run --demo`):

- The real orchestrator, verifier, disagreement detection, red-team requirements, evidence
  verification stage and confidence rules all run unchanged.
- Only the language model is replaced, by `finpulse.demo.DemoScriptLLM`: for each agent it returns
  an analysis **written in advance for this story**. Every number in it is read from the evidence
  in that agent's own prompt (each agent only sees its slice of the evidence pack), so it passes
  the same verifier as a model's output — all seven agents pass on the first attempt with nothing
  pruned (`tests/demo/test_script.py`).
- Answers are paced (`DEMO_SCRIPT_PACE` seconds × a per-agent factor; `0` for none) so the
  timeline can be watched.
- The record says so: `ai_mode = "demo_script"`, each agent run's `model` is
  `finpulse-demo-script-1`, and the UI shows "Demo script, not a live model" on the run, the
  timeline, the report and the brief.
- The script refuses any entity other than Sharma Electricals.

With `ANTHROPIC_API_KEY` set, *Live run with the language model* runs the same workflow with Claude.
Its wording will differ; the deterministic figures will not.

## Why the numbers are consistent

- One source: the scenario spec (`synthetic/scenarios/sharma_electricals.py`) and its seed. The
  generator is deterministic and its output is reconciled (every invoice payment is a bank credit,
  receivables roll forward, and so on — see SYNTHETIC_DATA.md).
- Every figure is computed by the engines at request time; the frontend formats but never
  calculates; the demo script quotes the engines' evidence and is verified.
- Rounding is done once: for example, the liquidity-deterioration rule stores whole-rupee averages
  so the warning text, its evidence and the brief show the same ₹6,98,191.

## Other entities

The portfolio has five more synthetic entities, including **Mehra Lighting & Electricals**, which
keeps FinPulse's earlier, more severe story (a sudden collapse: critical risk, bounced
auto-debits, a clean bureau record). Demo mode does not cover them; the deterministic views do.
