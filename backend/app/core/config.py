"""Runtime settings, read once from the environment and the project's own .env file."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
# Only the project's .env, never a parent folder's (find_dotenv would walk upwards).
load_dotenv(ROOT / ".env", override=False)


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    corpus_dir: Path = ROOT / "data" / "corpus"
    frontend_dir: Path = ROOT / "frontend" / "dist"   # built by `npm run build` in frontend/

    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'sabeeli.db').as_posix()}")
    secret_key: str = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)

    # Claude. The app runs without a key in "sources-only" mode.
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("SABEELI_MODEL", "claude-opus-5-5")
    answer_effort: str = os.getenv("SABEELI_ANSWER_EFFORT", "medium")
    light_effort: str = os.getenv("SABEELI_LIGHT_EFFORT", "low")
    use_fallbacks: bool = _bool("SABEELI_FALLBACKS", True)
    llm_timeout: float = float(os.getenv("SABEELI_LLM_TIMEOUT", "90"))

    # Retrieval
    top_k: int = int(os.getenv("SABEELI_TOP_K", "8"))

    # Calls (WebRTC). STUN is enough on most networks; set TURN for strict NATs,
    # and CALL_RELAY_ONLY=1 to keep the seeker's and the da'i's IPs private.
    stun_urls: list[str] = field(default_factory=lambda: _list("STUN_URLS", "stun:stun.l.google.com:19302"))
    turn_url: str = os.getenv("TURN_URL", "")
    turn_username: str = os.getenv("TURN_USERNAME", "")
    turn_credential: str = os.getenv("TURN_CREDENTIAL", "")
    call_relay_only: bool = _bool("CALL_RELAY_ONLY", False)
    call_wait_seconds: int = int(os.getenv("CALL_WAIT_SECONDS", "600"))

    # Privacy: seeker chat turns are deleted after this many hours.
    retention_hours: int = int(os.getenv("RETENTION_HOURS", "24"))

    # Demo data (synthetic accounts, groups and meetups) for judges and local runs.
    seed_demo: bool = _bool("SEED_DEMO", True)

    # Forces sources-only mode even when a key is present (tests, offline demos).
    offline: bool = _bool("SABEELI_OFFLINE", False)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key) and not self.offline


settings = Settings()
