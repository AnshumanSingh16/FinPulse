"""The Claude adapter: request shape, response handling and error mapping (no network)."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from finpulse.agents.llm import (
    AnthropicLLM,
    LLMRefusalError,
    LLMRequest,
    LLMTruncatedError,
    strict_schema,
)
from finpulse.agents.schemas import SeniorSynthesisOutput
from finpulse.core.errors import LLMUnavailableError, UpstreamLLMError
from tests.conftest import make_settings

REQUEST = LLMRequest(
    system="rules",
    messages=[{"role": "user", "content": "go"}],
    schema={"type": "object"},
    metadata={"agent": "x"},
)


def message(stop: str = "end_turn", text: str = '{"ok": true}', **extra: Any) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        stop_reason=stop,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
        **extra,
    )


class FakeMessages:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def llm(result: Any, **settings: Any) -> tuple[AnthropicLLM, FakeMessages]:
    messages = FakeMessages(result)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return AnthropicLLM(make_settings(**settings), client=client), messages


async def test_request_uses_structured_outputs_thinking_and_fallback() -> None:
    client, messages = llm(message())

    response = await client.complete(REQUEST)

    k = messages.kwargs
    assert k["model"] == "claude-opus-5-5"
    assert k["thinking"] == {"type": "adaptive"}
    assert k["output_config"] == {
        "effort": "high",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    assert k["fallbacks"] == "default" and k["betas"] == ["server-side-fallback-2026-07-01"]
    assert k["system"][0]["text"] == "rules"
    assert response.text == '{"ok": true}'
    assert (response.input_tokens, response.output_tokens) == (1200, 300)


async def test_settings_control_model_effort_and_fallback() -> None:
    client, messages = llm(
        message(), LLM_MODEL="claude-sonnet-5-5", LLM_EFFORT="medium", LLM_REFUSAL_FALLBACK="false"
    )

    await client.complete(REQUEST)

    assert messages.kwargs["model"] == "claude-sonnet-5-5"
    assert messages.kwargs["output_config"]["effort"] == "medium"
    assert "fallbacks" not in messages.kwargs and "betas" not in messages.kwargs


async def test_refusal_and_truncation() -> None:
    refused, _ = llm(message("refusal", stop_details=SimpleNamespace(category="cyber")))
    with pytest.raises(LLMRefusalError) as exc:
        await refused.complete(REQUEST)
    assert exc.value.extra == {"category": "cyber"}

    truncated, _ = llm(message("max_tokens"))
    with pytest.raises(LLMTruncatedError):
        await truncated.complete(REQUEST)


def status_error(
    cls: type[anthropic.APIStatusError], status: int, headers: dict[str, str] | None = None
) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request, headers=headers or {})
    return cls("boom", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected", "code"),
    [
        (status_error(anthropic.AuthenticationError, 401), LLMUnavailableError, "llm_unavailable"),
        (
            status_error(anthropic.RateLimitError, 429, {"retry-after": "30"}),
            LLMUnavailableError,
            "llm_unavailable",
        ),
        (status_error(anthropic.InternalServerError, 500), LLMUnavailableError, "llm_unavailable"),
        (status_error(anthropic.BadRequestError, 400), UpstreamLLMError, "llm_bad_request"),
        (status_error(anthropic.NotFoundError, 404), UpstreamLLMError, "llm_error"),
        (
            anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")),
            LLMUnavailableError,
            "llm_unavailable",
        ),
        (
            TypeError("Could not resolve authentication method."),
            LLMUnavailableError,
            "llm_unavailable",
        ),
    ],
)
async def test_errors_are_mapped(error: Exception, expected: type[Exception], code: str) -> None:
    client, _ = llm(error)

    with pytest.raises(expected) as exc:
        await client.complete(REQUEST)

    assert exc.value.instance_code == code  # type: ignore[attr-defined]


async def test_rate_limit_reports_retry_after() -> None:
    client, _ = llm(status_error(anthropic.RateLimitError, 429, {"retry-after": "30"}))

    with pytest.raises(LLMUnavailableError) as exc:
        await client.complete(REQUEST)

    assert exc.value.extra == {"retry_after_s": "30"}


async def test_other_type_errors_are_bugs_not_outages() -> None:
    client, _ = llm(TypeError("unexpected keyword"))

    with pytest.raises(TypeError):
        await client.complete(REQUEST)


def test_schema_is_made_strict() -> None:
    schema = strict_schema(SeniorSynthesisOutput.model_json_schema())

    def check(node: Any) -> None:
        if isinstance(node, dict):
            assert not {"title", "default", "minLength", "minItems"} & set(node)
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                check(v)
        elif isinstance(node, list):
            for v in node:
                check(v)

    check(schema)
    assert "SynthesisClaim" in schema["$defs"]
