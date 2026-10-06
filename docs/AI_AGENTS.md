# FinPulse AI agents — design and guarantees

> **AI interpretation of deterministic results, on synthetic data.** The agents explain and
> challenge numbers that the deterministic engines have already calculated. They never calculate
> financial facts. Nothing they say is a credit score, credit assessment or lending decision.

## The rule: agents read, Python calculates

```
deterministic engines ──▶ evidence pack (~150 citable items, hashed) ──▶ agents ──▶ verifier ──▶ report
 metrics · passport ·        fact / calculated_metric /                  Claude     every claim cited,
 warnings · stress           forecast / assumption                      (JSON)      every number found
```

1. **The evidence pack** (`agents/evidence.py`) gathers every verified backend output for one
   entity and date into citable items with stable ids. It covers:
   - the entity's facts and data coverage;
   - all 25 metrics;
   - the passport score, its dimensions and factors;
   - each early warning and its evidence;
   - the risk summary, trend and timeline;
   - all ten stress scenarios and their outcomes;
   - the assumptions behind the passport, warnings and stress tests.

   It is deterministic, with no LLM. `GET /entities/{id}/evidence-pack` shows exactly what the
   agents see.
2. **Agents** receive only evidence items (each agent a relevant subset) and return **structured
   JSON** (Pydantic schemas, enforced by structured outputs). Every statement is a `Claim`:

   ```json
   {"statement": "Receivables rose 59% to ₹10,97,992 while sales were flat.",
    "statement_type": "CALCULATED_METRIC",
    "evidence_ids": ["warning:EW-233FAE5A17"], "confidence": "high"}
   ```

3. **The verifier** (`agents/verifier.py`, deterministic) checks every claim before anything
   downstream sees it, as described below.

### Statement types

| Type | Meaning | Must cite at least one |
|---|---|---|
| `FACT` | A recorded fact about the entity or its data | `fact` item |
| `CALCULATED_METRIC` | A value calculated by the deterministic engines | `calculated_metric` item |
| `FORECAST` | A projected outcome of a hypothetical stress scenario | `forecast` item |
| `ASSUMPTION` | An assumption behind a calculation or projection | `assumption` item |
| `AI_INTERPRETATION` | The agent's own reading or judgement | any item (but must cite) |

## The verifier

For every claim:

- **Citations.** It cites at least one evidence item, and every cited id exists.
- **Type.** Its `statement_type` is supported by the kinds of item it cites (table above).
- **Numbers.** Every number in the statement appears in the evidence it cites. For the senior
  agent, the evidence behind the upstream claims it builds on also counts.
  - Display rounding is allowed: 0.5919 may be written "59%" or "59.2%", ₹6,89,747 may be
    written "₹6.9 lakh" or "₹6,90,000", and 47.8 days may be written "48 days".
  - Arithmetic is not allowed. "₹4,08,245", the difference between two cited values, is
    rejected, because the agent calculated it.
  - Numbers are read the way a person reads them: Indian digit grouping, lakh and crore, %, ×
    and the Unicode minus are understood. Dates and ids are ignored. Small counts (0–12, and the
    100 in "55/100") need no source.
- **Sections.** In the senior synthesis, each claim sits in the section of its type: `facts`,
  `calculated_metrics`, `forecasts`, `assumptions` or `interpretations`.
- **References.** Fields that name a warning (`warning:…`), a scenario (`stress:…`) or another
  agent's claim (`target_claim_id`, `based_on_claims`) must point at things that exist.
- **Other text.** Text fields that are not claims, such as open questions and the headline, may
  only contain numbers that exist somewhere in the pack.

### When verification fails

1. The issues are sent back to the model ("`weaknesses[1].statement: unsupported_number: '7.3'
   does not appear in the cited evidence …`"), which returns a corrected answer. There are up to
   **3 attempts** in all.
2. If issues remain only inside list elements (one weakness, one challenge), **those elements
   are dropped** and listed in `verification.pruned`.
3. Otherwise the agent **fails** with `verification_failed`.

**Unverified text is never returned.** Each run reports the issues found at every attempt
(`verification.attempts_issues`) for audit.

## The seven agents

| Agent | Sees | Returns |
|---|---|---|
| **Financial Profile** | Facts, all metrics, passport and dimensions, risk summary | Summary, strengths, weaknesses, data limitations |
| **Credit Intelligence** | Facts, debt, cash-flow, liquidity, behaviour and revenue metrics, full passport, debt, cash, liquidity and receivables warnings | Repayment capacity, payment behaviour, alternative-data signals where bureau history is thin, concerns, reliability view (never a decision), information gaps |
| **Early Warning Investigation** | Facts, metrics, every warning with its evidence, risk summary, trend and timeline | Per warning: the trigger, connected evidence, likely explanation and open questions. Plus the common thread |
| **Risk Investigation** | Facts, metrics, passport, warnings, risk summary, scenario outcomes | Ranked risks with severity, likely causes and evidence strength. Plus the overall risk |
| **Stress-Test Interpretation** | Cash, liquidity and debt metrics, passport, every scenario and its outcomes, stress assumptions | Per scenario: consequences (FORECAST) and the key vulnerability. Plus the most damaging scenario, resilience and assumption caveats |
| **Red Team** | The whole pack, plus the five analysts' verified claims (by id) | Challenges to the major conclusions: contradictory evidence, missing information, weak assumptions, alternative explanations, severity |
| **Senior Financial Intelligence** | The whole pack, all verified claims, the red-team challenges | Headline, overall assessment, claims separated into FACT / CALCULATED METRIC / FORECAST / ASSUMPTION / AI INTERPRETATION, a response to each challenge, open questions, confidence |

The five analysts run **in parallel**. The red team runs on their *verified* claims, and the
senior agent runs last.

Verified claims get stable ids within a run (`PRO-01`, `CRE-03`, `RSK-02`, `RED-01`, `SEN-04`).
The red team targets claims by id, and the senior synthesis cites both evidence ids and the
claim ids it builds on.

## Error handling

| Situation | What happens |
|---|---|
| No API key / bad key / provider down / rate-limited | `503 llm_unavailable`, with a clear message. The SDK first retries 408/409/429/5xx and connection errors (`LLM_MAX_RETRIES`). The deterministic API is unaffected |
| Model declines for safety reasons | A server-side fallback model retries by default (`LLM_REFUSAL_FALLBACK`). If it still declines, that agent fails with `llm_refusal` |
| Answer cut off | Agent fails with `llm_truncated` (raise `LLM_MAX_TOKENS`) |
| Reply not matching the schema | Re-asked with the validation errors. After 3 attempts the agent fails with `llm_invalid_output` |
| Verification issues | Repair loop, then pruning, then the agent fails with `verification_failed` (see above) |
| Unexpected exception in an agent | That agent fails with `agent_error`. The others continue |
| One analyst fails | Report `partial`. The red team and senior agent are told which agent produced nothing |
| Every analyst fails | Red team and senior agent are `skipped`. Report `failed` (or 503 if the model was unreachable) |

## API

```
GET  /api/v1/entities/{id}/evidence-pack[?as_of=]   the evidence (deterministic, no AI)
POST /api/v1/entities/{id}/intelligence              all seven agents → IntelligenceReport
POST /api/v1/entities/{id}/agents/{agent_name}        one agent (+ the agents it depends on)
GET  /api/v1/meta/agents                              agents, dependencies, prompt versions, schemas
```

The POST bodies take an optional `{"as_of": "YYYY-MM-DD"}`. An `IntelligenceReport` holds each
agent's run, plus the senior synthesis, token usage and a disclaimer. Each run includes:

- its status and verified output;
- the claims it registered;
- its verification report;
- its error, if any;
- the model and `prompt_version` (a hash of the prompt and schema);
- the number of evidence items it saw, its attempts and its token usage.

## Configuration

Set these in `.env` (see `.env.example`). The key is never logged.

| Variable | Default | |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for the agents. Without it the agent endpoints return 503 |
| `LLM_MODEL` | `claude-opus-5-5` | |
| `LLM_EFFORT` | `high` | `low` … `max`. Thinking is adaptive |
| `LLM_MAX_TOKENS` | `16000` | Per call |
| `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` | `300` / `2` | |
| `LLM_REFUSAL_FALLBACK` | `true` | Server-side `fallbacks: "default"` (Claude API) |

A full report is 7 model calls, plus any repair calls. The five analysts run concurrently.

## Modularity and tests

Each agent is an `AgentSpec` (in `agents/catalogue.py`), made of:

- an output schema;
- a role prompt (`agents/prompts.py`, after the shared rules);
- an evidence selector;
- a claim-id prefix;
- its dependencies;
- any extra verification rules.

`run_agent(spec, llm, pack, upstream)` runs any one of them against any `LLMClient`. Tests use a
scripted `FakeLLM` (`tests/agents/fakes.py`), so they need no key and make no network calls. The
tests in `tests/agents/` and `tests/test_agents_api.py` cover:

- **Number reading:** formats, rounding versus arithmetic, dates and ids.
- **Verifier:** each issue type, sections, references, numbers drawn from upstream claims, and
  pruning.
- **Evidence pack:** determinism and kinds.
- **Claude adapter:** request shape (structured outputs, adaptive thinking, fallback), refusal,
  truncation and error mapping. These tests make no network calls.
- **Runner:** passing first time, repairing an invented number, pruning, failing, schema
  retries, and errors.
- **Each agent on its own:** its evidence selection, plus the red team on verified claims only,
  section typing for the senior agent, and reference checks.
- **Pipeline:** order, partial failure, skipped agents, an unreachable model.
- **API:** 200, 404, 422 and 503, including the real adapter without credentials.

To add an agent: write its output schema in `schemas.py` from `Claim` fields, a role prompt, and
an `AgentSpec` in `catalogue.py` (with `depends_on` if it reads other agents' claims). The
verifier, repair loop, claim register, orchestrator and API need no changes.

## Limits

- **Not yet run against the live model.** Every test uses the scripted fake, so the prompts are
  version-1 and untuned. Expect some first-attempt verification issues that the repair loop
  absorbs.
- **Synchronous.** The intelligence endpoint returns when all agents finish. A full run is
  several model calls at high effort, so it takes minutes rather than seconds. Background jobs,
  persistence and SSE progress (DEVELOPMENT_PLAN Phase 8) are not built.
- **No tool use.** Agents receive the evidence up front rather than calling read-only tools.
- **Words are not checked.** The verifier checks numbers, citations and types, not prose: an
  agent could still over-interpret. The statement types and the red team exist to make that
  visible.
