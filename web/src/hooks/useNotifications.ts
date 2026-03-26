/**
 * useNotifications — React hook for Web Push subscription lifecycle.
 *
 * Manages the full push notification flow: permission request, service worker
 * registration, VAPID subscription creation, and backend sync. Exposes a
 * simple { permission, subscribed, loading, requestPermission, subscribe,
 * unsubscribe } interface so UI components stay free of Web Push plumbing.
 *
 * Token retrieval uses the canonical ADA_ACCESS_TOKEN key from auth.ts rather
 * than a hard-coded string, so the auth token lookup stays consistent.
 *
 * @decision DEC-NOTIF-001
 * @title useNotifications abstracts all Web Push API surface behind a hook
 * @status accepted
 * @rationale Keeping Push API details (VAPID key fetch, PushManager,
 *   Uint8Array conversion) inside a single hook means UI components only
 *   depend on a stable interface. This makes it easy to swap the SW
 *   registration strategy or backend endpoint without touching any component.
 */

import { useCallback, useEffect, useState } from 'react'
import { TOKEN_KEY } from '../api/auth'

interface UseNotificationsResult {
  permission: NotificationPermission | 'unsupported'
  subscribed: boolean
  loading: boolean
  requestPermission: () => Promise<void>
  subscribe: () => Promise<void>
  unsubscribe: () => Promise<void>
}

export function useNotifications(): UseNotificationsResult {
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>(
    typeof Notification !== 'undefined' ? Notification.permission : 'unsupported'
  )
  const [subscribed, setSubscribed] = useState(false)
  const [loading, setLoading] = useState(false)

  // Check if already subscribed on mount
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready
        .then(async (reg) => {
          const sub = await reg.pushManager.getSubscription()
          setSubscribed(!!sub)
        })
        .catch(() => {})
    }
  }, [])

  const requestPermission = useCallback(async () => {
    if (typeof Notification === 'undefined') return
    const result = await Notification.requestPermission()
    setPermission(result)
  }, [])

  const subscribe = useCallback(async () => {
    if (!('serviceWorker' in navigator)) return
    setLoading(true)
    try {
      // Get VAPID public key from backend
      const resp = await fetch('/api/notifications/vapid-key')
      const { public_key } = await resp.json()
      if (!public_key) {
        console.warn('No VAPID public key configured')
        return
      }

      // Register service worker if not already
      const reg = await navigator.serviceWorker.register('/sw.js')
      await navigator.serviceWorker.ready

      // Subscribe to push
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      })

      // Send subscription to backend
      const token = localStorage.getItem(TOKEN_KEY)
      await fetch('/api/notifications/subscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(sub.toJSON()),
      })

      setSubscribed(true)
    } catch (err) {
      console.error('Failed to subscribe to push:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  const unsubscribe = useCallback(async () => {
    if (!('serviceWorker' in navigator)) return
    setLoading(true)
    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (sub) {
        const endpoint = sub.endpoint
        await sub.unsubscribe()

        const token = localStorage.getItem(TOKEN_KEY)
        await fetch('/api/notifications/subscribe', {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ endpoint }),
        })
      }
      setSubscribed(false)
    } catch (err) {
      console.error('Failed to unsubscribe:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  return { permission, subscribed, loading, requestPermission, subscribe, unsubscribe }
}

// ---------------------------------------------------------------------------
// Helper: convert VAPID base64url key to Uint8Array for PushManager
// ---------------------------------------------------------------------------

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const arr = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i)
  return arr
}
