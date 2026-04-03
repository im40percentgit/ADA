"""
CircuitBreaker — per-agent failure isolation with three-state machine.

Prevents cascading failures when an LLM provider is degraded. Each agent
instance owns one CircuitBreaker. The breaker tracks recent failures in a
time-bounded window; when failures exceed the threshold the circuit opens
and all requests short-circuit to a fallback until the recovery timeout
elapses.

State machine:
    CLOSED  ──(failure_threshold reached)──→  OPEN
    OPEN    ──(recovery_timeout elapsed)───→  HALF_OPEN
    HALF_OPEN ──(probe succeeds)───────────→  CLOSED
    HALF_OPEN ──(probe fails)──────────────→  OPEN

@decision DEC-RESILIENCE-002
@title Per-agent circuit breaker with sliding window failure counting
@status accepted
@rationale A sliding window (vs. cumulative count) prevents a breaker from
    staying open forever after an early burst of failures that has long since
    resolved. Each failure timestamp is recorded; the window check discards
    entries older than failure_window_seconds before comparing to threshold.
    This means a brief spike opens the circuit, but sustained recovery
    naturally clears the window and allows re-close via the half-open probe.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from enum import Enum
from typing import Any, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Three-state circuit breaker for a single agent's LLM calls.

    Args:
        agent_name: Name of the agent this breaker protects (used in logs).
        failure_threshold: Number of failures within failure_window_seconds
            needed to open the circuit.
        failure_window_seconds: Rolling window over which failures are counted.
        recovery_timeout_seconds: Time the circuit stays open before allowing
            a half-open probe request.
    """

    def __init__(
        self,
        agent_name: str,
        failure_threshold: int = 5,
        failure_window_seconds: float = 60.0,
        recovery_timeout_seconds: float = 120.0,
    ) -> None:
        self.agent_name = agent_name
        self.failure_threshold = failure_threshold
        self.failure_window_seconds = failure_window_seconds
        self.recovery_timeout_seconds = recovery_timeout_seconds

        self._state: CircuitState = CircuitState.CLOSED
        # Timestamps of recent failures (monotonic clock)
        self._failure_times: deque[float] = deque()
        # When the circuit was opened (monotonic clock)
        self._opened_at: float | None = None
        # Lock prevents concurrent probe requests during HALF_OPEN
        self._probe_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def failure_count(self) -> int:
        """Count of failures within the current sliding window."""
        self._prune_old_failures()
        return len(self._failure_times)

    async def call(
        self,
        coro: Coroutine[Any, Any, T],
        fallback: T | None = None,
    ) -> T | None:
        """
        Execute a coroutine through the circuit breaker.

        - CLOSED: runs the coroutine, records failure on exception.
        - OPEN: short-circuits immediately, returns fallback.
        - HALF_OPEN: allows one probe; success closes, failure re-opens.

        Args:
            coro: The coroutine to protect (e.g., llm.complete(...)).
            fallback: Value returned when the circuit is open or probe fails.

        Returns:
            Coroutine result on success, or fallback on open/failure.
        """
        current_state = self._evaluate_state()

        if current_state == CircuitState.OPEN:
            logger.warning(
                "CircuitBreaker[%s]: circuit OPEN — short-circuiting to fallback",
                self.agent_name,
            )
            # Close the coroutine to suppress "coroutine was never awaited" warnings.
            # The caller passed a coroutine object; we must close it explicitly
            # when we decide not to await it.
            coro.close()
            return fallback

        if current_state == CircuitState.HALF_OPEN:
            return await self._probe(coro, fallback)

        # CLOSED — run normally
        return await self._run(coro, fallback)

    def record_success(self) -> None:
        """Record a successful call. Closes an open/half-open circuit."""
        if self._state in (CircuitState.OPEN, CircuitState.HALF_OPEN):
            logger.info(
                "CircuitBreaker[%s]: success — transitioning to CLOSED",
                self.agent_name,
            )
            self._state = CircuitState.CLOSED
            self._failure_times.clear()
            self._opened_at = None

    def record_failure(self) -> bool:
        """
        Record a failure. Opens the circuit if threshold is reached.

        Returns:
            True if this failure caused the circuit to open.
        """
        now = time.monotonic()
        self._failure_times.append(now)
        self._prune_old_failures()

        if len(self._failure_times) >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = now
                logger.error(
                    "CircuitBreaker[%s]: %d failures in %.0fs — circuit OPENED",
                    self.agent_name,
                    len(self._failure_times),
                    self.failure_window_seconds,
                )
                return True
        return False

    def reset(self) -> None:
        """Force-reset the breaker to CLOSED. For testing only."""
        self._state = CircuitState.CLOSED
        self._failure_times.clear()
        self._opened_at = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_state(self) -> CircuitState:
        """
        Re-evaluate state based on elapsed time.

        If OPEN and recovery_timeout has elapsed, transition to HALF_OPEN.
        """
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.recovery_timeout_seconds:
                logger.info(
                    "CircuitBreaker[%s]: recovery timeout elapsed (%.0fs) — entering HALF_OPEN",
                    self.agent_name,
                    elapsed,
                )
                self._state = CircuitState.HALF_OPEN
        return self._state

    def _prune_old_failures(self) -> None:
        """Remove failure timestamps outside the sliding window."""
        cutoff = time.monotonic() - self.failure_window_seconds
        while self._failure_times and self._failure_times[0] < cutoff:
            self._failure_times.popleft()

    async def _run(
        self,
        coro: Coroutine[Any, Any, T],
        fallback: T | None,
    ) -> T | None:
        """Run the coroutine in CLOSED state, recording success/failure."""
        try:
            result = await coro
            # Clear any accumulated failures on success (partial recovery)
            if self._failure_times:
                self._prune_old_failures()
            return result
        except Exception as exc:
            opened = self.record_failure()
            logger.warning(
                "CircuitBreaker[%s]: failure recorded (%s) — %s failures in window%s",
                self.agent_name,
                type(exc).__name__,
                len(self._failure_times),
                " — circuit now OPEN" if opened else "",
            )
            raise

    async def _probe(
        self,
        coro: Coroutine[Any, Any, T],
        fallback: T | None,
    ) -> T | None:
        """
        Half-open probe: allow one request through to test recovery.

        Uses a lock so concurrent requests during HALF_OPEN all get the
        fallback except the one holding the lock (the probe).
        """
        if self._probe_lock.locked():
            # Another coroutine is already probing — short-circuit this one
            logger.debug(
                "CircuitBreaker[%s]: probe in progress — short-circuiting",
                self.agent_name,
            )
            coro.close()
            return fallback

        async with self._probe_lock:
            # Re-check state in case a previous probe already closed/opened
            if self._state != CircuitState.HALF_OPEN:
                if self._state == CircuitState.CLOSED:
                    return await self._run(coro, fallback)
                coro.close()
                return fallback

            logger.info(
                "CircuitBreaker[%s]: sending HALF_OPEN probe",
                self.agent_name,
            )
            try:
                result = await coro
                self.record_success()
                return result
            except Exception as exc:
                # Probe failed — back to OPEN
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._failure_times.append(self._opened_at)
                logger.error(
                    "CircuitBreaker[%s]: probe failed (%s) — circuit re-OPENED",
                    self.agent_name,
                    type(exc).__name__,
                )
                raise
