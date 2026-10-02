"""Shared Claude transport: one client, refusal fallbacks, structured-output helper.

Features keep their own prompts (features/rag/assistant.py, features/calls/referral.py)
and call this module, so a change to one feature's prompts never touches another's.
"""
from __future__ import annotations

import json
import logging

import anthropic

from .config import settings

log = logging.getLogger("sabeeli.claude")

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    """No API key, the API failed, or the model declined; callers fall back to non-AI behaviour."""


class Claude:
    def __init__(self) -> None:
        if not settings.llm_enabled:
            raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                          timeout=settings.llm_timeout, max_retries=2)
        self.model = settings.model
        self._fallbacks = settings.use_fallbacks

    def create(self, **kw):
        """messages.create with server-side refusal fallbacks when the account supports them."""
        kw.setdefault("model", self.model)
        try:
            if self._fallbacks:
                try:
                    return self.client.beta.messages.create(
                        betas=[FALLBACK_BETA], extra_body={"fallbacks": "default"}, **kw)
                except anthropic.BadRequestError as exc:
                    if "fallback" not in str(exc).lower():
                        raise
                    log.warning("server-side fallbacks unavailable, continuing without: %s", exc)
                    self._fallbacks = False
            return self.client.messages.create(**kw)
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailable("invalid API key") from exc
        except anthropic.RateLimitError as exc:
            raise LLMUnavailable("rate limited") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable("network error") from exc

    @staticmethod
    def system(text: str) -> list[dict]:
        """A cacheable system prompt block (prompts are stable, so repeated calls reuse the cache)."""
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]

    def json(self, system: str, content, schema: dict, max_tokens: int = 2000, effort: str | None = None) -> dict:
        """One structured-output call; returns the parsed JSON object."""
        resp = self.create(
            max_tokens=max_tokens,
            system=self.system(system),
            output_config={"effort": effort or settings.light_effort,
                           "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        )
        if resp.stop_reason == "refusal":
            raise LLMUnavailable("the model declined this request")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMUnavailable("unparseable structured output") from exc


_client: Claude | None = None


def get_claude() -> Claude:
    """The shared client; raises LLMUnavailable when the app runs without a key."""
    global _client
    if _client is None:
        _client = Claude()
    return _client


def usage_dict(resp) -> dict:
    u = getattr(resp, "usage", None)
    if not u:
        return {}
    return {k: getattr(u, k, None) for k in
            ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
