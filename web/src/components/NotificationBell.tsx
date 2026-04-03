/**
 * NotificationBell — UI control for push notification opt-in/out.
 *
 * Renders nothing when the browser does not support the Notifications API.
 * Shows a prompt button when permission is default, a blocked indicator when
 * denied, and a toggle button (On/Off) when permission is granted.
 *
 * Delegates all Web Push logic to useNotifications so this component stays
 * purely presentational with respect to the subscription lifecycle.
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
 */

import { useNotifications } from '../hooks/useNotifications'

export function NotificationBell() {
  const { permission, subscribed, loading, requestPermission, subscribe, unsubscribe } =
    useNotifications()

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
  return (
    <button
      className="notification-bell notification-bell--active"
      onClick={subscribed ? unsubscribe : subscribe}
      disabled={loading}
      title={subscribed ? 'Disable notifications' : 'Enable notifications'}
      type="button"
    >
      {loading ? '...' : subscribed ? 'Notifications On' : 'Notifications Off'}
    </button>
  )
}
