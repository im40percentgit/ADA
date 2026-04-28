"""
Nightly verdict cron — Phase 15+ M3.

Runs a background asyncio loop that fires once per day at config.verdict.cron_hour:
cron_minute in config.verdict.cron_timezone. On each firing it calls
generate_verdict_for_date() for every patient that has had at least one game
session in the past 24 hours.

This module is stateless between firings: next-firing time is computed fresh
from `datetime.now(tz)` on each wakeup, so process restarts are harmless.

Instantiated in main.py after the StateManager and LLM router are ready;
shut down via VerdictCron.stop() in the lifespan finally block.

@decision DEC-VERDICT-008
@title Nightly cron via plain asyncio loop, not apscheduler
@status accepted
@rationale Zero new deps; matches DailySummaryGenerator / BoardSuggestionAgent
    pattern; restart-safe by recomputing next firing from current time.
    apscheduler would add ~300 kB of dependency weight and a new abstraction
    layer (job stores, schedulers, triggers) for a single daily job. The plain
    asyncio pattern is already established in this codebase and is trivially
    testable via the injected-now parameter.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from ada.core.config import AdaConfig
    from ada.core.state import StateManager

logger = logging.getLogger(__name__)


class VerdictCron:
    """
    Background asyncio loop that triggers nightly verdict generation.

    The loop sleeps until config.verdict.cron_hour:cron_minute in
    config.verdict.cron_timezone, then calls generate_verdict_for_date()
    for each patient with recent game activity.

    Args:
        config:    AdaConfig instance — reads config.verdict.*
        state:     Initialised StateManager — used to list patients and check
                   game session recency.
        generator: The generate_verdict_for_date coroutine function imported
                   from ada.verdict.generator. Passed as a parameter so tests
                   can substitute a fake without monkeypatching module globals.
        llm:       LLM provider forwarded to the generator.

    @decision DEC-VERDICT-010
    @title Deploy-wide patient timezone via config.verdict.cron_timezone
        rather than per-patient TZ on Patient.preferences
    @status accepted
    @rationale N=1 deploy — the patient lives in the deploy's TZ. Per-patient
        TZ is deferred to post-N=1; when added, resolve TZ as:
        patient.preferences.get("timezone") or config.verdict.cron_timezone.
    """

    def __init__(
        self,
        *,
        config: AdaConfig,
        state: StateManager,
        generator,  # callable: (state, llm, patient_id, date) -> Awaitable[DailyVerdict]
        llm,
    ) -> None:
        self._config = config
        self._state = state
        self._generator = generator
        self._llm = llm

        # @decision DEC-VERDICT-010: timezone resolved from deploy-wide config
        self._tz = ZoneInfo(config.verdict.cron_timezone)
        self._hour = config.verdict.cron_hour
        self._minute = config.verdict.cron_minute

        self._task: asyncio.Task | None = None
        self._cancelled = False

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Schedule the background cron task.

        No-op if config.verdict.nightly_cron_enabled is False.
        """
        if not self._config.verdict.nightly_cron_enabled:
            logger.info(
                "VerdictCron: nightly_cron_enabled=False — skipping cron start"
            )
            return

        logger.info(
            "VerdictCron: starting — fires daily at %02d:%02d %s",
            self._hour,
            self._minute,
            self._config.verdict.cron_timezone,
        )
        self._cancelled = False
        self._task = asyncio.create_task(
            self._loop(), name="verdict_cron"
        )

    async def stop(self) -> None:
        """Cancel the background task and await its completion.

        Safe to call even if start() was never called or nightly_cron_enabled
        was False (task will be None).
        """
        self._cancelled = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("VerdictCron: stopped")

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Main background loop: sleep → fire → repeat."""
        logger.debug("VerdictCron: background loop started")
        while not self._cancelled:
            sleep_for = self._seconds_until_next_firing()
            logger.debug(
                "VerdictCron: next firing in %.0f s (%.2f h)",
                sleep_for,
                sleep_for / 3600,
            )
            await asyncio.sleep(sleep_for)
            if self._cancelled:
                break
            await self._run_once()

    # ------------------------------------------------------------------
    # Schedule resolver (pure function — injectable `now` for tests)
    # ------------------------------------------------------------------

    def _seconds_until_next_firing(self, *, now: datetime | None = None) -> float:
        """Compute seconds until the next HH:MM firing in self._tz.

        Pure function. Pass `now` from tests; defaults to datetime.now(self._tz).

        Returns a float >= 0.

        DST correctness: next_firing is constructed using ZoneInfo so that
        the resolved wall-clock time honours DST rules for the deploy timezone.
        If the target time doesn't exist (spring-forward gap), zoneinfo folds
        the time forward automatically. If it's ambiguous (fall-back fold),
        zoneinfo picks the first occurrence — both are acceptable for a daily
        cron.

        Logic:
          - If now < HH:MM today → next firing is today at HH:MM
          - If now >= HH:MM today → next firing is tomorrow at HH:MM
        """
        if now is None:
            now = datetime.now(self._tz)

        # Candidate: today at HH:MM in self._tz
        today_firing = now.replace(
            hour=self._hour,
            minute=self._minute,
            second=0,
            microsecond=0,
        )

        if now < today_firing:
            delta = today_firing - now
        else:
            # Already past today's firing — schedule for tomorrow
            tomorrow_firing = today_firing + timedelta(days=1)
            delta = tomorrow_firing - now

        return max(0.0, delta.total_seconds())

    # ------------------------------------------------------------------
    # Per-firing execution
    # ------------------------------------------------------------------

    async def _run_once(self) -> None:
        """For each patient with recent game sessions, generate verdict for today.

        Per-patient try/except — one patient's failure does NOT abort iteration.
        Logs each invocation with patient_id, date, result_state, duration_ms.
        """
        now = datetime.now(self._tz)
        today_str = now.date().isoformat()
        logger.info("VerdictCron: firing for date=%s", today_str)

        try:
            patients = await self._state.list_patients()
        except Exception as exc:
            logger.error("VerdictCron: failed to list patients: %s", exc)
            return

        for patient in patients:
            patient_id = patient["id"]
            t0 = asyncio.get_event_loop().time()
            try:
                has_sessions = await self._state.has_recent_game_sessions(
                    patient_id, since=timedelta(days=1)
                )
                if not has_sessions:
                    logger.debug(
                        "VerdictCron: patient %s has no recent sessions — skipping",
                        patient_id,
                    )
                    continue

                verdict = await self._generator(
                    self._state,
                    self._llm,
                    patient_id,
                    now.date(),
                )
                duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                logger.info(
                    "VerdictCron: patient=%s date=%s verdict=%s duration_ms=%d",
                    patient_id,
                    today_str,
                    verdict.verdict,
                    duration_ms,
                )
            except Exception as exc:
                duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                logger.error(
                    "VerdictCron: patient=%s date=%s error=%s duration_ms=%d",
                    patient_id,
                    today_str,
                    exc,
                    duration_ms,
                )
