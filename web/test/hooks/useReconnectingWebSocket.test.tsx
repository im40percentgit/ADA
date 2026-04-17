/**
 * useReconnectingWebSocket.test.tsx — regression tests for the superseded-socket
 * guards added in DEC-FRONTEND-019.
 *
 * The key scenario: React 18 StrictMode runs mount → cleanup → mount before
 * the first socket's async onopen fires. Without guards both sockets survive
 * and duplicate every message. These tests verify that:
 *   1. Only the second (live) socket's messages reach the onMessage callback.
 *   2. The first (superseded) socket is closed by its own onopen guard.
 *   3. A normal single-mount still works correctly.
 *
 * @decision DEC-FRONTEND-019 — see useReconnectingWebSocket.ts for full rationale.
 */

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useReconnectingWebSocket } from '../../src/hooks/useReconnectingWebSocket'
import type { WsInboundMessage } from '../../src/types'

// ---------------------------------------------------------------------------
// Controllable WebSocket stub for this test file.
//
// Unlike setup.ts MockWebSocket (which auto-opens on next tick), this stub
// fires events only when the test explicitly calls .triggerOpen() /
// .triggerMessage() / .triggerClose(). This gives us deterministic control
// over the async-open race that StrictMode exposes.
// ---------------------------------------------------------------------------

class ControlledWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  /** All instances created during a test, in creation order */
  static instances: ControlledWebSocket[] = []

  url: string
  binaryType: BinaryType = 'blob'
  readyState: number = ControlledWebSocket.CONNECTING

  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null

  closedCount = 0

  constructor(url: string) {
    this.url = url
    ControlledWebSocket.instances.push(this)
  }

  send(_data: string) {}

  close() {
    this.closedCount += 1
    this.readyState = ControlledWebSocket.CLOSED
  }

  /** Simulate the network completing the handshake */
  triggerOpen() {
    this.readyState = ControlledWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  /** Inject a JSON message */
  triggerMessage(data: WsInboundMessage) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  /** Simulate the server closing the connection */
  triggerClose() {
    this.readyState = ControlledWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }
}

// ---------------------------------------------------------------------------
// Install / restore the stub around each test.
//
// setup.ts installs MockWebSocket via Object.defineProperty({ writable: true })
// but after that first assignment the property descriptor may still be
// non-configurable.  We always use defineProperty so we can override it
// regardless of what the current descriptor says.
// ---------------------------------------------------------------------------

const originalWebSocket = globalThis.WebSocket

function installWebSocket(ctor: unknown) {
  Object.defineProperty(globalThis, 'WebSocket', {
    value: ctor,
    writable: true,
    configurable: true,
  })
}

beforeEach(() => {
  ControlledWebSocket.instances = []
  installWebSocket(ControlledWebSocket)
})

afterEach(() => {
  installWebSocket(originalWebSocket)
})

// ---------------------------------------------------------------------------
// Helper: minimal WsInboundMessage
// ---------------------------------------------------------------------------

function makeMsg(content: string): WsInboundMessage {
  return { type: 'assistant_message', content } as unknown as WsInboundMessage
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useReconnectingWebSocket — superseded-socket guards (DEC-FRONTEND-019)', () => {
  it('normal single mount: onMessage is called for socket messages', async () => {
    const received: WsInboundMessage[] = []
    const { unmount } = renderHook(() =>
      useReconnectingWebSocket({
        url: 'ws://localhost/test',
        onMessage: (msg) => received.push(msg),
      })
    )

    const [ws] = ControlledWebSocket.instances
    await act(async () => { ws.triggerOpen() })
    await act(async () => { ws.triggerMessage(makeMsg('hello')) })

    expect(received).toHaveLength(1)
    expect((received[0] as unknown as { content: string }).content).toBe('hello')
    unmount()
  })

  it('StrictMode double-mount: only the second socket delivers messages', async () => {
    const received: WsInboundMessage[] = []

    // Simulate StrictMode: mount, immediate cleanup (unmount), re-mount
    const { unmount: unmount1 } = renderHook(() =>
      useReconnectingWebSocket({
        url: 'ws://localhost/strictmode',
        onMessage: (msg) => received.push(msg),
      })
    )

    // First socket was created
    expect(ControlledWebSocket.instances).toHaveLength(1)
    const ws1 = ControlledWebSocket.instances[0]

    // StrictMode cleanup — sets intentionalCloseRef = true, nulls wsRef
    unmount1()

    // StrictMode re-mount — creates second socket, resets intentionalCloseRef = false
    const { unmount: unmount2 } = renderHook(() =>
      useReconnectingWebSocket({
        url: 'ws://localhost/strictmode',
        onMessage: (msg) => received.push(msg),
      })
    )

    expect(ControlledWebSocket.instances).toHaveLength(2)
    const ws2 = ControlledWebSocket.instances[1]

    // Now fire ws1.onopen AFTER the second mount has overwritten wsRef.
    // Without the wsRef.current !== ws guard, ws1 would authenticate and
    // both sockets would deliver messages. With the guard, ws1 closes itself.
    await act(async () => { ws1.triggerOpen() })
    // ws1 should have called close() on itself (superseded guard)
    expect(ws1.closedCount).toBeGreaterThanOrEqual(1)

    // ws2 opens normally
    await act(async () => { ws2.triggerOpen() })

    // Fire a message on both sockets
    await act(async () => { ws1.triggerMessage(makeMsg('from-ws1-should-be-dropped')) })
    await act(async () => { ws2.triggerMessage(makeMsg('from-ws2-should-arrive')) })

    // Only ws2's message should reach the callback
    expect(received).toHaveLength(1)
    expect((received[0] as unknown as { content: string }).content).toBe('from-ws2-should-arrive')

    unmount2()
  })

  it('superseded socket onclose does not trigger a spurious reconnect', async () => {
    const statusChanges: string[] = []

    const { unmount: unmount1 } = renderHook(() =>
      useReconnectingWebSocket({
        url: 'ws://localhost/noreconnect',
        onMessage: () => {},
        onStatusChange: (s) => statusChanges.push(s),
      })
    )

    const ws1 = ControlledWebSocket.instances[0]
    unmount1()

    const { unmount: unmount2 } = renderHook(() =>
      useReconnectingWebSocket({
        url: 'ws://localhost/noreconnect',
        onMessage: () => {},
        onStatusChange: (s) => statusChanges.push(s),
      })
    )

    const ws2 = ControlledWebSocket.instances[1]
    await act(async () => { ws2.triggerOpen() })

    const instanceCountBeforeWs1Close = ControlledWebSocket.instances.length

    // ws1 closes — should be a no-op because it's superseded
    await act(async () => { ws1.triggerClose() })

    // No new WebSocket should have been created (no spurious reconnect)
    expect(ControlledWebSocket.instances.length).toBe(instanceCountBeforeWs1Close)

    unmount2()
  })
})
