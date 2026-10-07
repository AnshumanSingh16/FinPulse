# Synthetic financial data

FinPulse's MVP runs on realistic, fictional financial histories instead of real bank
integrations. This document explains what the data contains, how it is produced, what is
guaranteed about it, and how to change or add scenarios.

Code: `apps/api/src/finpulse/synthetic/` (pure Python: no I/O, no clock, no LLM).
Loader and CLI: `apps/api/src/finpulse/persistence/seed.py`, `apps/api/src/finpulse/cli.py`.

## 1. The entities

| Code | Entity | Archetype | History | What happens |
|---|---|---|---|---|
| `sharma_electricals` | **Sharma Electricals**, Lucknow — electrical goods retail and contractor supply. **Primary demo** ([DEMO.md](DEMO.md)). | Strained MSME | 18 months, Apr 2025 – Sep 2026 | Thin credit history (one small bank equipment loan, always paid). Sound and growing through 2025 with ₹12–13 lakh in the bank. From Dec 2025 its largest customer, a builder, more than doubles its orders while paying a little later every two months; other customers drift later from June. Revenue keeps growing, but receivables more than double, collection time stretches from ~30 to ~46 days, cash falls to ~₹7.4 lakh and the builder reaches 37% of revenue. Nothing has gone wrong yet: medium risk, led by liquidity deterioration. |
| `mehra_lighting` | Mehra Lighting & Electricals, Kanpur — electrical goods retail and contractor supply | Deteriorating MSME | 18 months, Apr 2025 – Sep 2026 | Sound for seven months. From Nov 2025 its largest customer (a builder) pays ~45 days later, then almost stops ordering; copper-linked costs rise; walk-in sales decline; other customers slow down. Two digital loans that don't report to the bureau bridge the gap; drawings stop; suppliers are stretched; the account lives in its overdraft; digital-loan auto-debits bounce in Aug–Sep 2026. **The bureau record stays clean**: its only reported loan is still paid on time. |
| `kaveri_packaging` | Kaveri Packaging Solutions, Coimbatore — corrugated boxes | Healthy MSME | 15 months | Eight diversified, punctual customers; steady growth; equipment loan always paid on time; never overdrawn. |
| `annapurna_kitchen` | Annapurna Home Kitchen, Pune — cloud kitchen | Thin-file but healthy MSME | 12 months | One year old, has never borrowed, so a bureau has no record at all. Weekly delivery-platform payouts, a corporate catering contract and direct UPI orders, growing ~3.5% a month; cash buffer grows steadily. |
| `rapid_mobile_hub` | Rapid Mobile Hub, Delhi — mobile phones and accessories | High-risk MSME | 15 months | Thin margins and volatile sales; lives at its overdraft limit; heavy ATM withdrawals and online gaming spend; resellers pay late and in parts; four lenders; repeated auto-debit bounces throughout. |
| `ananya_rao_design` | Ananya Rao, Bengaluru — UX design consultant | Freelancer (individual) | 14 months | A monthly retainer, occasional large projects from a slow-paying UK studio, and a start-up client that sometimes pays in parts. Lumpy income, rent, SIP investing, quarterly advance tax, and a laptop loan repaid on time. |

All names, banks, lenders and platforms are fictional.

`finpulse synthetic summary sharma_electricals` prints the month-by-month picture. The primary
demo, month-end figures (₹ lakh, rounded):

| | 2025 | Sep 2026 |
|---|---|---|
| Monthly revenue | about 9.5 | 13.4 |
| Receivables outstanding | 5.6 (Apr) – 6.3 (Jan 2026) | 14.8 |
| Receivable days | about 30 | 45.8 |
| Cash balance | 12–13 | 7.4 |
| Largest customer's share of revenue (6 months) | 23% (Jan 2026) | 37% |
| Loans · bounces · bureau delinquencies | 1 bank loan · 0 · 0 | unchanged |

Mehra Lighting & Electricals keeps FinPulse's earlier, more severe demo story (identical
parameters and seed): sales fall from about ₹12.1 to ₹8.0 lakh a month after onset, the largest
customer's share drops from over 40% to under 15%, it borrows twice from unreported digital
lenders and its auto-debits bounce in Aug–Sep 2026, while the bureau still shows nothing.

## 2. Dataset structure

One run of a scenario produces a `Dataset` (`synthetic/model.py`). Loaded into PostgreSQL it maps
one-to-one onto these tables (DATA_MODEL.md §3.2, §3.2b, §3.3):

```
subjects ── synthetic_generations   (scenario, seed, generator version, ground truth, fingerprint)
   │
   ├── accounts ── transactions ─────────────── counterparties
   │                  ▲      ▲      ▲                (customers, platforms, suppliers, employees,
   │                  │      │      │                 landlord, utilities, lenders, tax, bank, owner)
   ├── invoices ── invoice_payments    (one payment ↔ one bank credit)
   ├── bills ───── bill_payments       (one payment ↔ one bank debit)
   ├── loans ───── loan_installments   (disbursement ↔ bank credit; paid EMI ↔ bank debit)
   ├── counter_sales                   (daily sales register → next-day UPI settlement, cash deposits)
   └── simulated_bureau_events         (evaluation only)
```

| Record | What it represents |
|---|---|
| **Transaction** | One bank statement line: date, signed amount in paise (+ credit / − debit), running balance, Indian-style narration (`NEFT CR …`, `UPI SETTL PAYZAP …`, `NACH DR … EMI 7/48`, `GST CHALLAN …`), channel, counterparty, and a **category label** (`income.customer_payment`, `expense.supplier`, `debt.emi`, `bank.bounce_charge`, …). Labels are simulation ground truth for evaluating the Phase 2 categoriser, which must infer them from the narration. |
| **Counter sale** | A day's walk-in takings, split into UPI and cash, with GST. |
| **Invoice / bill** | Sales invoice (receivable) or supplier bill (payable): taxable value, GST, total, issue and due dates, status at `as_of`. |
| **Invoice / bill payment** | Allocation of a bank transaction to a document. |
| **Loan / installment** | Principal, rate, tenor, EMI and a reducing-balance schedule; each instalment's payment date, transaction and number of bounces. |
| **Bureau event** | What a traditional bureau would hold: account opened, 30/60/90 days past due, closed. Only for lenders that report, from month-end snapshots, received 20 days later. |
| **Ground truth** | Archetype, whether and when deterioration starts, the mechanisms, and a plain-language narrative. |

Money is always integer paise. GST is modelled (output tax on sales, input credit on purchases,
net paid monthly on the 20th); a freelancer below the threshold is not registered and pays
quarterly advance tax instead.

## 3. How the data is generated

`engine.py` runs a **day-by-day simulation** of the business, so relationships hold by
construction rather than being patched afterwards. Each day:

1. Loan auto-debits (NACH) are presented against the overnight balance. If the account can't
   cover one, it **bounces**: a ₹590 charge is raised and the debit is presented again a few
   days later.
2. Money comes in: loan disbursements, yesterday's UPI settlement, and customer payments that
   fall due today.
3. On open days: the counter-sales register and cash deposits, plus new invoices. Customers order
   at roughly regular intervals (±30% jitter), each with their own payment terms and delay habits.
4. Supplier bills arrive on each supplier's cycle, sized from expected sales × the purchase/sales
   ratio. Salaries, rent, utilities, variable spending, GST and advance tax join a payment queue.
5. The queue is paid in priority order (bank charges → EMIs → salaries → rent/tax → utilities →
   suppliers → other) **only if the account can afford it** (balance + overdraft limit).
   Otherwise the payment waits. That is how a cash squeeze shows up as stretched payables, late
   salaries or bounces, without anyone writing those in by hand.
6. The owner takes drawings only if the balance stays above their buffer. Overdraft interest
   accrues daily and is charged monthly.

Two months of **warm-up** are simulated before the visible window and then cut away. The history
therefore opens mid-stream, with customers already owing money, suppliers already owed, and a
balance shaped by real activity. Documents from the warm-up appear only if still open when the
window starts (opening receivables and payables). Their earlier payments keep
`transaction_id = NULL`, because they predate the statement.

**Scenario shocks** change behaviour from a given month: a customer's order volume
(`CustomerVolumeShock`), payment delays (`PaymentDelayShock`), walk-in sales trend
(`SalesTrendShock`) and purchase costs (`CostInflationShock`). Shocks flagged as deterioration set
the ground-truth onset date and mechanisms. Their effects on cash, receivables, payables, loans
and bounces all emerge from the simulation.

## 4. Guarantees (and the tests that enforce them)

`apps/api/tests/synthetic/` runs every check against every scenario:

| Guarantee | Test |
|---|---|
| Same scenario + seed ⇒ byte-identical dataset (fingerprint); a different seed ⇒ different data; the primary demo's fingerprint is pinned | `test_determinism.py` |
| Running balance = opening balance + Σ postings; ordered, inside the window; never beyond the overdraft limit; every line labelled | `test_ledger.py` |
| `taxable + tax = total`; payments never exceed the document; statuses agree with payments | `test_receivables_payables.py` |
| Every invoice payment is a bank credit from that customer with the same amount and date (bills: debits to that supplier), and every customer receipt and supplier payment is allocated exactly once | ″ |
| **Receivables/payables roll forward**: closing = opening + issued − settled | ″ |
| **Till to bank**: opening cash in transit + takings = UPI settlements + cash deposits + closing cash in transit | `test_cash_tax_debt.py` |
| Each GST payment = that month's output tax − input tax | ″ |
| Loan schedules repay exactly the principal; disbursements and every paid EMI are bank transactions; bounce charges match bounces; debt outstanding = borrowed − principal repaid | ″ |
| Bureau events only for reporting lenders, and DPD events match real days past due | ″ |
| The monthly summary reconciles with the ledger | ″ |
| Each scenario behaves like its archetype (e.g. Mehra's sales fall > 25% after onset, it bounces only after onset, and the bureau still shows nothing) | `test_scenarios.py` |
| Seeding into PostgreSQL is idempotent, and the same reconciliations hold in SQL | `tests/test_seed_db.py` |

## 5. Commands

From the repository root (`DATABASE_URL` comes from `.env`):

| Task | Command |
|---|---|
| Create the database if missing + migrate | `make db-init` (`scripts/db-init.sh`) |
| Load all scenarios (idempotent) | `make db-seed` (`scripts/db-seed.sh`; one scenario: `scripts/db-seed.sh -s sharma_electricals`) |
| Drop everything, re-migrate, re-seed | `make db-reset` (`scripts/db-reset.sh`; refuses when `FINPULSE_ENV=production`) |
| Row counts | `cd apps/api && uv run finpulse db counts` |
| List scenarios | `cd apps/api && uv run finpulse synthetic list` |
| Month-by-month view | `cd apps/api && uv run finpulse synthetic summary sharma_electricals` |
| Export to CSV (no database needed) | `cd apps/api && uv run finpulse synthetic export -o ../../synthetic-export` |

## 6. Changing or adding scenarios

A scenario is a frozen `ScenarioSpec` (`synthetic/spec.py`): pure data, with amounts in paise via
`rupees(...)`. To add one:

1. Create `synthetic/scenarios/<code>.py`. Copying the closest existing scenario is the
   quickest start. Fill in:
   - **Identity:** `code`, `display_name`, `kind` (`business`/`individual`), `archetype`,
     `segment`, `narrative`, `profile`.
   - **Window and seed:** `start` (first of a month), `months`, `seed`.
   - **Money in:**
     - `account`: opening balance, overdraft limit and rate.
     - `customers`: monthly volume, orders per month, terms, payment delay and its spread,
       partial-payment probability.
     - `counter_sales` (optional): daily mean, volatility, UPI share, closed days.
     - `seasonality` (12 monthly multipliers) and `monthly_growth`.
   - **Money out:**
     - Purchases: `cogs_ratio` plus `suppliers` (share, billing cycle, terms, payment habits).
     - `employees`, `recurring_expenses` (day of month, optional monthly multipliers) and
       `variable_expenses` (times per month).
     - `owner` drawings and buffer; `tax` (GST rate or advance tax).
   - **Debt:** `loans` — principal, rate, tenor, disbursement month (negative = before the
     history), EMI day, whether the lender reports to the bureau.
   - **Story:** `shocks` — what changes, and from which month.
2. Register it in `synthetic/scenarios/__init__.py`. Seeding, export and the test suite pick it up
   automatically, and every consistency test then runs against it.
3. Check the story: `uv run finpulse synthetic summary <code>`. Then run `uv run pytest tests/synthetic`.

Tips:

- **Variants of an existing scenario** (e.g. for an evaluation cohort):
  `dataclasses.replace(SHARMA_ELECTRICALS, code="sharma_seed_7", seed=7)`. The same story plays
  out with different day-to-day noise.
- **Make a deterioration hit harder or sooner:** move shock `start_month`s earlier, deepen
  `factor` / `monthly_change` / `cogs_ratio_delta`, or lower the opening balance or overdraft
  limit. Drawings, supplier stretching and loans all respond automatically.
- **Mark context changes that aren't deterioration** (e.g. a planned seasonal pause) with
  `deterioration=False`. They then don't set the ground-truth onset.
- Each component draws from its own named random stream (`sampling.py`). Adding a customer
  doesn't reshuffle anyone else's numbers, so diffs stay local.
- **Changing an existing scenario or the engine** changes the data everyone sees. Update the
  pinned fingerprint in `tests/synthetic/test_determinism.py`, and bump `GENERATOR_VERSION` in
  `engine.py` when the engine changed.

## 7. Known simplifications

- One bank account per subject. There are no cards, wallets or transfers between own accounts
  yet (transfer pairing is a Phase 2 concern).
- No inventory or profit-and-loss statement. Purchases track expected demand, so gross margin is
  set by `cogs_ratio` rather than by stock levels.
- A single GST rate per scenario; no reverse charge, exports or composition scheme.
- Bank holidays are ignored; bank activity can post on any day, while sales happen on open days.
- The bureau model is intentionally simple: monthly snapshots and DPD buckets with a fixed
  reporting lag, and no scores or enquiries.
- The data is plausible by design, not calibrated to real-world distributions. Evaluation
  results measure FinPulse against this generator's model of financial behaviour.
