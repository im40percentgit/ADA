# Phase 10 Design Spec — Push Notifications

## Problem

Ada's caregivers only see updates when they open the app and poll. Crisis alerts, Ada board suggestions, and daily summaries sit unseen until the caregiver checks. The shared boards feature (Phase 9b) is especially limited without push — board changes only sync when both users have the app open.

## Solution

Web Push notifications via Service Worker + VAPID. A central NotificationDispatcher infrastructure subscriber listens to EventBus events, resolves affected care circle members, filters by role, and sends push notifications to all subscribed devices.

## Data Model

```sql
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    endpoint    TEXT NOT NULL UNIQUE,
    p256dh_key  TEXT NOT NULL,
    auth_key    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    event_type  TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    sent_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Indices: idx_push_subs_user, idx_notification_log_user.

## NotificationDispatcher

Infrastructure subscriber (like DailySummaryGenerator, BoardSuggestionAgent).

**Subscribed events:**
| Event | Notification | Roles |
|-------|-------------|-------|
| CRISIS_DETECTED | "Crisis Alert: {severity}" | primary_caregiver, family, clinician |
| BOARD_ITEM_SUGGESTED | "Ada suggested: {text}" | primary_caregiver, family |
| BOARD_ITEM_ADDED | "New item on {board}: {text}" | primary_caregiver, family |
| BOARD_ITEM_CHECKED | "{user} checked: {text}" | primary_caregiver, family |
| DAILY_SUMMARY_GENERATED | "Daily summary ready for {patient}" | primary_caregiver, family, clinician |
| CIRCLE_MEMBER_ADDED | "{email} joined care team" | primary_caregiver |

**Flow:**
1. Event arrives → extract patient_id
2. Get care circle for patient → get circle members
3. Filter members by role (see table above)
4. For each eligible member: get their push_subscriptions
5. Send Web Push to each device via pywebpush
6. Log to notification_log
7. On delivery failure (410 Gone): delete stale subscription

**No deduplication or throttling in Phase 10.** Board item events (add/check) may produce multiple notifications per day — acceptable for now.

## API

- `POST /api/notifications/subscribe` — register PushSubscription JSON from browser
- `DELETE /api/notifications/subscribe` — unregister by endpoint
- `GET /api/notifications/vapid-key` — return public VAPID key for frontend subscription

## Frontend

**Service Worker (`web/public/sw.js`):**
- `push` event handler: show browser notification from payload
- `notificationclick` event: open/focus the app

**`useNotifications` hook:**
- Check `Notification.permission`
- Request permission
- Subscribe to push via `PushManager.subscribe()` with VAPID applicationServerKey
- POST subscription to backend
- Provide `subscribed` state for UI

**CaregiverDashboard integration:**
- Notification bell/prompt in header when permission not yet granted
- Once subscribed, no further UI needed (notifications come via browser)

## Config

```python
class NotificationConfig(BaseModel):
    enabled: bool = True
    vapid_private_key_env: str = "ADA_VAPID_PRIVATE_KEY"
    vapid_public_key_env: str = "ADA_VAPID_PUBLIC_KEY"
    vapid_email: str = "mailto:admin@ada.local"
```

VAPID keys generated once with: `python -c "from pywebpush import webpush; from py_vapid import Vapid; v = Vapid(); v.generate_keys(); print(v.private_pem()); print(v.public_key)"`

## Dependencies

- `pywebpush` (Python Web Push library, ~50KB)
- No external services — VAPID is self-hosted
