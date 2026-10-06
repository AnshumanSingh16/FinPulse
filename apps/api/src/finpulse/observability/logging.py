"""Structured logging.

Everything — our own ``structlog`` loggers and stdlib loggers such as uvicorn's — goes through
one processor chain, so every line has the same shape and carries the request context bound in
``finpulse.api.middleware``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from finpulse.config import Settings

# Keys whose values must never reach a log line. Matching is on the key name, case-insensitive,
# and applies to nested dicts too. Financial narrations and counterparties are included now so
# the policy is in place before any real data exists.
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "api_key",
        "llm_api_key",
        "database_url",
        "description",
        "counterparty_name",
        "account_number",
    }
)
REDACTED = "[redacted]"


def _redact(value: Any) -> Any:
    if isinstance(value, MutableMapping):
        return {
            k: (REDACTED if str(k).lower() in SENSITIVE_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def redact_sensitive(_: Any, __: str, event_dict: EventDict) -> EventDict:
    return {
        k: (REDACTED if k.lower() in SENSITIVE_KEYS else _redact(v)) for k, v in event_dict.items()
    }


def configure_logging(settings: Settings) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive,
    ]
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # Our middleware writes one access line per request with the request id; uvicorn's own
    # access log would duplicate it without that context.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
