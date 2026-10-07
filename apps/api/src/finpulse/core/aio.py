"""Event loops that work with psycopg's async mode on every platform.

On Windows, asyncio defaults to the Proactor event loop, which psycopg cannot use ("Psycopg
cannot use the 'ProactorEventLoop' to run in async mode"). Everything that runs async database
code outside the test suite goes through ``run`` (CLI, migrations) or ``event_loop`` (the API
server, via uvicorn's ``loop`` setting).
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any

IS_WINDOWS = sys.platform == "win32"


def event_loop() -> asyncio.AbstractEventLoop:
    """A new event loop psycopg can use: a selector loop on Windows, the default elsewhere."""
    if IS_WINDOWS:
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """``asyncio.run`` on a psycopg-compatible loop."""
    return asyncio.run(coro, loop_factory=event_loop if IS_WINDOWS else None)
