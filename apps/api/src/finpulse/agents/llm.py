"""The language-model boundary. Agents depend on the ``LLMClient`` protocol only, so each agent
can be tested with a scripted fake and the provider can be swapped without touching them.

``AnthropicLLM`` calls Claude through the official SDK with:
  * structured outputs (``output_config.format``): the reply is JSON matching the agent's schema;
  * adaptive thinking and a configurable effort level;
  * server-side refusal fallback (``fallbacks: "default"``), on by default;
  * SDK retries for 408/409/429/5xx and connection errors, then typed errors mapped to
    ``LLMUnavailableError`` (503: try later) or ``UpstreamLLMError`` (502: this request failed).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from finpulse.config import Settings
from finpulse.core.errors import LLMUnavailableError, UpstreamLLMError
from finpulse.observability.logging import get_logger

log = get_logger("finpulse.agents.llm")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NOT_CONFIGURED = "The AI layer is not configured: set ANTHROPIC_API_KEY to enable the agents."


class LLMRefusalError(UpstreamLLMError):
    code = "llm_refusal"
    title = "The AI model declined the request"


class LLMTruncatedError(UpstreamLLMError):
    code = "llm_truncated"
    title = "The AI model's answer was cut off"


@dataclass
class LLMResponse:
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    # The assistant content exactly as returned, to append unchanged in a follow-up turn.
    content: Any = None
    request_id: str | None = None


@dataclass
class LLMRequest:
    system: str
    messages: list[dict[str, Any]]
    schema: dict[str, Any]
    max_tokens: int | None = None
    effort: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class LLMClient(Protocol):
    model: str

    async def complete(self, request: LLMRequest) -> LLMResponse: ...


# --- JSON schema for structured outputs ---------------------------------------------------------

_UNSUPPORTED = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "title",
    "default",
    "examples",
}


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic's JSON schema, adapted to what structured outputs accept: every object closed
    (``additionalProperties: false``) with all properties required, and no unsupported
    constraint keywords (Pydantic re-checks those when the reply is parsed)."""

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: fix(v) for k, v in node.items() if k not in _UNSUPPORTED}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            return node
        if isinstance(node, list):
            return [fix(v) for v in node]
        return node

    result: dict[str, Any] = fix(copy.deepcopy(schema))
    return result


# --- Claude --------------------------------------------------------------------------------------


class AnthropicLLM:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.model = settings.llm_model
        self.effort = settings.llm_effort
        self.max_tokens = settings.llm_max_tokens
        self.fallback = settings.llm_refusal_fallback
        if client is not None:
            self.client = client
            return
        key = settings.anthropic_api_key
        try:
            # Without an explicit key the SDK resolves ANTHROPIC_API_KEY / a CLI profile itself.
            self.client = anthropic.AsyncAnthropic(
                api_key=key.get_secret_value() if key else None,
                timeout=settings.llm_timeout_s,
                max_retries=settings.llm_max_retries,
            )
        except anthropic.AnthropicError as exc:
            raise LLMUnavailableError(NOT_CONFIGURED) from exc

    async def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens or self.max_tokens,
            "system": [
                {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": request.messages,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": request.effort or self.effort,
                "format": {"type": "json_schema", "schema": request.schema},
            },
        }
        if self.fallback:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        try:
            response = await self.client.beta.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailableError("The AI provider rejected the API key.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMUnavailableError("The API key may not use this model.") from exc
        except anthropic.RateLimitError as exc:
            retry = exc.response.headers.get("retry-after")
            raise LLMUnavailableError(
                "The AI provider is rate-limiting requests; try again later.",
                extra={"retry_after_s": retry} if retry else None,
            ) from exc
        except anthropic.BadRequestError as exc:
            log.error("llm_bad_request", error=exc.message, **request.metadata)
            raise UpstreamLLMError(
                "The AI provider rejected the request.", code="llm_bad_request"
            ) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMUnavailableError(f"The AI provider failed ({exc.status_code}).") from exc
            raise UpstreamLLMError(f"The AI provider returned {exc.status_code}.") from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise LLMUnavailableError("Could not reach the AI provider.") from exc
        except anthropic.AnthropicError as exc:  # credentials that cannot be loaded, etc.
            raise LLMUnavailableError(NOT_CONFIGURED) from exc
        except TypeError as exc:
            # The SDK raises a plain TypeError when no credentials resolve at all.
            if "authentication" in str(exc).lower():
                raise LLMUnavailableError(NOT_CONFIGURED) from exc
            raise

        stop = response.stop_reason
        if stop == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise LLMRefusalError("The AI model declined to answer.", extra={"category": category})
        if stop == "max_tokens":
            raise LLMTruncatedError(
                "The AI model's answer exceeded the output limit (raise LLM_MAX_TOKENS)."
            )
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        usage = response.usage
        return LLMResponse(
            text=text,
            model=response.model,
            stop_reason=stop,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            content=response.content,
            request_id=getattr(response, "_request_id", None),
        )
