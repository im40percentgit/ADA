/**
 * ErrorBoundary — class-based React error boundary.
 *
 * Catches render-time throws from any descendant and renders an
 * <ErrorState> fallback with the caught error message. React requires
 * class components for error boundaries (getDerivedStateFromError /
 * componentDidCatch are not available on function components).
 *
 * Props:
 *   children      — subtree to protect
 *   fallbackTitle — override the ErrorState title (default: "Something went wrong")
 *   onError       — optional callback(error, info) fired after componentDidCatch
 *
 * AsyncBoundary pattern (DEC-ERROR-002):
 *   For async data loading, the recommended pattern is to use ErrorBoundary
 *   directly alongside a Suspense boundary rather than a combined AsyncBoundary
 *   component. This keeps concerns separated and avoids coupling error handling
 *   to loading-state management. Example:
 *
 *     <ErrorBoundary>
 *       <Suspense fallback={<SkeletonCard />}>
 *         <MyDataComponent />
 *       </Suspense>
 *     </ErrorBoundary>
 *
 *   If a shared AsyncBoundary abstraction becomes warranted in a future phase,
 *   introduce it then with usage evidence — YAGNI applies here.
 *
 * @decision DEC-ERROR-001
 * @title ErrorBoundary uses getDerivedStateFromError + componentDidCatch
 * @status accepted
 * @rationale getDerivedStateFromError is the canonical React API for
 *   render-phase error capture; it is synchronous and pure (no side effects),
 *   making it safe to use in concurrent mode. componentDidCatch handles
 *   post-render side effects (logging, external callbacks). Both together
 *   cover the full lifecycle per the React docs recommendation.
 *
 * @decision DEC-ERROR-002
 * @title AsyncBoundary is an inline pattern (ErrorBoundary + Suspense), not a component
 * @status accepted
 * @rationale Combining error boundaries and Suspense into a single
 *   AsyncBoundary component adds coupling without meaningful DX improvement
 *   for the current call sites. Each Phase 13e-02..06 view can compose
 *   ErrorBoundary + Suspense directly. If 3+ views repeat the same
 *   nesting, extract AsyncBoundary then.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ErrorState } from './ErrorState'

export interface ErrorBoundaryProps {
  children: ReactNode
  fallbackTitle?: string
  onError?: (error: Error, info: ErrorInfo) => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info)
  }

  render(): ReactNode {
    if (this.state.hasError && this.state.error) {
      return (
        <ErrorState
          title={this.props.fallbackTitle ?? 'Something went wrong'}
          message={this.state.error.message}
        />
      )
    }
    return this.props.children
  }
}
