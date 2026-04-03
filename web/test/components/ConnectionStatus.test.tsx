/**
 * ConnectionStatus.test.tsx — tests for the connection status banner.
 *
 * ConnectionStatus is a pure presentational component that maps a
 * ReconnectingWsStatus value to a visible banner (or nothing for 'open').
 * Tests cover all four status values and verify ARIA attributes for
 * accessibility.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ConnectionStatus } from '../../src/components/ConnectionStatus'
import type { ReconnectingWsStatus } from '../../src/hooks/useReconnectingWebSocket'

describe('ConnectionStatus', () => {
  it('renders nothing when status is open', () => {
    const { container } = render(<ConnectionStatus status="open" />)
    expect(container.firstChild).toBeNull()
  })

  it('renders a banner with role="status" when not open', () => {
    render(<ConnectionStatus status="connecting" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows "Connecting…" label for connecting state', () => {
    render(<ConnectionStatus status="connecting" />)
    expect(screen.getByRole('status')).toHaveTextContent('Connecting…')
  })

  it('shows "Reconnecting…" label for reconnecting state', () => {
    render(<ConnectionStatus status="reconnecting" />)
    expect(screen.getByRole('status')).toHaveTextContent('Reconnecting…')
  })

  it('shows disconnected label for closed state', () => {
    render(<ConnectionStatus status="closed" />)
    expect(screen.getByRole('status')).toHaveTextContent('Disconnected')
  })

  it('applies the correct modifier class for connecting', () => {
    render(<ConnectionStatus status="connecting" />)
    expect(screen.getByRole('status')).toHaveClass('connection-status--connecting')
  })

  it('applies the correct modifier class for reconnecting', () => {
    render(<ConnectionStatus status="reconnecting" />)
    expect(screen.getByRole('status')).toHaveClass('connection-status--reconnecting')
  })

  it('applies the correct modifier class for closed', () => {
    render(<ConnectionStatus status="closed" />)
    expect(screen.getByRole('status')).toHaveClass('connection-status--closed')
  })

  it('sets aria-live="polite" on the banner', () => {
    render(<ConnectionStatus status="reconnecting" />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
  })

  it('sets aria-label describing the current status', () => {
    render(<ConnectionStatus status="reconnecting" />)
    expect(screen.getByRole('status')).toHaveAttribute(
      'aria-label',
      'Connection status: Reconnecting…',
    )
  })

  it('transitions from open to reconnecting — banner appears', () => {
    const { rerender } = render(
      <ConnectionStatus status={'open' as ReconnectingWsStatus} />,
    )
    expect(screen.queryByRole('status')).toBeNull()

    rerender(<ConnectionStatus status="reconnecting" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('transitions from reconnecting to open — banner disappears', () => {
    const { rerender } = render(<ConnectionStatus status="reconnecting" />)
    expect(screen.getByRole('status')).toBeInTheDocument()

    rerender(<ConnectionStatus status={'open' as ReconnectingWsStatus} />)
    expect(screen.queryByRole('status')).toBeNull()
  })
})
