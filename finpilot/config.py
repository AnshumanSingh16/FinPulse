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


def env_path() -> Path:
    return Path(os.environ.get("FINPILOT_ENV_FILE") or ROOT / ".env")


def local_env() -> dict[str, str]:
    """KEY=VALUE pairs in the project's local .env file (never committed; see .gitignore)."""
    path = env_path()
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def save_local(key: str, value: str | None) -> None:
    """Set (or with None, remove) one variable in the local .env file and in this process."""
    path = env_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [ln for ln in lines if not (ln.strip().split("=", 1)[0].strip() == key and "=" in ln)]
    if value is not None:
        lines.append(f"{key}={value}")
        os.environ[key] = value
    else:
        os.environ.pop(key, None)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    try:
        path.chmod(0o600)  # the file can hold an API key: owner-only where the OS supports it
    except OSError:
        pass


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    model: str
    max_agent_steps: int
    db_path: Path
    ai_disabled: bool
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    provider_choice: str = ""

    @property
    def provider(self) -> str:
        """'gemini' or 'anthropic': FINPILOT_PROVIDER if set, else whichever key is present (Anthropic first, as before)."""
        if self.provider_choice in ("gemini", "anthropic"):
            return self.provider_choice
        return "anthropic" if self.anthropic_api_key or not self.gemini_api_key else "gemini"

    @property
    def api_key(self) -> str | None:
        return self.gemini_api_key if self.provider == "gemini" else self.anthropic_api_key

    @property
    def active_model(self) -> str:
        return self.gemini_model if self.provider == "gemini" else self.model

    @property
    def ai_enabled(self) -> bool:
        return bool(self.api_key) and not self.ai_disabled


def settings() -> Settings:
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model=os.environ.get("FINPILOT_MODEL", "claude-opus-5-5"),
        max_agent_steps=int(os.environ.get("FINPILOT_MAX_STEPS", "8")),
        db_path=Path(os.environ.get("FINPILOT_DB", ROOT / "finpilot.db")),
        ai_disabled=os.environ.get("FINPILOT_AI", "").lower() == "off",
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None,
        gemini_model=os.environ.get("FINPILOT_GEMINI_MODEL", "gemini-flash-latest"),
        provider_choice=os.environ.get("FINPILOT_PROVIDER", "").lower(),
    )
