"""
Central push notification dispatcher.

Subscribes to high-value EventBus events and sends Web Push notifications
to care circle members based on their circle role.

Role-based notification matrix:
| Event                    | primary_caregiver | family | clinician |
|--------------------------|:-----------------:|:------:|:---------:|
| CRISIS_DETECTED          |         Y         |   Y    |     Y     |
| BOARD_ITEM_SUGGESTED     |         Y         |   Y    |     N     |
| BOARD_ITEM_ADDED         |         Y         |   Y    |     N     |
| BOARD_ITEM_CHECKED       |         Y         |   Y    |     N     |
| DAILY_SUMMARY_GENERATED  |         Y         |   Y    |     Y     |
| CIRCLE_MEMBER_ADDED      |         Y         |   N    |     N     |

@decision DEC-NOTIF-002
@title NotificationDispatcher as infrastructure subscriber (not BaseAgent)
@status accepted
@rationale Push dispatching is an infrastructure concern triggered by domain
    events, not a therapy agent. Follows DailySummaryGenerator pattern
    (DEC-DAILY-001). Not registered in AgentRegistry — instantiated directly
    in main.py and wired to EventBus.

@decision DEC-NOTIF-003
@title Role-based notification matrix (primary_caregiver > family > clinician)
@status accepted
@rationale Different stakeholders need different event subsets. Primary
    caregivers receive everything. Clinicians receive only clinical events
    (crisis, daily summary). Family receive all care coordination except
    team membership changes.

@decision DEC-NOTIF-005
@title 410 Gone auto-deletes subscription
@status accepted
@rationale W3C Push API spec: browsers return 410 when a subscription expires
    or is revoked. Auto-deleting on 410 keeps the subscription table clean
    without requiring explicit client-side unsubscribe.

@decision DEC-NOTIF-006
@title asyncio.to_thread() for pywebpush calls
@status accepted
@rationale pywebpush.webpush() is synchronous and makes an HTTP request.
    Running it in a thread pool via asyncio.to_thread() keeps the EventBus
    handler non-blocking.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from ada.core.bus import EventBus
from ada.core.config import NotificationConfig
from ada.core.events import (
    AdaEvent,
    BoardItemAddedEvent,
    BoardItemCheckedEvent,
    BoardItemSuggestedEvent,
    CircleMemberAddedEvent,
    CrisisDetectedEvent,
    DailySummaryGeneratedEvent,
    EventTypes,
)
from ada.core.state import StateManager
from ada.notifications.preferences import NotificationPreferenceManager

logger = logging.getLogger(__name__)

try:
    from pywebpush import webpush  # type: ignore[import]
except ImportError:  # pragma: no cover
    webpush = None  # type: ignore[assignment]

# Role → set of event types the role receives notifications for
_ROLE_EVENTS: dict[str, set[str]] = {
    "primary_caregiver": {
        EventTypes.CRISIS_DETECTED,
        EventTypes.BOARD_ITEM_SUGGESTED,
        EventTypes.BOARD_ITEM_ADDED,
        EventTypes.BOARD_ITEM_CHECKED,
        EventTypes.DAILY_SUMMARY_GENERATED,
        EventTypes.CIRCLE_MEMBER_ADDED,
    },
    "family": {
        EventTypes.CRISIS_DETECTED,
        EventTypes.BOARD_ITEM_SUGGESTED,
        EventTypes.BOARD_ITEM_ADDED,
        EventTypes.BOARD_ITEM_CHECKED,
        EventTypes.DAILY_SUMMARY_GENERATED,
    },
    "clinician": {
        EventTypes.CRISIS_DETECTED,
        EventTypes.DAILY_SUMMARY_GENERATED,
    },
}

_SUBSCRIBED_EVENTS = [
    EventTypes.CRISIS_DETECTED,
    EventTypes.BOARD_ITEM_SUGGESTED,
    EventTypes.BOARD_ITEM_ADDED,
    EventTypes.BOARD_ITEM_CHECKED,
    EventTypes.DAILY_SUMMARY_GENERATED,
    EventTypes.CIRCLE_MEMBER_ADDED,
]


class NotificationDispatcher:
    """Infrastructure subscriber that fans out push notifications to care circles.

    Instantiated once at startup. For each subscribed event, it:
    1. Extracts the patient_id to identify the relevant care circle.
    2. Loads circle members and filters by role-event matrix.
    3. Sends a Web Push to each qualifying member's registered devices.
    4. Logs the notification for audit.
    """

    def __init__(
        self,
        bus: EventBus,
        state: StateManager,
        config: NotificationConfig,
    ) -> None:
        self._bus = bus
        self._state = state
        self._config = config
        self._pref_mgr = NotificationPreferenceManager(state, config.throttle)

        # Read VAPID keys from env at construction time
        self._vapid_private_key = os.environ.get(config.vapid_private_key_env, "")
        self._vapid_public_key = os.environ.get(config.vapid_public_key_env, "")

        for event_type in _SUBSCRIBED_EVENTS:
            bus.subscribe(event_type, self._on_event, f"notification_{event_type}")

        logger.info(
            "NotificationDispatcher: subscribed to %d event types",
            len(_SUBSCRIBED_EVENTS),
        )

    async def _on_event(self, event: AdaEvent) -> None:
        """Route an incoming event to the appropriate care circle members."""
        try:
            patient_id = self._extract_patient_id(event)
            if not patient_id:
                logger.debug(
                    "NotificationDispatcher: no patient_id for %s, skipping",
                    event.event_type,
                )
                return

            title, body = self._format_notification(event)
            # Stable dedup key: event type + patient + event id (if present)
            dedup_key = f"{event.event_type}:{patient_id}:{getattr(event, 'id', '')}"

            circle = await self._state.get_care_circle_by_patient(patient_id)
            if not circle:
                return

            members = await self._state.get_circle_members(circle["id"])

            for member in members:
                role = member.get("role", "")
                allowed = _ROLE_EVENTS.get(role, set())
                if event.event_type not in allowed:
                    continue

                user_id = member["user_id"]

                # Preference + throttle + dedup gate
                if not await self._pref_mgr.should_send(user_id, event.event_type, dedup_key):
                    logger.debug(
                        "NotificationDispatcher: suppressed %s for user %s (pref/throttle/dedup)",
                        event.event_type,
                        user_id,
                    )
                    continue

                subs = await self._state.get_push_subscriptions(user_id)
                for sub in subs:
                    await self._send_push(sub, title, body, event.event_type, user_id, dedup_key)

        except Exception:
            logger.exception(
                "NotificationDispatcher: unhandled error processing %s",
                event.event_type,
            )

    def _extract_patient_id(self, event: AdaEvent) -> str | None:
        """Return patient_id from an event, or None if unavailable."""
        patient_id = getattr(event, "patient_id", None)
        if patient_id:
            return patient_id
        return None

    def _format_notification(self, event: AdaEvent) -> tuple[str, str]:
        """Generate (title, body) for a Web Push notification payload."""
        if isinstance(event, CrisisDetectedEvent):
            return "Crisis Alert", f"Severity: {event.severity}"
        if isinstance(event, BoardItemSuggestedEvent):
            return "Ada Suggestion", f"Ada suggested: {event.text}"
        if isinstance(event, BoardItemAddedEvent):
            return "New Board Item", event.text
        if isinstance(event, BoardItemCheckedEvent):
            status = "completed" if event.checked else "unchecked"
            return "Board Update", f"Item {status}"
        if isinstance(event, DailySummaryGeneratedEvent):
            return "Daily Summary Ready", "Your daily wellness summary is available"
        if isinstance(event, CircleMemberAddedEvent):
            return "Care Team Update", "A new member joined the care team"
        return "Ada", "New update available"

    async def _send_push(
        self,
        sub: dict[str, Any],
        title: str,
        body: str,
        event_type: str,
        user_id: str,
        dedup_key: str,
    ) -> None:
        """Deliver a single Web Push notification, log it, and record for throttle/dedup.

        If the VAPID private key is not configured, push is skipped silently
        (safe for development and testing environments). The audit log and
        throttle record are always written so the gating logic stays accurate.
        """
        if not self._vapid_private_key:
            logger.debug(
                "NotificationDispatcher: VAPID key not configured, skipping push"
            )
            # Still log so audit trail shows the notification would have been sent
            await self._log_notification(user_id, event_type, title, body)
            await self._pref_mgr.record_sent(user_id, event_type, dedup_key)
            return

        payload = json.dumps({"title": title, "body": body, "url": "/"})
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {
                "p256dh": sub["p256dh_key"],
                "auth": sub["auth_key"],
            },
        }

        push_succeeded = False
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=self._vapid_private_key,
                vapid_claims={"sub": self._config.vapid_email},
            )
            push_succeeded = True
        except Exception as exc:
            # 410 Gone = subscription expired — clean it up automatically
            status_code = getattr(getattr(exc, "response", None), "status_code", 0)
            if status_code == 410:
                await self._state.delete_push_subscription(sub["endpoint"])
                logger.info(
                    "NotificationDispatcher: removed expired subscription %.50s",
                    sub["endpoint"],
                )
            else:
                logger.warning(
                    "NotificationDispatcher: push failed for %.50s: %s",
                    sub["endpoint"],
                    exc,
                )

        await self._log_notification(user_id, event_type, title, body)
        # Record for throttle/dedup regardless of delivery success — a failed
        # push still counts as "attempted" to prevent retry floods.
        await self._pref_mgr.record_sent(user_id, event_type, dedup_key)

    async def _log_notification(
        self,
        user_id: str,
        event_type: str,
        title: str,
        body: str,
    ) -> None:
        """Persist a notification_log record for audit."""
        await self._state.create_notification_log({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "event_type": event_type,
            "title": title,
            "body": body,
        })

    async def shutdown(self) -> None:
        """No-op shutdown hook for symmetry with other infrastructure subscribers."""
        logger.info("NotificationDispatcher: shutdown")
