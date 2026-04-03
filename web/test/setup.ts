/**
 * test/setup.ts — Global test setup for Ada frontend tests.
 *
 * Executed before every test file via vitest.config.ts setupFiles.
 *
 * Responsibilities:
 *   1. RTL cleanup — unmount components after each test
 *   2. MSW server — start/reset/stop HTTP mock server
 *   3. WebSocket mock — jsdom has no WebSocket; provide a controllable stub
 *   4. Browser API mocks — Notification, serviceWorker, matchMedia
 *   5. localStorage — real jsdom localStorage (cleared per test)
 *
 * @decision DEC-TEST-010
 * @title MSW at network layer, WebSocket stubbed at global scope
 * @status accepted
 * @rationale MSW intercepts fetch() at the service worker / fetch handler
 *   layer, so all REST calls go through real api/client.ts code. WebSocket
 *   cannot be intercepted by MSW in jsdom, so we provide a minimal global
 *   stub that tracks the last constructed instance and lets tests inject
 *   messages. This keeps Chat and BoardView tests deterministic without
 *   mocking the hook layer.
 */

import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './msw/handlers'

// ---------------------------------------------------------------------------
// RTL cleanup
// ---------------------------------------------------------------------------

afterEach(() => {
  cleanup()
  localStorage.clear()
})

// ---------------------------------------------------------------------------
// MSW server lifecycle
// ---------------------------------------------------------------------------

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// ---------------------------------------------------------------------------
// WebSocket mock
// ---------------------------------------------------------------------------
// jsdom does not implement WebSocket. We provide a minimal controllable stub
// so components that call `new WebSocket(url)` don't throw. Tests can use
// MockWebSocket.lastInstance to trigger onopen/onmessage/onclose events.

export class MockWebSocket {
  // WebSocket readyState constants — required so hooks that reference
  // WebSocket.CONNECTING / WebSocket.OPEN / etc. get real numeric values
  // rather than undefined, which would break guard conditions like
  // `wsRef.current?.readyState === WebSocket.OPEN`.
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  static lastInstance: MockWebSocket | null = null

  url: string
  protocol: string = ''
  extensions: string = ''
  binaryType: BinaryType = 'blob'
  bufferedAmount: number = 0
  readyState: number = 0 // CONNECTING
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null

  sentMessages: unknown[] = []

  // EventTarget-like API — MSW's @mswjs/interceptors calls addEventListener
  // when it wraps a WebSocket instance. We store listeners so event dispatch
  // works through both the property callbacks (onopen, etc.) and the listener
  // list, keeping hook code and MSW interceptor compatible simultaneously.
  private _listeners: Map<string, Set<EventListenerOrEventListenerObject>> = new Map()

  constructor(url: string) {
    this.url = url
    MockWebSocket.lastInstance = this
    // Auto-open on next tick so components using useEffect(onOpen) work
    setTimeout(() => {
      this.readyState = 1 // OPEN
      const ev = new Event('open')
      this.onopen?.(ev)
      this._dispatchToListeners('open', ev)
    }, 0)
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    if (!this._listeners.has(type)) this._listeners.set(type, new Set())
    this._listeners.get(type)!.add(listener)
  }

  removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this._listeners.get(type)?.delete(listener)
  }

  dispatchEvent(event: Event): boolean {
    this._dispatchToListeners(event.type, event)
    return true
  }

  private _dispatchToListeners(type: string, event: Event) {
    const listeners = this._listeners.get(type)
    if (!listeners) return
    for (const listener of listeners) {
      if (typeof listener === 'function') listener(event)
      else listener.handleEvent(event)
    }
  }

  send(data: string) {
    try {
      this.sentMessages.push(JSON.parse(data))
    } catch {
      this.sentMessages.push(data)
    }
  }

  close() {
    this.readyState = 3 // CLOSED
    const ev = new CloseEvent('close')
    this.onclose?.(ev)
    this._dispatchToListeners('close', ev)
  }

  /** Helper: inject a message event into the component */
  simulateMessage(data: unknown) {
    const ev = new MessageEvent('message', { data: JSON.stringify(data) })
    this.onmessage?.(ev)
    this._dispatchToListeners('message', ev)
  }
}

// Install globally — replaces any undefined WebSocket in jsdom
;(globalThis as unknown as Record<string, unknown>).WebSocket = MockWebSocket

// ---------------------------------------------------------------------------
// Notification API mock
// ---------------------------------------------------------------------------

if (typeof globalThis.Notification === 'undefined') {
  Object.defineProperty(globalThis, 'Notification', {
    value: {
      permission: 'default' as NotificationPermission,
      requestPermission: async () => 'granted' as NotificationPermission,
    },
    writable: true,
    configurable: true,
  })
}

// ---------------------------------------------------------------------------
// navigator.serviceWorker mock
// ---------------------------------------------------------------------------

Object.defineProperty(globalThis.navigator, 'serviceWorker', {
  value: {
    ready: Promise.resolve({
      pushManager: {
        getSubscription: async () => null,
        subscribe: async () => ({ toJSON: () => ({}) }),
      },
      register: async () => undefined,
    }),
    register: async () => ({
      pushManager: {
        getSubscription: async () => null,
        subscribe: async () => ({ toJSON: () => ({}) }),
      },
    }),
  },
  writable: true,
  configurable: true,
})

// ---------------------------------------------------------------------------
// scrollIntoView mock — jsdom does not implement it
// ---------------------------------------------------------------------------

window.HTMLElement.prototype.scrollIntoView = function () {}

// ---------------------------------------------------------------------------
// window.matchMedia mock
// ---------------------------------------------------------------------------

Object.defineProperty(globalThis, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})
