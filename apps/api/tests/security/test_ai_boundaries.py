"""Architectural guarantees about the AI layer, enforced by tests rather than convention.

* An LLM response can never modify financial records: the modules that call the model, run the
  agents or assemble investigations cannot import the persistence layer or a database driver,
  and the model is never offered tools — it can only return text, which is verified.
* All financial figures come from deterministic code: the agents receive the evidence pack
  (built by the engines) and the verifier rejects any number not present in it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import finpulse
from finpulse.agents import llm

SRC = Path(finpulse.__file__).parent
AI_PACKAGES = ("agents", "investigation", "demo")
FORBIDDEN = ("finpulse.persistence", "sqlalchemy", "psycopg", "alembic", "asyncpg")


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_the_ai_layer_cannot_reach_the_database() -> None:
    offenders = []
    for package in AI_PACKAGES:
        for path in (SRC / package).rglob("*.py"):
            for name in imports(path):
                if name.startswith(FORBIDDEN):
                    offenders.append(f"{path.relative_to(SRC)} imports {name}")
    assert not offenders, offenders


def test_the_model_is_never_given_tools() -> None:
    source = inspect.getsource(llm)
    assert "tools=" not in source and '"tools"' not in source and "tool_choice" not in source


def test_engines_do_not_depend_on_the_ai_layer() -> None:
    """Deterministic engines must not be able to take a number from an agent."""
    offenders = []
    for package in ("analytics", "scoring", "early_warning", "stress"):
        for path in (SRC / package).rglob("*.py"):
            for name in imports(path):
                if name.startswith(("finpulse.agents", "finpulse.investigation", "finpulse.demo")):
                    offenders.append(f"{path.relative_to(SRC)} imports {name}")
    assert not offenders, offenders
