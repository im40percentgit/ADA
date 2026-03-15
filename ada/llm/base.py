"""
LLM provider abstraction — ABC and response model.

@decision DEC-LLM-001
@title Abstract LLMProvider with Claude + OpenAI-compat implementations
@status accepted
@rationale Phase 1 must support both the Anthropic Claude API (primary) and
    any OpenAI-compatible endpoint (for local models, Ollama, LM Studio, etc.).
    An ABC ensures both providers expose identical interfaces so agents never
    need to branch on provider type. The factory selects the provider at startup
    based on config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LLMResponse:
    """Structured response from an LLM provider."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "end_turn"
    reasoning: str = ""


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Agents call ``complete()`` for a full response or ``stream()`` for
    token-by-token streaming to the WebSocket.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> LLMResponse:
        """
        Request a complete (non-streaming) response.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            system: Optional system prompt (overrides provider default).

        Returns:
            LLMResponse with the generated content.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a response token by token.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            system: Optional system prompt (overrides provider default).

        Yields:
            Text chunks as they arrive from the provider.
        """
        ...
