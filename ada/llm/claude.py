"""
Anthropic Claude LLM provider.

Uses the official anthropic SDK. API key is read from the env var named
in config.llm.claude.api_key_env — never stored in config directly.

@decision DEC-LLM-001
@title Abstract LLMProvider with Claude + OpenAI-compat implementations
@status accepted
@rationale See ada/llm/base.py for full rationale.

@decision DEC-LLM-007
@title Aggressive prompt caching on Opus system prompts
@status accepted
@rationale Opus 4.7 is triggered for clinical reasoning (~50 times/day).
    System prompts for cognitive_assessor, crisis_monitor, fusion, and
    session_summarizer are long and stable across calls. Sending them as
    structured cache_control blocks with type="ephemeral" lets Anthropic
    cache the KV state between calls, cutting Opus input token costs by
    30-50% after warm-up. When prompt_cache_system=False (default), the
    system prompt is sent as a plain string for backward compat.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

import anthropic

from ada.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class ClaudeProvider(LLMProvider):
    """
    LLM provider backed by Anthropic's Claude API.

    Args:
        api_key: Anthropic API key (from environment, never config file).
        model: Claude model ID (e.g. "claude-sonnet-4-6").
        default_max_tokens: Default max tokens if not specified per call.
        default_temperature: Default sampling temperature.
        prompt_cache_system: When True, wrap the system prompt in a
            cache_control={"type":"ephemeral"} block so Anthropic caches
            the KV state. Only effective on models that support caching
            (Opus 4.7, Sonnet 4.6, Haiku 4.5). See DEC-LLM-007.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        default_max_tokens: int = 1024,
        default_temperature: float = 0.7,
        prompt_cache_system: bool = False,
    ) -> None:
        self._model = model
        self._default_max_tokens = default_max_tokens
        self._default_temperature = default_temperature
        self._prompt_cache_system = prompt_cache_system
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    def _build_system(self, system: str | None) -> "str | list[dict] | None":
        """Return system prompt in the appropriate form for the API call.

        When prompt_cache_system is True, wraps the system text in the
        structured block form that activates Anthropic's prompt caching.
        Plain string is returned when caching is off (backward compat).
        """
        if not system:
            return None
        if self._prompt_cache_system:
            return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        return system

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system: str | None = None,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens if max_tokens is not None else self._default_max_tokens,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "messages": messages,
        }
        built_system = self._build_system(system)
        if built_system is not None:
            kwargs["system"] = built_system

        logger.debug("ClaudeProvider: complete request model=%s cache=%s", self._model, self._prompt_cache_system)
        response = await self._client.messages.create(**kwargs)

        content = ""
        if response.content:
            content = response.content[0].text if hasattr(response.content[0], "text") else ""

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "end_turn",
        )

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens if max_tokens is not None else self._default_max_tokens,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "messages": messages,
        }
        built_system = self._build_system(system)
        if built_system is not None:
            kwargs["system"] = built_system

        logger.debug("ClaudeProvider: stream request model=%s cache=%s", self._model, self._prompt_cache_system)
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
