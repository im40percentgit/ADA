/**
 * ErrorBoundary.test.tsx — component tests for the ErrorBoundary UI primitive.
 *
 * Verifies:
 * - Children render normally when there is no error
 * - A child that throws is caught; ErrorState is rendered with the error message
 * - The fallback does not appear when there is no error
 * - onError callback fires when a child throws (if provided)
 *
 * @mock-exempt: console.error spy suppresses React's test-environment error logging
 *   for uncaught boundary errors — not mocking internal code. The onError vi.fn()
 *   is a stub for an external callback prop boundary (caller-supplied handler).
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { ErrorBoundary } from '../../../src/components/ui/ErrorBoundary'

// A component that unconditionally throws
function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('Bomb exploded')
  return <div>Safe content</div>
}

describe('ErrorBoundary', () => {
  it('renders children when no error is thrown', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>
    )
    expect(screen.getByText('Safe content')).toBeTruthy()
  })

  it('renders ErrorState when a child throws', () => {
    // Suppress the console.error that React logs for uncaught errors in tests
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>
    )
    // ErrorState should show up with the caught error message
    expect(screen.getByText('Bomb exploded')).toBeTruthy()
    consoleError.mockRestore()
  })

  it('does not render ErrorState when there is no error', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow={false} />
      </ErrorBoundary>
    )
    // ErrorState has role=status + aria-label="Error state"
    expect(screen.queryByLabelText('Error state')).toBeNull()
  })

  it('calls onError when provided and a child throws', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const onError = vi.fn()
    render(
      <ErrorBoundary onError={onError}>
        <Bomb shouldThrow={true} />
      </ErrorBoundary>
    )
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error)
    consoleError.mockRestore()
  })

  it('accepts a custom title prop for the fallback', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary fallbackTitle="Oops!">
        <Bomb shouldThrow={true} />
      </ErrorBoundary>
    )
    expect(screen.getByText('Oops!')).toBeTruthy()
    consoleError.mockRestore()
  })
})
