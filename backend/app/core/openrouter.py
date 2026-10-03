"""Shared OpenRouter transport (an OpenAI-compatible API for many models; default Gemma 4 31B).

Same contract as core/claude.py, so features don't care which provider runs:
  json(system, content, schema)  - one structured-output call, returns the parsed object;
  chat(system, content)          - plain text, with token usage and the model that answered.
Content may be a string or Anthropic-style blocks (text, base64 image); they are converted here.

Claude-only features (search-result citations, refusal fallbacks, prompt caching) don't exist here:
features/rag/assistant.py asks the model to cite numbered sources instead, and the pipeline's strict
grounding still drops every sentence that cites nothing.

Privacy: by default requests may only go to OpenRouter providers that don't store or train on
prompts (provider.data_collection = "deny"); SABEELI_OPENROUTER_PRIVATE=0 lifts that.
"""
from __future__ import annotations

import json
import logging
import re
import time

import httpx

from . import timing
from .config import settings

log = logging.getLogger("sabeeli.openrouter")

URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouter:
    kind = "openrouter"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        from .claude import LLMUnavailable

        if not settings.llm_enabled:
            raise LLMUnavailable("OPENROUTER_API_KEY is not set")
        self.model = settings.model
        self._schema_ok = True      # turned off if the model or provider rejects json_schema
        self.http = httpx.Client(timeout=settings.llm_timeout, transport=transport, headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://github.com/mushari44/Islam-hackthon",
            "X-Title": "Sabeeli",
        })

    # ---- content -------------------------------------------------------------------
    @staticmethod
    def _content(content) -> str | list[dict]:
        """Anthropic-style blocks -> OpenAI-style parts (text and base64 images)."""
        if isinstance(content, str):
            return content
        parts = []
        for b in content:
            if b.get("type") == "text":
                parts.append({"type": "text", "text": b["text"]})
            elif b.get("type") == "image" and b.get("source", {}).get("type") == "base64":
                src = b["source"]
                parts.append({"type": "image_url",
                              "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}})
        return parts

    # ---- transport -----------------------------------------------------------------
    def _post(self, body: dict) -> dict:
        from .claude import LLMUnavailable

        body = {"model": self.model, **body}
        if settings.openrouter_private:
            body["provider"] = {"data_collection": "deny"}
        if settings.openrouter_sort:
            body.setdefault("provider", {})["sort"] = settings.openrouter_sort
        t0 = time.perf_counter()
        try:
            r = self.http.post(URL, json=body)
        except httpx.HTTPError as exc:
            raise LLMUnavailable("network error") from exc
        elapsed = time.perf_counter() - t0
        if r.status_code in (401, 403):
            raise LLMUnavailable("invalid OpenRouter API key")
        if r.status_code == 429:
            raise LLMUnavailable("rate limited")
        if r.status_code == 402:
            raise LLMUnavailable("OpenRouter credits exhausted")
        if r.status_code >= 400:
            text = r.text[:300]
            if r.status_code == 404 and "data" in text.lower():
                log.warning("no provider for %s accepts data_collection=deny; set SABEELI_OPENROUTER_PRIVATE=0 "
                            "to allow others (check their data policy first)", self.model)
            raise LLMUnavailable(f"API error {r.status_code}: {text}")
        data = r.json()
        if data.get("error"):
            raise LLMUnavailable(f"API error: {str(data['error'])[:300]}")
        u = data.get("usage") or {}
        timing.llm_call(data.get("provider") or "openrouter", data.get("model") or self.model, elapsed,
                        u.get("prompt_tokens"), u.get("completion_tokens"))
        return data

    @staticmethod
    def _text(data: dict) -> tuple[str, str]:
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        return msg.get("content") or "", choice.get("finish_reason") or ""

    @staticmethod
    def usage(data: dict) -> dict:
        u = data.get("usage") or {}
        return {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")}

    # ---- calls ---------------------------------------------------------------------
    def chat(self, system: str, content, max_tokens: int = 2000, temperature: float = 0.2) -> tuple[str, dict]:
        """Plain text answer; returns (text, raw response)."""
        data = self._post({"max_tokens": max_tokens, "temperature": temperature, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": self._content(content)}]})
        text, _ = self._text(data)
        return text, data

    def json(self, system: str, content, schema: dict, max_tokens: int = 2000, effort: str | None = None) -> dict:
        """One structured-output call; returns the parsed JSON object (effort is Claude-only, ignored)."""
        from .claude import LLMUnavailable

        messages = [{"role": "system", "content": system}, {"role": "user", "content": self._content(content)}]
        body = {"max_tokens": max_tokens, "temperature": 0, "messages": messages}
        if self._schema_ok:
            try:
                data = self._post({**body, "response_format": {
                    "type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": schema}}})
                return _parse(self._text(data)[0])
            except LLMUnavailable as exc:
                msg = str(exc).lower()
                if not any(w in msg for w in ("response_format", "json_schema", "structured", "schema")):
                    raise   # an unrelated failure (a rejected image, a bad reply) must not drop the schema for good
                log.warning("json_schema not accepted by %s, using json_object: %s", self.model, exc)
                self._schema_ok = False
        hint = "\n\nReply with one JSON object only, matching this JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
        data = self._post({**body, "messages": [{"role": "system", "content": system + hint}, messages[1]],
                           "response_format": {"type": "json_object"}})
        return _parse(self._text(data)[0])


def _parse(text: str) -> dict:
    from .claude import LLMUnavailable

    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    elif not text.startswith("{") and "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    try:
        out = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("unparseable structured output") from exc
    if not isinstance(out, dict):
        raise LLMUnavailable("unparseable structured output")
    return out
