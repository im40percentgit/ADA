"""
AgentErrorHandler — timeout wrapper for agent LLM calls.

Provides a simple async timeout wrapper that returns a configurable fallback
value on TimeoutError rather than raising. Used by BaseAgent to wrap every
LLM call so a hung provider does not block the agent indefinitely.

@decision DEC-RESILIENCE-001
@title Timeout wrapper as standalone coroutine wrapper (not decorator)
@status accepted
@rationale A coroutine-wrapper function is composable and testable without
    mocking. Agents call with_timeout() directly around their llm.complete()
    calls, making the timeout boundary explicit and auditable. A decorator
    would hide the timeout from the call site and make it harder to pass
    different timeout values per call.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout_seconds: float = 30.0,
    fallback: T | None = None,
    agent_name: str = "unknown",
) -> T | None:
    """
    Await a coroutine with a timeout, returning a fallback on TimeoutError.

    On timeout, logs a warning at WARNING level (not exception, since this
    is expected behaviour under load). The caller is responsible for
    publishing AGENT_ERROR events if appropriate.

    Args:
        coro: The coroutine to await.
        timeout_seconds: Maximum seconds to wait before returning fallback.
        fallback: Value returned if the coroutine times out. Defaults to None.
        agent_name: Name of the calling agent, used in log messages.

    Returns:
        The coroutine's return value, or fallback on TimeoutError.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning(
            "Agent %s: LLM call timed out after %.1fs",
            agent_name,
            timeout_seconds,
        )
        return fallback
