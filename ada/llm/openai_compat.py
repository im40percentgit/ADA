"""
OpenAI-compatible LLM provider.

Uses httpx to call any /v1/chat/completions endpoint — Ollama, LM Studio,
vLLM, or any OpenAI-spec server. This lets Ada run entirely on local models
without a cloud dependency.

@decision DEC-LLM-001
@title Abstract LLMProvider with Claude + OpenAI-compat implementations
@status accepted
@rationale See ada/llm/base.py for full rationale.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from ada.llm.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMProvider):
    """
    LLM provider for any OpenAI-compatible /v1/chat/completions endpoint.

    Args:
        base_url: Base URL of the API server (e.g. "http://localhost:8080/v1").
        api_key: API key (may be "none" for local servers that don't require one).
        model: Model name as recognised by the server.
        default_max_tokens: Default max tokens if not specified per call.
        default_temperature: Default sampling temperature.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "none",
        model: str = "local-model",
        default_max_tokens: int = 1024,
        default_temperature: float = 0.7,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._default_max_tokens = default_max_tokens
        self._default_temperature = default_temperature
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system: str | None = None,
    ) -> LLMResponse:
        all_messages = list(messages)
        if system:
            all_messages = [{"role": "system", "content": system}] + all_messages

        payload = {
            "model": self._model,
            "messages": all_messages,
            "max_tokens": max_tokens if max_tokens is not None else self._default_max_tokens,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "stream": False,
        }

        logger.debug("OpenAICompatProvider: complete request model=%s", self._model)
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=data["choices"][0].get("finish_reason", "stop"),
        )

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        all_messages = list(messages)
        if system:
            all_messages = [{"role": "system", "content": system}] + all_messages

        payload = {
            "model": self._model,
            "messages": all_messages,
            "max_tokens": max_tokens if max_tokens is not None else self._default_max_tokens,
            "temperature": temperature if temperature is not None else self._default_temperature,
            "stream": True,
        }

        logger.debug("OpenAICompatProvider: stream request model=%s", self._model)
        async with self._client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        yield text
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
