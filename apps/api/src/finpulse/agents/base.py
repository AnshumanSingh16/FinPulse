"""Running one agent: give it its evidence, get structured JSON, verify, repair, register claims.

Every agent is an ``AgentSpec`` (data, not a class hierarchy): its output schema, prompt, the
evidence it sees and the extra verification rules for its output. ``run_agent`` is the same for
all of them, so an agent can be run and tested on its own with any ``LLMClient``.

The loop, per agent:
  1. ask for JSON matching the schema (structured outputs);
  2. validate it with Pydantic; on a schema error, ask again with the error;
  3. verify it deterministically; on issues, send the issues back and ask for a corrected
     answer (up to ``MAX_ATTEMPTS`` calls in all);
  4. if issues remain only inside list elements, drop those elements and say so in the
     verification report; otherwise the agent fails with ``verification_failed``.
Nothing unverified is returned.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from finpulse.agents.evidence import EvidenceItem, EvidencePack
from finpulse.agents.llm import LLMClient, LLMRequest, LLMResponse, strict_schema
from finpulse.agents.prompts import SHARED_RULES
from finpulse.agents.schemas import (
    AgentErrorInfo,
    AgentInfo,
    AgentRun,
    Issue,
    RegisteredClaim,
    Usage,
    VerificationReport,
)
from finpulse.agents.verifier import (
    Found,
    Verifier,
    VerifyRules,
    is_claim,
    path_str,
    prunable,
    prune,
)
from finpulse.core.errors import AppError, UpstreamLLMError
from finpulse.observability.logging import get_logger

log = get_logger("finpulse.agents")
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class AgentSpec:
    name: str
    title: str
    purpose: str
    output_model: type[BaseModel]
    role: str
    select: Callable[[EvidencePack], list[EvidenceItem]]
    claim_prefix: str
    depends_on: tuple[str, ...] = ()
    rules: VerifyRules = field(default_factory=VerifyRules)
    effort: str | None = None

    @property
    def system_prompt(self) -> str:
        return f"{SHARED_RULES}\n{self.role}"

    @property
    def prompt_version(self) -> str:
        schema = json.dumps(self.output_model.model_json_schema(), sort_keys=True)
        digest = hashlib.sha256((self.system_prompt + schema).encode()).hexdigest()
        return f"{self.name}@{digest[:12]}"

    def info(self) -> AgentInfo:
        return AgentInfo(
            name=self.name,
            title=self.title,
            purpose=self.purpose,
            depends_on=list(self.depends_on),
            prompt_version=self.prompt_version,
            output_schema=self.output_model.model_json_schema(),
        )


# --- input ---------------------------------------------------------------------------------------


def build_user_message(
    spec: AgentSpec,
    pack: EvidencePack,
    items: list[EvidenceItem],
    upstream: dict[str, AgentRun],
) -> str:
    e = pack.entity
    lines = [
        "## Entity",
        f"{e.display_name}: {e.kind}, {e.segment}. Analysis as of {pack.as_of}.",
        "",
        f"## Evidence ({len(items)} items)",
        "One JSON object per line. Cite ids exactly. Kinds: fact | calculated_metric | "
        "forecast | assumption.",
        "<evidence>",
        *(json.dumps(i.for_prompt(), ensure_ascii=False) for i in items),
        "</evidence>",
    ]
    if spec.depends_on:
        claims = [c for run in upstream.values() for c in run.claims]
        lines += [
            "",
            f"## Verified findings from other agents ({len(claims)} claims)",
            "Refer to these by claim_id (in `target_claim_id` or `based_on_claims`).",
            "<claims>",
            *(
                json.dumps(
                    {
                        "claim_id": c.claim_id,
                        "agent": c.agent,
                        "statement": c.statement,
                        "statement_type": c.statement_type,
                        "evidence_ids": c.evidence_ids,
                        "confidence": c.confidence,
                    },
                    ensure_ascii=False,
                )
                for c in claims
            ),
            "</claims>",
        ]
        red = upstream.get("red_team")
        if red is not None and red.status == "succeeded" and red.output:
            lines += [
                "",
                "## Red-team challenges",
                "<challenges>",
                *(
                    json.dumps(
                        {
                            "target_claim_id": ch["target_claim_id"],
                            "severity": ch["severity"],
                            "challenge_summary": ch["challenge_summary"],
                            "missing_information": ch["missing_information"],
                        },
                        ensure_ascii=False,
                    )
                    for ch in red.output.get("challenges", [])
                ),
                "</challenges>",
            ]
        missing = [
            n for n in spec.depends_on if n not in upstream or upstream[n].status != "succeeded"
        ]
        if missing:
            lines += [
                "",
                f"Note: these agents produced no verified findings: {', '.join(missing)}.",
            ]
    lines += ["", "## Task", "Produce your analysis as JSON matching the response schema."]
    return "\n".join(lines)


def repair_message(found: list[Found]) -> str:
    listed = "\n".join(f"- {f.issue().path}: {f.code}: {f.detail}" for f in found[:40])
    return (
        "Your previous answer failed verification:\n"
        f"{listed}\n\n"
        "Return the complete corrected JSON. Fix only these problems: cite the right evidence "
        "ids, correct the statement_type, or quote numbers exactly as the cited evidence gives "
        "them (never compute new numbers). If a statement cannot be supported, remove it."
    )


def _assistant_turn(response: LLMResponse) -> dict[str, Any]:
    content = response.content if response.content else [{"type": "text", "text": response.text}]
    return {"role": "assistant", "content": content}


# --- claim register -------------------------------------------------------------------------------


def register_claims(spec: AgentSpec, output: dict[str, Any]) -> list[RegisteredClaim]:
    found: list[RegisteredClaim] = []

    def walk(node: object, path: tuple[str | int, ...]) -> None:
        if isinstance(node, dict) and is_claim(node):
            found.append(
                RegisteredClaim(
                    claim_id=f"{spec.claim_prefix}-{len(found) + 1:02d}",
                    agent=spec.name,
                    path=path_str(path),
                    statement=node["statement"],
                    statement_type=node["statement_type"],
                    evidence_ids=node["evidence_ids"],
                    confidence=node["confidence"],
                )
            )
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, (*path, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, (*path, i))

    walk(output, ())
    return found


# --- run -----------------------------------------------------------------------------------------


async def run_agent(
    spec: AgentSpec,
    llm: LLMClient,
    pack: EvidencePack,
    upstream: dict[str, AgentRun] | None = None,
) -> AgentRun:
    upstream = upstream or {}
    items = spec.select(pack)
    upstream_claims = {c.claim_id: c for run in upstream.values() for c in run.claims}
    verifier = Verifier(pack, spec.rules, upstream_claims)
    schema = strict_schema(spec.output_model.model_json_schema())
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_user_message(spec, pack, items, upstream)}
    ]
    usage = Usage()
    history: list[list[Issue]] = []
    base = {
        "agent": spec.name,
        "title": spec.title,
        "prompt_version": spec.prompt_version,
        "evidence_items": len(items),
        "model": getattr(llm, "model", None),
    }

    def failed(code: str, message: str, report: VerificationReport | None = None) -> AgentRun:
        log.warning("agent_failed", agent=spec.name, code=code, error=message)
        return AgentRun(
            **base,
            status="failed",
            output=None,
            verification=report,
            usage=usage,
            attempts=usage.calls,
            error=AgentErrorInfo(code=code, message=message),
        )

    def succeeded(data: dict[str, Any], report: VerificationReport) -> AgentRun:
        log.info(
            "agent_succeeded", agent=spec.name, attempts=usage.calls, pruned=len(report.pruned)
        )
        return AgentRun(
            **base,
            status="succeeded",
            output=data,
            claims=register_claims(spec, data),
            verification=report,
            usage=usage,
            attempts=usage.calls,
        )

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = await llm.complete(
                LLMRequest(
                    system=spec.system_prompt,
                    messages=messages,
                    schema=schema,
                    effort=spec.effort,
                    metadata={"agent": spec.name},
                )
            )
            usage = Usage(
                input_tokens=usage.input_tokens + response.input_tokens,
                output_tokens=usage.output_tokens + response.output_tokens,
                calls=usage.calls + 1,
            )
            try:
                output = spec.output_model.model_validate_json(response.text)
            except ValidationError as exc:
                if attempt == MAX_ATTEMPTS:
                    return failed(
                        "llm_invalid_output",
                        f"The model's reply did not match the schema: {exc.error_count()} "
                        "error(s).",
                    )
                messages += [
                    _assistant_turn(response),
                    {
                        "role": "user",
                        "content": "Your reply did not match the response schema "
                        f"({exc.errors(include_url=False)[:10]}). Reply again with JSON only.",
                    },
                ]
                continue

            data = output.model_dump(mode="json")
            result = verifier.verify(data)
            history.append([f.issue() for f in result.found])
            if result.passed:
                return succeeded(data, _report(result, history, []))
            if attempt < MAX_ATTEMPTS:
                messages += [
                    _assistant_turn(response),
                    {"role": "user", "content": repair_message(result.found)},
                ]
                continue
            if prunable(result.found):
                data, removed = prune(data, result.found)
                data = spec.output_model.model_validate(data).model_dump(mode="json")
                final = verifier.verify(data)
                if final.passed:
                    return succeeded(data, _report(final, history, removed))
                result = final
            return failed(
                "verification_failed",
                f"{len(result.found)} issue(s) remained after {MAX_ATTEMPTS} attempts.",
                _report(result, history, []),
            )
    except UpstreamLLMError as exc:
        return failed(exc.instance_code, exc.detail or str(exc))
    except AppError as exc:
        return failed(exc.instance_code, exc.detail or str(exc))
    except Exception as exc:  # an agent must never take the pipeline down
        log.exception("agent_crashed", agent=spec.name)
        return failed("agent_error", f"{type(exc).__name__}: {exc}")
    return failed("agent_error", "No attempt was made.")  # pragma: no cover


def _report(result: Any, history: list[list[Issue]], pruned: list[str]) -> VerificationReport:
    return VerificationReport(
        passed=result.passed,
        claims_checked=result.claims_checked,
        numbers_checked=result.numbers_checked,
        issues=[f.issue() for f in result.found],
        pruned=pruned,
        attempts_issues=history,
    )
