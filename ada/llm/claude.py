"""
Anthropic Claude LLM provider.

Uses the official anthropic SDK. API key is read from the env var named
in config.llm.claude.api_key_env — never stored in config directly.

@decision DEC-LLM-001
@title Abstract LLMProvider with Claude + OpenAI-compat implementations
@status accepted
@rationale See ada/llm/base.py for full rationale.
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
        model: Claude model ID (e.g. "claude-sonnet-4-5-20250514").
        default_max_tokens: Default max tokens if not specified per call.
        default_temperature: Default sampling temperature.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5-20250514",
        default_max_tokens: int = 1024,
        default_temperature: float = 0.7,
    ) -> None:
        self._model = model
        self._default_max_tokens = default_max_tokens
        self._default_temperature = default_temperature
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

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
        if system:
            kwargs["system"] = system

        logger.debug("ClaudeProvider: complete request model=%s", self._model)
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
        if system:
            kwargs["system"] = system

        logger.debug("ClaudeProvider: stream request model=%s", self._model)
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
