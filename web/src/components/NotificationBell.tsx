/**
 * NotificationBell — push notification opt-in control with inline preferences.
 *
 * Renders nothing when the browser does not support the Notifications API.
 * Shows a prompt button when permission is default, a blocked indicator when
 * denied, and when permission is granted: a toggle button plus an inline
 * preferences panel (Phase 11b) with per-event-type on/off switches.
 *
 * The preferences panel renders inline in the dropdown (not a separate route)
 * so users can adjust settings without leaving the current page.
 *
 * Delegates all Web Push logic and preference state to useNotifications so
 * this component stays focused on presentation.
 *
 * @decision DEC-NOTIF-002
 * @title NotificationBell renders three states driven by Notification.permission
 * @status accepted
 * @rationale The Web Notifications API has three distinct permission states
 *   (default, granted, denied) plus an unsupported case. Mapping each to a
 *   distinct render branch keeps the component self-contained and avoids
 *   callers needing to reason about permission state. The unsupported path
 *   returns null so progressive enhancement works automatically — browsers
 *   without push support show nothing rather than a broken control.
 *
 * @decision DEC-NOTIF-013
 * @title Preferences as inline section in NotificationBell dropdown
 * @status accepted
 * @rationale Keeps notification settings co-located with the toggle that
 *   controls them. No routing required. Inline panel is simple enough (~6
 *   checkboxes) that a separate settings page would add navigation overhead
 *   without UX benefit. The panel only renders when permission is granted
 *   and the user is subscribed — hiding it otherwise reduces visual noise.
 */

import { useState } from 'react'
import { useNotifications } from '../hooks/useNotifications'
import type { NotificationPreferences } from '../types'

// Human-readable labels for each preference key
const PREF_LABELS: Record<keyof NotificationPreferences, string> = {
  crisis_detected: 'Crisis alerts',
  board_item_suggested: 'Ada suggestions',
  board_item_added: 'Board items added',
  board_item_checked: 'Board items checked',
  daily_summary_generated: 'Daily summary',
  circle_member_added: 'Care team changes',
}

export function NotificationBell() {
  const {
    permission,
    subscribed,
    loading,
    preferences,
    prefsLoading,
    requestPermission,
    subscribe,
    unsubscribe,
    updatePreferences,
  } = useNotifications()

  const [prefsOpen, setPrefsOpen] = useState(false)

  if (permission === 'unsupported') return null

  if (permission === 'default') {
    return (
      <button
        className="notification-bell notification-bell--prompt"
        onClick={async () => {
          await requestPermission()
          await subscribe()
        }}
        title="Enable notifications"
        type="button"
      >
        Enable Notifications
      </button>
    )
  }

  if (permission === 'denied') {
    return (
      <span
        className="notification-bell notification-bell--denied"
        title="Notifications blocked in browser settings"
      >
        Notifications Blocked
      </span>
    )
  }

  // permission === 'granted'
  const handlePrefChange = async (key: keyof NotificationPreferences, value: boolean) => {
    await updatePreferences({ [key]: value })
  }

  return (
    <div className="notification-bell notification-bell--granted">
      <button
        className="notification-bell__toggle"
        onClick={subscribed ? unsubscribe : subscribe}
        disabled={loading}
        title={subscribed ? 'Disable notifications' : 'Enable notifications'}
        type="button"
      >
        {loading ? '...' : subscribed ? 'Notifications On' : 'Notifications Off'}
      </button>

      {subscribed && (
        <button
          className="notification-bell__prefs-toggle"
          onClick={() => setPrefsOpen((o) => !o)}
          type="button"
          aria-expanded={prefsOpen}
          title={prefsOpen ? 'Hide notification preferences' : 'Show notification preferences'}
        >
          {prefsOpen ? 'Hide preferences' : 'Preferences'}
        </button>
      )}

      {subscribed && prefsOpen && (
        <div
          className="notification-bell__prefs-panel"
          role="group"
          aria-label="Notification type preferences"
        >
          <p className="notification-bell__prefs-heading">Notify me about:</p>
          {prefsLoading && (
            <p className="notification-bell__prefs-loading">Loading preferences...</p>
          )}
          {!prefsLoading &&
            (Object.keys(PREF_LABELS) as (keyof NotificationPreferences)[]).map((key) => (
              <label key={key} className="notification-bell__pref-row">
                <input
                  type="checkbox"
                  checked={preferences[key]}
                  onChange={(e) => handlePrefChange(key, e.target.checked)}
                  aria-label={PREF_LABELS[key]}
                />
                <span>{PREF_LABELS[key]}</span>
              </label>
            ))}
        </div>
      )}
    </div>
  )
}
