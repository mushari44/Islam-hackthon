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


DEFAULT_MODELS = {"openrouter": "google/gemma-4-31b-it", "anthropic": "claude-opus-5-5"}
_PROVIDER = (os.getenv("SABEELI_LLM_PROVIDER", "").strip().lower()
             or ("openrouter" if os.getenv("OPENROUTER_API_KEY") else "anthropic"))
if _PROVIDER not in DEFAULT_MODELS:
    _PROVIDER = "openrouter"


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    corpus_dir: Path = ROOT / "data" / "corpus"
    frontend_dir: Path = ROOT / "frontend" / "dist"   # built by `npm run build` in frontend/

    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'sabeeli.db').as_posix()}")
    secret_key: str = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)

    # The language model. Provider "openrouter" (default when OPENROUTER_API_KEY is set; Gemma 4 31B)
    # or "anthropic" (Claude). The app runs without a key in "sources-only" mode.
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    llm_provider: str = _PROVIDER
    model: str = os.getenv("SABEELI_MODEL") or DEFAULT_MODELS[_PROVIDER]
    # Only OpenRouter providers that don't store or train on prompts (seekers' questions).
    openrouter_private: bool = _bool("SABEELI_OPENROUTER_PRIVATE", True)
    # Among the allowed providers, prefer the fastest ("throughput"), the quickest to start ("latency"),
    # or the cheapest ("price"); "" lets OpenRouter balance them.
    openrouter_sort: str = os.getenv("SABEELI_OPENROUTER_SORT", "throughput")
    answer_effort: str = os.getenv("SABEELI_ANSWER_EFFORT", "medium")
    light_effort: str = os.getenv("SABEELI_LIGHT_EFFORT", "low")
    use_fallbacks: bool = _bool("SABEELI_FALLBACKS", True)
    llm_timeout: float = float(os.getenv("SABEELI_LLM_TIMEOUT", "90"))

    # Retrieval
    top_k: int = int(os.getenv("SABEELI_TOP_K", "8"))
    # Grounding: model text without a citation to an approved passage is never shown,
    # except short connecting phrases of at most this many words.
    strict_grounding: bool = _bool("SABEELI_STRICT_GROUNDING", True)
    max_uncited_words: int = int(os.getenv("SABEELI_MAX_UNCITED_WORDS", "6"))

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
        key = self.openrouter_api_key if self.llm_provider == "openrouter" else self.anthropic_api_key
        return bool(key) and not self.offline


settings = Settings()
