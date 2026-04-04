// Service Worker for Ada — caching + push notifications
//
// @decision DEC-PWA-001
// @title Cache-first for static assets, network-first for API calls
// @status accepted
// @rationale Static assets (JS bundles, icons, manifest) are content-addressed
//   in production (Vite hash filenames) so cache-first is safe and fast.
//   API calls must be fresh — network-first with offline fallback prevents
//   stale clinical data being shown. WebSocket URLs are skipped entirely
//   since they cannot be cached and the fetch handler would interfere.

const CACHE_VERSION = 'ada-v1'
const STATIC_ASSETS = [
  '/manifest.json',
  '/icons/ada-192.png',
  '/icons/ada-512.png',
  '/offline.html',
]

// ---------------------------------------------------------------------------
// Install — pre-cache static assets and offline fallback
// ---------------------------------------------------------------------------

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => {
      return cache.addAll(STATIC_ASSETS)
    }).then(() => self.skipWaiting())
  )
})

// ---------------------------------------------------------------------------
// Activate — prune old cache versions
// ---------------------------------------------------------------------------

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_VERSION)
          .map((key) => caches.delete(key))
      )
    }).then(() => self.clients.claim())
  )
})

// ---------------------------------------------------------------------------
// Fetch — route requests to appropriate strategy
// ---------------------------------------------------------------------------

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)

  // Skip non-GET requests — POST/PUT/DELETE must always reach the network
  if (event.request.method !== 'GET') return

  // Skip WebSocket upgrade requests — cannot be cached
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return
  if (url.pathname.startsWith('/ws/')) return

  // API calls: network-first, fall back to cache on network failure
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Only cache successful responses
          if (response.ok) {
            const clone = response.clone()
            caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, clone))
          }
          return response
        })
        .catch(() =>
          caches.match(event.request).then(
            (cached) => cached ?? caches.match('/offline.html')
          )
        )
    )
    return
  }

  // Static assets (/assets/*, /icons/*, manifest.json): cache-first
  const isStatic =
    url.pathname.startsWith('/assets/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname === '/manifest.json'

  if (isStatic) {
    event.respondWith(
      caches.match(event.request).then(
        (cached) =>
          cached ??
          fetch(event.request).then((response) => {
            if (response.ok) {
              const clone = response.clone()
              caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, clone))
            }
            return response
          })
      )
    )
    return
  }

  // All other GET requests (HTML navigation): network-first, offline fallback
  event.respondWith(
    fetch(event.request).catch(() => caches.match('/offline.html'))
  )
})

// ---------------------------------------------------------------------------
// Push notifications (preserved from Phase 10)
// ---------------------------------------------------------------------------

self.addEventListener('push', (event) => {
  let data = { title: 'Ada', body: 'New update available', url: '/' }

  if (event.data) {
    try {
      data = { ...data, ...event.data.json() }
    } catch {
      data.body = event.data.text()
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/ada-192.png',
      badge: '/ada-192.png',
      data: { url: data.url || '/' },
      requireInteraction: data.title.includes('Crisis'),
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // Focus existing tab if open
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus()
        }
      }
      // Otherwise open new tab
      return clients.openWindow(url)
    })
  )
})
