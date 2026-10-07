# FinPulse investigations — the orchestrated workflow

> A fixed financial investigation workflow, not a chatbot. There is no free-text question: you
> name an entity (and optionally a date), and the orchestrator runs every stage and returns one
> structured, auditable record.

```
POST /api/v1/entities/{entity_id}/investigate      {"as_of": "2026-09-30"}  (body optional)
GET  /api/v1/investigations                        recent investigations, newest first
GET  /api/v1/investigations/{investigation_id}     the complete record
GET  /api/v1/investigations/{investigation_id}/events   its timestamped event log
```

## The workflow

| # | Stage | What happens | AI? |
|---|---|---|---|
| 1 | Financial data | Records the data being investigated (transactions, invoices, bills, loans) | – |
| 2 | Deterministic analytics | The 25 metrics | – |
| 3 | Financial Passport | Six dimensions and the prototype Financial Health score; flags a provisional passport | – |
| 4 | Early warning detection | The warnings and risk summary. Each warning is logged | – |
| 5 | Stress testing | All ten scenarios | – |
| 6 | Evidence assembly | The verified, citable, hashed evidence pack the agents may use | – |
| 7 | Specialized AI investigation | Five agents in parallel: Financial Profile, Credit Intelligence, Early Warning Investigation, Risk Investigation and Stress-Test Interpretation | ✓ |
| 8 | Disagreement detection and review planning | Finds disagreements and chooses which assessments the red team must review | – |
| 9 | Red-team challenge | Challenges the verified conclusions. It **must** review every significant assessment, and it assesses every disagreement | ✓ |
| 10 | Evidence verification | Audits every verified claim (analysts and red team) before synthesis. It reports per-agent verifier results (claims passed, pruned, issues caught) and confirms every evidence reference resolves to the hashed pack | – |
| 11 | Senior Financial Intelligence | The final synthesis. It resolves disagreements, answers challenges and gives recommendations | ✓ |
| 12 | Final assessment | Assembles the record, caps confidence, and audits claims and evidence references | – |

Each stage records its status, start and end times, duration, a one-line summary and details.

### The eight user-facing steps

Users see eight steps rather than twelve stages. `investigation/timeline.py` declares exactly
which stages and agents execute each step. It rebuilds the steps from the run's stage records
and events, for both live progress and the stored record (`timeline` on each), so the timeline
users watch is the one that is stored.

| Step | Executed by |
|---|---|
| 1 Collecting financial evidence | Stages 1–6 (deterministic) |
| 2 Analyzing cash flow | Financial Profile Agent |
| 3 Evaluating financial reliability | Credit Intelligence Agent |
| 4 Investigating early warnings | Early Warning Investigation and Risk Investigation Agents |
| 5 Running stress scenarios | Stress-Test Interpretation Agent, on the stress-test engine's results from step 1 |
| 6 Red-team challenge | Disagreement detection, then the Red-Team Agent |
| 7 Verifying evidence | The evidence verification stage (the verifier itself also runs inside every agent call) |
| 8 Generating final assessment | Senior Financial Intelligence Agent, then the final assessment |

Notes on how the steps report:
- Steps 2–5 run **concurrently**, so they are marked as one parallel group, not a sequence.
- A step with no recorded work is pending while the run is live, and skipped afterwards.
- For each agent, the timeline shows its focus, its key (summary-level) verified finding with
  confidence, every evidence item it cited, and verifier counts.
- It also shows each red-team challenge against the agent's claims, with the senior agent's
  ruling. These are carried on the agents' completion events, so they appear live.

## How the orchestrator keeps the investigation honest

- **Only verified data goes to agents.** Agents see only evidence-pack items (deterministic
  engine output) and other agents' *verified* claims. A failed agent's output never reaches
  anyone.
- **Unsupported claims are blocked.** Every agent output passes the deterministic verifier
  ([AI_AGENTS.md](AI_AGENTS.md)): every claim cites existing evidence, its type matches what it
  cites, and every number appears in the cited evidence. Failing claims are repaired or dropped.
  The `claim_audit` reports how many issues were caught and how many claims were pruned.
- **Evidence references are preserved.** Every claim keeps its evidence ids, and claims get
  stable ids (`RSK-01`, `RED-03`, `SEN-07`). The investigation lists every cited evidence item,
  with its text, in `evidence_references`, and checks that all of them resolve.
- **Structured context.** The red team and senior agent receive the disagreements and review
  requests as structured blocks, and must refer to them by id (`DIS-01`, a claim id). The
  verifier checks those ids too.

### Disagreements (deterministic)

Each analyst states an overall `risk_stance` (low, moderate, elevated, high or severe). The
orchestrator compares stances, citations and severities:

| Kind | When |
|---|---|
| `stance_spread` | Two agents' stances are 2+ levels apart (major at 3+) |
| `agent_vs_engine` | An agent's stance is 2+ levels from the deterministic early-warning risk level |
| `conflicting_reading` | One agent cites an item as a strength while another cites it as a weakness, concern or risk |
| `severity_mismatch` | A risk's stated severity is 2+ levels from the warnings it cites |

The red team must assess each disagreement, and the senior agent must resolve each one, citing
evidence. Unresolved disagreements lower confidence.

### Mandatory red-team review

These claims are significant risk assessments, and the red team is required to challenge each
one:

- high- and critical-severity risks;
- explanations of high or critical warnings;
- the overall reliability and resilience judgements;
- the profile summary, when risk is elevated;
- claims involved in a disagreement.

If the red team leaves one out, it is sent back once or twice to cover it. Anything still
unreviewed is listed, logged (`review_missing`) and caps confidence at medium.

### Confidence

The senior agent states a confidence. The orchestrator then caps it deterministically:

| Cap | Reason |
|---|---|
| low | 2+ specialist agents failed; no red-team review; or no senior synthesis |
| medium | One specialist failed; required reviews missing; disagreements unresolved; challenges unaddressed; or the passport is provisional |

The investigation's confidence is the lower of the stated value and the cap. Every reason is
listed in `confidence.adjustments`.

### Failures

| Failure | What happens |
|---|---|
| A specialist fails | Its failure is recorded, the others continue, and the status is `completed_with_gaps` |
| The red team fails | The senior agent works without challenges, and confidence is low |
| The senior agent fails | The final assessment falls back to **deterministic results quoted verbatim** (`source: deterministic_fallback`): no interpretation and no recommendations |
| The model is unreachable or not configured | `503 llm_unavailable`, with nothing half-done returned |

## The investigation record

| Field | Contents |
|---|---|
| `investigation_id`, `entity_id`, `entity`, `as_of`, `status`, `workflow_version` | Identity and outcome (`completed`, `completed_with_gaps` or `failed`) |
| `started_at`, `completed_at`, `duration_ms`, `stages[]` | Timestamps and the per-stage record |
| `triggered_warnings[]` | Every warning the engine raised, with whether and by which claims it was investigated |
| `risk_summary`, `financial_health` | The deterministic risk level and index, and the prototype passport score |
| `financial_metrics_used[]` | Each metric cited by a verified claim: its value, unit and period, and the claims citing it |
| `agent_analyses{}` | The five specialists' runs: verified output, claims, verification report, attempts and usage |
| `disagreements[]`, `review_requests[]` | What the orchestrator detected and asked the red team to review, and whether each was resolved or reviewed |
| `red_team_findings`, `red_team_run` | Challenges, disagreement assessments, robustness and review coverage |
| `senior_synthesis_run`, `final_assessment` | The synthesis. FACT, CALCULATED METRIC, FORECAST, ASSUMPTION and AI INTERPRETATION are kept separate, with challenge and disagreement resolutions and open questions. Also the deterministic risk level and health score |
| `recommendations[]` | Next steps for the analyst (verify, request, monitor), each with a priority and a cited rationale. Never a lending decision |
| `confidence` | Level, the senior agent's own statement, the orchestrator's cap and the reasons |
| `evidence_pack`, `evidence_references[]`, `claim_audit` | The pack hash and every cited item. Claims verified and pruned, issues caught, unmet requirements, and whether every reference resolves |
| `usage`, `events[]`, `disclaimer` | Model calls and tokens, the full event log, and the disclaimer |

## Inspecting an investigation during a demo

- **Web.** The AI Investigation view starts a run with `POST /api/v1/entities/{id}/investigations`.
  It returns `202` at once, and the run continues in the background. The view then polls
  `GET /api/v1/investigations/{id}/progress` and shows:
  - the eight-step timeline above, with each agent's key finding, evidence used, confidence
    and challenges as they arrive;
  - the latest event and the raw event log.

  When the run completes, the view shows the **Investigation Report**:
  1. Overall assessment
  2. Key evidence (the most-cited evidence items)
  3. Primary risks (from the Risk Investigation Agent)
  4. Contradictory evidence (red-team challenges and disagreements, with rulings)
  5. Stress-test results (the engine's before → after figures from the same hashed pack)
  6. Recommended actions

  When the run completes, the view opens the full record. The progress is built only from the
  orchestrator's own events, through a listener on its recorder; nothing is estimated. The
  Evidence view traces any claim to the evidence items it cites.

- **API.** Recent investigations are kept in memory (`INVESTIGATIONS_KEEP`, default 50) and
  listed by `GET /api/v1/investigations`. Set `INVESTIGATIONS_DIR` to also write each one as a
  JSON file.
- **Logs.** Every event is also written to the structured log, bound to the `investigation_id`.
  Events include stage starts and ends, triggered warnings, agent completions and failures,
  disagreements, review requests, missing reviews, unmet requirements and fallbacks. Use
  `LOG_FORMAT=console` for readable logs, or `json` to filter by `investigation_id`.
- **Terminal.**

  ```bash
  cd apps/api
  uv run finpulse investigate run sharma_electricals -o sharma.json --events   # needs ANTHROPIC_API_KEY
  uv run finpulse investigate show sharma.json --events                       # no key needed
  ```

  This prints the workflow (✓ / ! / ✗ per stage, with timings) and the triggered warnings. It
  also shows the metrics used, each agent's verified claims, attempts and issues caught, the
  disagreements and red-team challenges, the final assessment by statement type, the
  recommendations, confidence with its reasons, the audit and the timed event log.

## Limits

- `POST …/investigate` is synchronous: the request returns when the investigation is complete. A
  real run makes at least seven calls to Claude and takes minutes. The background variant
  (`POST …/investigations` plus `/progress`) keeps progress in memory, in the API process only.
- Investigations are kept in memory (and optionally as files), not in PostgreSQL.
- Not yet run against the live model. Every test uses a scripted model.
