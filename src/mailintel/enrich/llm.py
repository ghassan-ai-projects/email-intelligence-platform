"""LLM provider abstraction.

`OpenAICompatProvider` covers every OpenAI-compatible API by pointing `base_url`
at the vendor (DeepSeek, Ollama, Groq, OpenRouter, OpenAI itself).
`AnthropicProvider` uses the native Anthropic SDK.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from ..config import LLMConfig

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


def parse_json_response(text: str) -> dict:
    text = _FENCE.sub("", text.strip()).strip()
    # Some models wrap JSON in prose; grab the outermost object as a fallback.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"No JSON object in LLM response: {text[:200]!r}")
        return json.loads(text[start : end + 1])


class OpenAICompatProvider:
    def __init__(self, cfg: LLMConfig):
        from openai import OpenAI

        if not cfg.api_key:
            raise LLMError(
                f"Missing API key: set the {cfg.api_key_env} environment variable"
            )
        self.cfg = cfg
        self.client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)

    def complete_json(self, system: str, user: str) -> dict:
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        return parse_json_response(content)


class AnthropicProvider:
    def __init__(self, cfg: LLMConfig):
        import anthropic

        if not cfg.api_key:
            raise LLMError(
                f"Missing API key: set the {cfg.api_key_env} environment variable"
            )
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=cfg.api_key)

    def complete_json(self, system: str, user: str) -> dict:
        resp = self.client.messages.create(
            model=self.cfg.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_tokens,
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return parse_json_response(text)


def make_provider(cfg: LLMConfig) -> LLMProvider:
    if cfg.provider == "openai-compat":
        return OpenAICompatProvider(cfg)
    if cfg.provider == "anthropic":
        return AnthropicProvider(cfg)
    raise LLMError(f"Unknown llm.provider: {cfg.provider!r} (use 'openai-compat' or 'anthropic')")
