"""
Unit tests for ClaudeProvider prompt caching behavior (DEC-LLM-007).

Verifies that when prompt_cache_system=True and a system prompt is passed,
the outgoing API call contains the structured system list with
cache_control={"type": "ephemeral"}, and that the plain-string path is
preserved when caching is off.

@decision DEC-LLM-007
@title Aggressive prompt caching on Opus system prompts
@status accepted
@rationale See ada/llm/claude.py for full rationale.

# @mock-exempt: anthropic.AsyncAnthropic is a third-party HTTP client.
#   Mocking it is the only way to test outgoing API call shapes without
#   making real network requests. The mock replaces the external HTTP
#   boundary only — all ClaudeProvider internal logic is exercised against
#   the real implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ada.llm.claude import ClaudeProvider
from ada.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(content: str = "Hello") -> MagicMock:
    """Build a mock that looks like an anthropic.Message response."""
    mock_content = MagicMock()
    mock_content.text = content
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_response.model = "claude-opus-4-7"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 20
    mock_response.stop_reason = "end_turn"
    return mock_response


def _make_provider(prompt_cache_system: bool) -> tuple[ClaudeProvider, MagicMock]:
    """Create a ClaudeProvider with a mocked AsyncAnthropic client."""
    provider = ClaudeProvider(
        api_key="test-key",
        model="claude-opus-4-7",
        prompt_cache_system=prompt_cache_system,
    )
    mock_client = MagicMock()
    provider._client = mock_client
    return provider, mock_client


# ---------------------------------------------------------------------------
# _build_system helper
# ---------------------------------------------------------------------------

class TestBuildSystem:

    def test_none_input_returns_none(self):
        provider = ClaudeProvider(api_key="k", prompt_cache_system=False)
        assert provider._build_system(None) is None

    def test_empty_string_returns_none(self):
        provider = ClaudeProvider(api_key="k", prompt_cache_system=False)
        assert provider._build_system("") is None

    def test_plain_string_when_cache_off(self):
        provider = ClaudeProvider(api_key="k", prompt_cache_system=False)
        result = provider._build_system("You are a helpful assistant.")
        assert result == "You are a helpful assistant."
        assert isinstance(result, str)

    def test_structured_list_when_cache_on(self):
        provider = ClaudeProvider(api_key="k", prompt_cache_system=True)
        result = provider._build_system("You are a helpful assistant.")
        assert isinstance(result, list)
        assert len(result) == 1
        block = result[0]
        assert block["type"] == "text"
        assert block["text"] == "You are a helpful assistant."
        assert block["cache_control"] == {"type": "ephemeral"}

    def test_cache_on_none_still_returns_none(self):
        provider = ClaudeProvider(api_key="k", prompt_cache_system=True)
        assert provider._build_system(None) is None


# ---------------------------------------------------------------------------
# complete() — cache off
# ---------------------------------------------------------------------------

class TestCompleteNoCaching:

    @pytest.mark.asyncio
    async def test_system_sent_as_plain_string(self):
        """Without caching, system is a plain string in the API call."""
        provider, mock_client = _make_provider(prompt_cache_system=False)
        mock_response = _make_mock_response()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        await provider.complete(
            messages=[{"role": "user", "content": "Hello"}],
            system="You are Ada, a mental health AI.",
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "system" in call_kwargs
        assert call_kwargs["system"] == "You are Ada, a mental health AI."
        assert isinstance(call_kwargs["system"], str)

    @pytest.mark.asyncio
    async def test_no_system_key_when_system_is_none(self):
        """No system key in kwargs when system=None."""
        provider, mock_client = _make_provider(prompt_cache_system=False)
        mock_response = _make_mock_response()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        await provider.complete(messages=[{"role": "user", "content": "Hi"}])

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "system" not in call_kwargs


# ---------------------------------------------------------------------------
# complete() — cache on
# ---------------------------------------------------------------------------

class TestCompleteWithCaching:

    @pytest.mark.asyncio
    async def test_system_sent_as_structured_list(self):
        """With caching on, system is a list with cache_control block."""
        provider, mock_client = _make_provider(prompt_cache_system=True)
        mock_response = _make_mock_response()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        system_text = "You are Ada. You help dementia patients."
        await provider.complete(
            messages=[{"role": "user", "content": "Hello"}],
            system=system_text,
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "system" in call_kwargs
        system_arg = call_kwargs["system"]
        assert isinstance(system_arg, list)
        assert len(system_arg) == 1
        block = system_arg[0]
        assert block["type"] == "text"
        assert block["text"] == system_text
        assert block["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_correct_model_in_call(self):
        provider, mock_client = _make_provider(prompt_cache_system=True)
        mock_response = _make_mock_response()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        await provider.complete(
            messages=[{"role": "user", "content": "Hi"}],
            system="System prompt",
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-7"

    @pytest.mark.asyncio
    async def test_response_parsed_correctly(self):
        provider, mock_client = _make_provider(prompt_cache_system=True)
        mock_response = _make_mock_response("I am Ada.")
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await provider.complete(
            messages=[{"role": "user", "content": "Who are you?"}],
            system="Be Ada.",
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "I am Ada."
        assert result.input_tokens == 100
        assert result.output_tokens == 20


# ---------------------------------------------------------------------------
# stream() — cache behavior
# ---------------------------------------------------------------------------

class TestStreamWithCaching:

    @pytest.mark.asyncio
    async def test_stream_sends_structured_system_when_cache_on(self):
        """stream() also uses the structured system form when cache is on."""
        provider, mock_client = _make_provider(prompt_cache_system=True)

        # Build a mock context manager for client.messages.stream()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        async def _fake_text_stream():
            yield "Hello"
            yield " world"

        mock_stream_ctx.text_stream = _fake_text_stream()
        mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

        system_text = "Streaming system prompt"
        chunks = []
        async for chunk in provider.stream(
            messages=[{"role": "user", "content": "Hi"}],
            system=system_text,
        ):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello world"
        call_kwargs = mock_client.messages.stream.call_args[1]
        system_arg = call_kwargs["system"]
        assert isinstance(system_arg, list)
        assert system_arg[0]["cache_control"] == {"type": "ephemeral"}

    @pytest.mark.asyncio
    async def test_stream_sends_plain_string_when_cache_off(self):
        """stream() uses plain string system when cache is off."""
        provider, mock_client = _make_provider(prompt_cache_system=False)

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        async def _fake_text_stream():
            yield "Hi"

        mock_stream_ctx.text_stream = _fake_text_stream()
        mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

        async for _ in provider.stream(
            messages=[{"role": "user", "content": "Hello"}],
            system="Plain system",
        ):
            pass

        call_kwargs = mock_client.messages.stream.call_args[1]
        assert call_kwargs["system"] == "Plain system"
        assert isinstance(call_kwargs["system"], str)


# ---------------------------------------------------------------------------
# Default model literal
# ---------------------------------------------------------------------------

class TestDefaultModel:

    def test_default_model_is_sonnet_4_6(self):
        """DEC-LLM-006 default: ClaudeProvider defaults to claude-sonnet-4-6."""
        provider = ClaudeProvider(api_key="key")
        assert provider._model == "claude-sonnet-4-6"

    def test_explicit_model_overrides_default(self):
        provider = ClaudeProvider(api_key="key", model="claude-opus-4-7")
        assert provider._model == "claude-opus-4-7"

    def test_prompt_cache_system_default_is_false(self):
        provider = ClaudeProvider(api_key="key")
        assert provider._prompt_cache_system is False
