"""
Tests for ada.agents.circuit_breaker — CircuitBreaker three-state machine.

@decision DEC-RESILIENCE-002
@title Per-agent circuit breaker with sliding window failure counting
@status accepted
@rationale Tests use real asyncio coroutines and real time (short timeouts
    via asyncio.sleep) to exercise state transitions. No internal mocking.
    The recovery_timeout_seconds is set to 0.05s in tests that need to
    exercise HALF_OPEN transitions — small enough to not slow the suite.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from ada.agents.circuit_breaker import CircuitBreaker, CircuitState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ok_coro(value: str = "ok") -> str:
    return value


async def _fail_coro(msg: str = "fail") -> str:
    raise RuntimeError(msg)


def _make_breaker(
    failure_threshold: int = 3,
    failure_window_seconds: float = 60.0,
    recovery_timeout_seconds: float = 120.0,
) -> CircuitBreaker:
    return CircuitBreaker(
        agent_name="test_agent",
        failure_threshold=failure_threshold,
        failure_window_seconds=failure_window_seconds,
        recovery_timeout_seconds=recovery_timeout_seconds,
    )


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_starts_closed(self):
        cb = _make_breaker()
        assert cb.state == CircuitState.CLOSED
        assert not cb.is_open

    def test_failure_count_zero_initially(self):
        cb = _make_breaker()
        assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# CLOSED state — normal operation
# ---------------------------------------------------------------------------

class TestClosedState:
    async def test_successful_call_returns_result(self):
        cb = _make_breaker()
        result = await cb.call(_ok_coro("hello"))
        assert result == "hello"

    async def test_failed_call_raises_and_records_failure(self):
        cb = _make_breaker(failure_threshold=5)
        with pytest.raises(RuntimeError):
            await cb.call(_fail_coro())
        assert cb.failure_count == 1
        assert cb.state == CircuitState.CLOSED

    async def test_stays_closed_below_threshold(self):
        cb = _make_breaker(failure_threshold=3)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 2


# ---------------------------------------------------------------------------
# CLOSED → OPEN transition
# ---------------------------------------------------------------------------

class TestClosedToOpen:
    async def test_opens_at_threshold(self):
        cb = _make_breaker(failure_threshold=3)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.state == CircuitState.OPEN
        assert cb.is_open

    async def test_open_circuit_returns_fallback_without_calling(self):
        cb = _make_breaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.is_open

        # Now call with a coro that would raise — should NOT raise (short-circuited)
        result = await cb.call(_fail_coro(), fallback="fallback_value")
        assert result == "fallback_value"

    async def test_open_circuit_returns_none_fallback_by_default(self):
        cb = _make_breaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())

        result = await cb.call(_ok_coro())
        assert result is None

    async def test_configurable_thresholds(self):
        """Thresholds are applied correctly when set non-default."""
        cb = _make_breaker(failure_threshold=5)
        for _ in range(4):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.state == CircuitState.CLOSED  # Still closed at 4

        with pytest.raises(RuntimeError):
            await cb.call(_fail_coro())
        assert cb.state == CircuitState.OPEN   # Opens at 5


# ---------------------------------------------------------------------------
# Sliding window — failures expire
# ---------------------------------------------------------------------------

class TestSlidingWindow:
    def test_old_failures_pruned_from_window(self):
        cb = _make_breaker(failure_threshold=3, failure_window_seconds=0.05)
        # Record two failures directly
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

        # Wait for window to expire, then check count again
        time.sleep(0.06)
        assert cb.failure_count == 0

    async def test_circuit_does_not_open_on_expired_failures(self):
        cb = _make_breaker(failure_threshold=3, failure_window_seconds=0.05)
        # Record 2 failures — below threshold
        cb.record_failure()
        cb.record_failure()

        # Wait for window to expire
        await asyncio.sleep(0.06)

        # One fresh failure — only 1 in window, should not open
        with pytest.raises(RuntimeError):
            await cb.call(_fail_coro())
        assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN transition (real time, short recovery_timeout)
# ---------------------------------------------------------------------------

class TestOpenToHalfOpen:
    async def test_transitions_to_half_open_after_recovery_timeout(self):
        # Use a very short recovery timeout so the test doesn't need mocking
        cb = _make_breaker(failure_threshold=2, recovery_timeout_seconds=0.05)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout to elapse
        await asyncio.sleep(0.06)

        # _evaluate_state() should now report HALF_OPEN
        state = cb._evaluate_state()
        assert state == CircuitState.HALF_OPEN

    async def test_open_circuit_stays_open_before_recovery_timeout(self):
        cb = _make_breaker(failure_threshold=2, recovery_timeout_seconds=120.0)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.state == CircuitState.OPEN

        # Evaluating state immediately should keep it OPEN
        state = cb._evaluate_state()
        assert state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# HALF_OPEN probe — success → CLOSED
# ---------------------------------------------------------------------------

class TestHalfOpenProbeSuccess:
    async def test_successful_probe_closes_circuit(self):
        cb = _make_breaker(failure_threshold=2, recovery_timeout_seconds=0.05)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.is_open

        # Wait for recovery timeout
        await asyncio.sleep(0.06)

        result = await cb.call(_ok_coro("recovered"))
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    async def test_successful_probe_clears_failure_count(self):
        cb = _make_breaker(failure_threshold=2, recovery_timeout_seconds=0.05)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())

        await asyncio.sleep(0.06)
        await cb.call(_ok_coro())

        assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# HALF_OPEN probe — failure → OPEN
# ---------------------------------------------------------------------------

class TestHalfOpenProbeFailure:
    async def test_failed_probe_reopens_circuit(self):
        cb = _make_breaker(failure_threshold=2, recovery_timeout_seconds=0.05)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(_fail_coro())
        assert cb.is_open

        await asyncio.sleep(0.06)

        with pytest.raises(RuntimeError):
            await cb.call(_fail_coro())
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# record_success / record_failure direct API
# ---------------------------------------------------------------------------

class TestDirectRecordAPI:
    def test_record_failure_increments_count(self):
        cb = _make_breaker(failure_threshold=5)
        cb.record_failure()
        assert cb.failure_count == 1

    def test_record_failure_opens_at_threshold(self):
        cb = _make_breaker(failure_threshold=3)
        opened = False
        for _ in range(3):
            opened = cb.record_failure()
        assert opened is True
        assert cb.state == CircuitState.OPEN

    def test_record_success_closes_open_circuit(self):
        cb = _make_breaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset_clears_state(self):
        cb = _make_breaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
