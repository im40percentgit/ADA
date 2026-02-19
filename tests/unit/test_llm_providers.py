"""
Unit tests for ada.llm — ClaudeProvider, OpenAICompatProvider, and factory.

ClaudeProvider construction is tested without making real API calls.
OpenAICompatProvider is tested with pytest-httpx to mock the HTTP layer.
The factory is tested by patching environment variables and config.

@decision DEC-TEST-003
@title LLM provider tests mock only the external HTTP/SDK boundary
@status accepted
@rationale ClaudeProvider wraps the anthropic SDK (external boundary) and
    OpenAICompatProvider wraps httpx (external boundary). Mocking at these
    seams lets us test the provider logic (message formatting, response
    parsing, error handling) without live API credentials. Internal
    modules (factory, config) are tested with real instances.
"""

from __future__ import annotations

import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock

from ada.core.config import AdaConfig, LLMConfig, OpenAICompatConfig
from ada.llm.base import LLMProvider, LLMResponse
from ada.llm.claude import ClaudeProvider
from ada.llm.factory import create_llm_provider
from ada.llm.openai_compat import OpenAICompatProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openai_response(content: str, model: str = "test-model") -> dict:
    """Build a minimal OpenAI-compatible /chat/completions response body."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }


# ---------------------------------------------------------------------------
# ClaudeProvider — construction and interface
# ---------------------------------------------------------------------------

class TestClaudeProviderConstruction:

    def test_can_instantiate_with_api_key(self):
        provider = ClaudeProvider(api_key="test-key-123")
        assert isinstance(provider, LLMProvider)

    def test_can_instantiate_with_all_params(self):
        provider = ClaudeProvider(
            api_key="test-key",
            model="claude-3-haiku-20240307",
            default_max_tokens=512,
            default_temperature=0.5,
        )
        assert isinstance(provider, LLMProvider)

    def test_is_llmprovider_subclass(self):
        assert issubclass(ClaudeProvider, LLMProvider)

    def test_has_complete_method(self):
        provider = ClaudeProvider(api_key="test-key")
        assert callable(provider.complete)

    def test_has_stream_method(self):
        provider = ClaudeProvider(api_key="test-key")
        assert callable(provider.stream)

    async def test_complete_calls_anthropic_sdk(self):
        """complete() should call the anthropic client; we mock the SDK response."""
        provider = ClaudeProvider(api_key="test-key")

        # Mock the underlying anthropic async client
        mock_content = MagicMock()
        mock_content.text = "Hello from Ada"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.model = "claude-sonnet-4-5-20250514"
        mock_response.usage.input_tokens = 5
        mock_response.usage.output_tokens = 10
        mock_response.stop_reason = "end_turn"

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        result = await provider.complete(
            [{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello from Ada"
        assert result.model == "claude-sonnet-4-5-20250514"
        assert result.input_tokens == 5
        assert result.output_tokens == 10
        assert result.stop_reason == "end_turn"

    async def test_complete_includes_system_prompt_when_provided(self):
        """system= kwarg should be forwarded to the anthropic SDK call."""
        provider = ClaudeProvider(api_key="test-key")

        mock_content = MagicMock()
        mock_content.text = "response"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.model = "claude-sonnet-4-5-20250514"
        mock_response.usage.input_tokens = 1
        mock_response.usage.output_tokens = 1
        mock_response.stop_reason = "end_turn"

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        await provider.complete(
            [{"role": "user", "content": "Hi"}],
            system="You are a helpful assistant.",
        )

        call_kwargs = provider._client.messages.create.call_args[1]
        assert call_kwargs.get("system") == "You are a helpful assistant."

    async def test_complete_omits_system_when_none(self):
        """system=None should NOT add a 'system' key to the SDK call."""
        provider = ClaudeProvider(api_key="test-key")

        mock_content = MagicMock()
        mock_content.text = "response"
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_response.model = "claude-sonnet-4-5-20250514"
        mock_response.usage.input_tokens = 1
        mock_response.usage.output_tokens = 1
        mock_response.stop_reason = "end_turn"

        provider._client.messages.create = AsyncMock(return_value=mock_response)

        await provider.complete([{"role": "user", "content": "Hi"}])

        call_kwargs = provider._client.messages.create.call_args[1]
        assert "system" not in call_kwargs


# ---------------------------------------------------------------------------
# OpenAICompatProvider — HTTP mock via pytest-httpx
# ---------------------------------------------------------------------------

class TestOpenAICompatProvider:

    async def test_complete_returns_llm_response(self, httpx_mock: HTTPXMock):
        body = _openai_response("I understand how you feel.")
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/v1/chat/completions",
            json=body,
        )

        provider = OpenAICompatProvider(
            base_url="http://localhost:8080/v1",
            api_key="none",
            model="test-model",
        )
        result = await provider.complete(
            [{"role": "user", "content": "How are you?"}]
        )
        await provider.close()

        assert isinstance(result, LLMResponse)
        assert result.content == "I understand how you feel."
        assert result.model == "test-model"
        assert result.input_tokens == 10
        assert result.output_tokens == 20
        assert result.stop_reason == "stop"

    async def test_complete_prepends_system_message(self, httpx_mock: HTTPXMock):
        body = _openai_response("Sure!")
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/v1/chat/completions",
            json=body,
        )

        provider = OpenAICompatProvider(base_url="http://localhost:8080/v1")
        await provider.complete(
            [{"role": "user", "content": "Hi"}],
            system="You are Ada.",
        )
        await provider.close()

        request = httpx_mock.get_requests()[0]
        payload = json.loads(request.content)
        assert payload["messages"][0] == {"role": "system", "content": "You are Ada."}
        assert payload["messages"][1]["role"] == "user"

    async def test_complete_without_system_does_not_prepend(self, httpx_mock: HTTPXMock):
        body = _openai_response("OK")
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/v1/chat/completions",
            json=body,
        )

        provider = OpenAICompatProvider(base_url="http://localhost:8080/v1")
        await provider.complete([{"role": "user", "content": "Hi"}])
        await provider.close()

        request = httpx_mock.get_requests()[0]
        payload = json.loads(request.content)
        assert payload["messages"][0]["role"] == "user"
        assert len(payload["messages"]) == 1

    async def test_complete_forwards_max_tokens_and_temperature(self, httpx_mock: HTTPXMock):
        body = _openai_response("OK")
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/v1/chat/completions",
            json=body,
        )

        provider = OpenAICompatProvider(base_url="http://localhost:8080/v1")
        await provider.complete(
            [{"role": "user", "content": "Hi"}],
            max_tokens=256,
            temperature=0.3,
        )
        await provider.close()

        request = httpx_mock.get_requests()[0]
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 256
        assert payload["temperature"] == 0.3

    async def test_http_error_propagates(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/v1/chat/completions",
            status_code=500,
        )

        provider = OpenAICompatProvider(base_url="http://localhost:8080/v1")
        with pytest.raises(Exception):
            await provider.complete([{"role": "user", "content": "Hi"}])
        await provider.close()

    async def test_stream_yields_text_chunks(self, httpx_mock: HTTPXMock):
        # Build a minimal SSE stream body
        chunks = ["Hello", " world", "!"]
        sse_lines = []
        for i, text in enumerate(chunks):
            data = json.dumps({
                "choices": [{"delta": {"content": text}, "finish_reason": None}]
            })
            sse_lines.append(f"data: {data}")
        sse_lines.append("data: [DONE]")
        sse_body = "\n".join(sse_lines) + "\n"

        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/v1/chat/completions",
            text=sse_body,
        )

        provider = OpenAICompatProvider(base_url="http://localhost:8080/v1")
        collected = []
        # stream() is an async generator — iterate directly, no await
        async for chunk in provider.stream([{"role": "user", "content": "Hi"}]):
            collected.append(chunk)
        await provider.close()

        assert collected == ["Hello", " world", "!"]

    def test_is_llmprovider_subclass(self):
        assert issubclass(OpenAICompatProvider, LLMProvider)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestLLMFactory:

    def test_factory_creates_claude_provider(self):
        config = AdaConfig(llm=LLMConfig(provider="claude"))
        provider = create_llm_provider(config)
        assert isinstance(provider, ClaudeProvider)

    def test_factory_creates_openai_compat_provider(self):
        config = AdaConfig(
            llm=LLMConfig(
                provider="openai_compat",
                openai_compat=OpenAICompatConfig(
                    base_url="http://localhost:11434/v1",
                    model="llama3",
                ),
            )
        )
        provider = create_llm_provider(config)
        assert isinstance(provider, OpenAICompatProvider)

    def test_factory_raises_on_unknown_provider(self):
        # Bypass Pydantic validation with a manual override
        config = AdaConfig()
        config.llm.provider = "unknown_provider"  # type: ignore[assignment]
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider(config)

    def test_factory_returns_llmprovider_subclass(self):
        config = AdaConfig(llm=LLMConfig(provider="claude"))
        provider = create_llm_provider(config)
        assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# LLMProvider ABC — streaming interface contract
# ---------------------------------------------------------------------------

class TestLLMProviderContract:
    """Verify that both providers satisfy the LLMProvider ABC contract."""

    def test_claude_provider_is_abstract_base_subclass(self):
        assert issubclass(ClaudeProvider, LLMProvider)

    def test_openai_compat_provider_is_abstract_base_subclass(self):
        assert issubclass(OpenAICompatProvider, LLMProvider)

    def test_llm_response_dataclass_fields(self):
        resp = LLMResponse(content="hi", model="test")
        assert resp.content == "hi"
        assert resp.model == "test"
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0
        assert resp.stop_reason == "end_turn"
