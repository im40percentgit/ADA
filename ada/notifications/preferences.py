"""
Notification preference gating, per-user throttling, and deduplication.

NotificationPreferenceManager is used by NotificationDispatcher to determine
whether a notification should be sent to a specific user for a specific event.

Decision logic (evaluated in order):
  1. Preference check — if user has disabled this event type, suppress.
  2. Dedup check     — if exact same dedup_key was sent within dedup_window, suppress.
  3. Throttle check  — if any notification of this event_type was sent within
                       throttle_window, suppress.  EXCEPTION: crisis.detected
                       bypasses throttle (but not preferences per spec).

Crisis bypass rationale: a second crisis event may arrive seconds after the
first during a rapid escalation. Throttling it would delay a potentially
life-saving alert. The user must explicitly disable crisis_detected in their
preferences to silence it.

@decision DEC-NOTIF-007
@title NotificationPreferenceManager as standalone module separate from dispatcher
@status accepted
@rationale Separating preference/throttle/dedup logic from the dispatch loop
    keeps NotificationDispatcher focused on fan-out routing and makes the
    gating logic independently testable. The manager is instantiated once at
    startup and passed to the dispatcher via constructor injection, following
    the same pattern as StateManager throughout the codebase.

@decision DEC-NOTIF-008
@title Crisis bypasses throttle but not preferences
@status accepted
@rationale Crisis notifications are safety-critical — throttling them during a
    rapid escalation could delay a life-saving alert. However, respecting
    explicit preference opt-out is paramount: if a user has disabled crisis
    notifications (e.g., a family member who finds them distressing), that
    decision must be honoured. The asymmetry (bypass throttle, respect prefs)
    gives caregivers control without compromising safety for those who want
    the full alert stream.
"""

from __future__ import annotations

import time
from typing import Any

from ada.core.config import NotificationThrottleConfig
from ada.core.state import StateManager

# Event type string → preference key mapping.
# Preference keys are snake_case versions of the event type with dots replaced.
_EVENT_TO_PREF_KEY: dict[str, str] = {
    "crisis.detected": "crisis_detected",
    "board.item.suggested": "board_item_suggested",
    "board.item.added": "board_item_added",
    "board.item.checked": "board_item_checked",
    "daily.summary.generated": "daily_summary_generated",
    "circle.member.added": "circle_member_added",
}

# Default preferences — all enabled.
_DEFAULT_PREFERENCES: dict[str, bool] = {
    "crisis_detected": True,
    "board_item_suggested": True,
    "board_item_added": True,
    "board_item_checked": True,
    "daily_summary_generated": True,
    "circle_member_added": True,
}

# Event types that bypass the throttle window (but NOT preferences).
_THROTTLE_BYPASS_EVENT_TYPES: frozenset[str] = frozenset({"crisis.detected"})


class NotificationPreferenceManager:
    """Gate notification dispatch based on user preferences, throttle, and dedup.

    Usage:
        allowed = await mgr.should_send(user_id, event_type, dedup_key)
        if allowed:
            # send the push
            await mgr.record_sent(user_id, event_type, dedup_key)
    """

    def __init__(
        self,
        state: StateManager,
        config: NotificationThrottleConfig,
    ) -> None:
        self._state = state
        self._config = config

    async def get_preferences(self, user_id: str) -> dict[str, bool]:
        """Return the user's notification preferences, merging with defaults.

        Unknown keys in stored preferences are ignored. Missing keys fall back
        to the default (enabled). This ensures forward compatibility when new
        event types are added without requiring a migration.
        """
        stored = await self._state.get_notification_preferences(user_id)
        if stored is None:
            return dict(_DEFAULT_PREFERENCES)
        # Merge stored over defaults so new event types are enabled by default
        merged = dict(_DEFAULT_PREFERENCES)
        for k, v in stored.items():
            if k in merged:
                merged[k] = bool(v)
        return merged

    async def set_preferences(
        self,
        user_id: str,
        prefs: dict[str, Any],
    ) -> None:
        """Persist notification preferences for a user.

        Only recognised preference keys are stored — unknown keys are silently
        dropped. This prevents schema drift from arbitrary client input.
        """
        clean = {k: bool(v) for k, v in prefs.items() if k in _DEFAULT_PREFERENCES}
        await self._state.set_notification_preferences(user_id, clean)

    async def should_send(
        self,
        user_id: str,
        event_type: str,
        dedup_key: str,
    ) -> bool:
        """Return True if the notification should be dispatched.

        Evaluation order:
          1. Preference check (always applied, including crisis)
          2. Dedup check (always applied)
          3. Throttle check (bypassed for crisis.detected)
        """
        # 1. Preference check
        pref_key = _EVENT_TO_PREF_KEY.get(event_type)
        if pref_key is not None:
            prefs = await self.get_preferences(user_id)
            if not prefs.get(pref_key, True):
                return False

        now = time.time()

        # 2. Dedup check — suppress exact same dedup_key within dedup window
        if self._config.dedup_window_seconds > 0:
            last_dedup = await self._state.get_dedup_key_last_sent(
                user_id, event_type, dedup_key
            )
            if last_dedup is not None:
                age = now - last_dedup
                if age < self._config.dedup_window_seconds:
                    return False

        # 3. Throttle check — crisis bypasses; all others respect window
        if event_type not in _THROTTLE_BYPASS_EVENT_TYPES:
            if self._config.throttle_window_seconds > 0:
                last_sent = await self._state.get_last_notification_sent(
                    user_id, event_type
                )
                if last_sent is not None:
                    age = now - last_sent
                    if age < self._config.throttle_window_seconds:
                        return False

        return True

    async def record_sent(
        self,
        user_id: str,
        event_type: str,
        dedup_key: str,
    ) -> None:
        """Record that a notification was dispatched for this user/event/dedup_key.

        Must be called after a successful push delivery so subsequent calls to
        should_send() have an accurate last-sent timestamp.
        """
        await self._state.record_notification_sent(
            user_id, event_type, dedup_key, time.time()
        )
