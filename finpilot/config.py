"""Settings from the environment (and an optional .env file). No secrets live in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    """Minimal .env reader (KEY=VALUE lines); real environment variables win."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    model: str
    max_agent_steps: int
    db_path: Path
    ai_disabled: bool

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key) and not self.ai_disabled


def settings() -> Settings:
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model=os.environ.get("FINPILOT_MODEL", "claude-opus-5-5"),
        max_agent_steps=int(os.environ.get("FINPILOT_MAX_STEPS", "8")),
        db_path=Path(os.environ.get("FINPILOT_DB", ROOT / "finpilot.db")),
        ai_disabled=os.environ.get("FINPILOT_AI", "").lower() == "off",
    )
