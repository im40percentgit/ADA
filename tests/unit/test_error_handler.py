"""
Tests for ada.agents.error_handler — with_timeout() wrapper.

@decision DEC-RESILIENCE-001
@title Timeout wrapper as standalone coroutine wrapper (not decorator)
@status accepted
@rationale A coroutine-wrapper function is composable and testable without
    mocking. Tests use real asyncio.sleep() to trigger timeouts rather than
    patching time, ensuring the behaviour is real rather than simulated.
"""

from __future__ import annotations

import asyncio

import pytest

from ada.agents.error_handler import with_timeout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fast_coro(value: str) -> str:
    """Coroutine that completes immediately."""
    return value


async def _slow_coro(delay: float, value: str) -> str:
    """Coroutine that sleeps before returning."""
    await asyncio.sleep(delay)
    return value


async def _failing_coro() -> str:
    """Coroutine that raises an exception (not TimeoutError)."""
    raise ValueError("LLM API error")


# ---------------------------------------------------------------------------
# Normal completion
# ---------------------------------------------------------------------------

class TestNormalCompletion:
    async def test_returns_coroutine_result(self):
        result = await with_timeout(_fast_coro("hello"), timeout_seconds=1.0)
        assert result == "hello"

    async def test_returns_result_within_timeout(self):
        result = await with_timeout(
            _slow_coro(0.01, "ok"), timeout_seconds=1.0
        )
        assert result == "ok"

    async def test_fallback_not_used_on_success(self):
        result = await with_timeout(
            _fast_coro("real"), timeout_seconds=1.0, fallback="fallback"
        )
        assert result == "real"


# ---------------------------------------------------------------------------
# Timeout behaviour
# ---------------------------------------------------------------------------

class TestTimeoutBehaviour:
    async def test_returns_none_fallback_on_timeout(self):
        result = await with_timeout(
            _slow_coro(10.0, "never"), timeout_seconds=0.01
        )
        assert result is None

    async def test_returns_custom_fallback_on_timeout(self):
        fallback_value = "I'm having a moment — could you try saying that again?"
        result = await with_timeout(
            _slow_coro(10.0, "never"),
            timeout_seconds=0.01,
            fallback=fallback_value,
        )
        assert result == fallback_value

    async def test_does_not_raise_on_timeout(self):
        # Must NOT raise asyncio.TimeoutError — swallows it and returns fallback
        try:
            await with_timeout(_slow_coro(10.0, "never"), timeout_seconds=0.01)
        except asyncio.TimeoutError:
            pytest.fail("with_timeout must not propagate TimeoutError")

    async def test_timeout_without_fallback_returns_none(self):
        result = await with_timeout(
            _slow_coro(10.0, "never"), timeout_seconds=0.01
        )
        assert result is None

    async def test_agent_name_accepted(self):
        """agent_name parameter is accepted without error."""
        result = await with_timeout(
            _fast_coro("ok"), timeout_seconds=1.0, agent_name="wellness_companion"
        )
        assert result == "ok"


# ---------------------------------------------------------------------------
# Non-timeout exceptions propagate
# ---------------------------------------------------------------------------

class TestExceptionPropagation:
    async def test_non_timeout_exception_propagates(self):
        """with_timeout does not catch non-TimeoutError exceptions."""
        with pytest.raises(ValueError, match="LLM API error"):
            await with_timeout(_failing_coro(), timeout_seconds=1.0)

    async def test_fallback_not_used_on_non_timeout_error(self):
        """Fallback is only for TimeoutError, not general exceptions."""
        with pytest.raises(ValueError):
            await with_timeout(
                _failing_coro(), timeout_seconds=1.0, fallback="fallback"
            )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    async def test_very_long_timeout_completes_normally(self):
        result = await with_timeout(_fast_coro("done"), timeout_seconds=60.0)
        assert result == "done"

    async def test_fallback_can_be_dict(self):
        result = await with_timeout(
            _slow_coro(10.0, "never"),
            timeout_seconds=0.01,
            fallback={"error": "timeout"},
        )
        assert result == {"error": "timeout"}

    async def test_fallback_can_be_integer(self):
        result = await with_timeout(
            _slow_coro(10.0, "never"),
            timeout_seconds=0.01,
            fallback=42,
        )
        assert result == 42
