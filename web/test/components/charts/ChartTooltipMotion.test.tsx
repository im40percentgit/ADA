/**
 * ChartTooltipMotion.test.tsx — DEC-MOTION-007 chart tooltip class coverage.
 *
 * The chart tooltip motion (DEC-MOTION-007 affordance #2) is implemented by
 * adding the class .chart-tooltip-motion to the ResponsiveContainer wrapper
 * element in SessionFrequencyChart and WellbeingTrendChart. The CSS rule
 *   .chart-tooltip-motion .recharts-tooltip-wrapper { transition: ... }
 * targets the Recharts-managed tooltip div.
 *
 * WHY JSDOM CANNOT EXERCISE THE TOOLTIP TRANSITION:
 *   - Recharts renders its tooltip wrapper only when a user hovers a data
 *     point. In jsdom there is no DOM layout, no pointer events that trigger
 *     Recharts' internal SVG hit-testing, and no computed CSS (getComputedStyle
 *     returns empty strings for all properties). The tooltip div is never
 *     inserted into the DOM during a jsdom test run.
 *   - ResponsiveContainer in jsdom gets clientWidth=0/clientHeight=0, so
 *     Recharts renders with 0×0 dimensions and no chart paths are drawn. Even
 *     if we could dispatch a mouseover, there are no SVG path elements to hit.
 *   - CSS transitions are a paint-layer concern — jsdom does not evaluate
 *     them. Testing that getComputedStyle(wrapper).transitionProperty === '...'
 *     would always return an empty string regardless of what the stylesheet says.
 *
 * WHAT IS VERIFIED INSTEAD:
 *   The class .chart-tooltip-motion is present on the ResponsiveContainer
 *   wrapper in the rendered DOM. This confirms the hook-up point between our
 *   React components and the CSS rule. The CSS correctness is verified by a
 *   visual review and the token-driven blanket reduced-motion override
 *   (DEC-MOTION-002) which zeroes all transition durations.
 *
 * @decision DEC-MOTION-007
 * @title Chart tooltip motion: .chart-tooltip-motion class presence verified in jsdom
 * @status accepted
 * @rationale The CSS transition on .recharts-tooltip-wrapper cannot be exercised
 *   in jsdom (no layout, no pointer events, no CSS evaluation). We verify that
 *   the wrapper class is present in the DOM so the CSS selector can attach at
 *   runtime in a real browser.
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { SessionFrequencyChart } from '../../../src/components/charts/SessionFrequencyChart'
import { WellbeingTrendChart } from '../../../src/components/charts/WellbeingTrendChart'

const SESSION_DATA = [
  { week: '2026-W01', count: 2 },
  { week: '2026-W02', count: 3 },
]

const WELLBEING_DATA = [
  { date: '2026-01-01', score: 48 },
  { date: '2026-01-08', score: 56 },
]

describe('SessionFrequencyChart — DEC-MOTION-007 tooltip motion class', () => {
  it('renders the chart-tooltip-motion class on the ResponsiveContainer wrapper', () => {
    const { container } = render(<SessionFrequencyChart data={SESSION_DATA} />)
    // Recharts ResponsiveContainer renders a div with the className we pass
    const wrapper = container.querySelector('.chart-tooltip-motion')
    expect(wrapper).toBeInTheDocument()
  })

  it('renders the sessions-per-week heading', () => {
    render(<SessionFrequencyChart data={SESSION_DATA} />)
    expect(screen.getByText(/Sessions per Week/i)).toBeInTheDocument()
  })

  it('renders empty state when data is empty', () => {
    render(<SessionFrequencyChart data={[]} />)
    expect(screen.getByText(/No session data available/i)).toBeInTheDocument()
  })

  /**
   * Tooltip transition class NOT tested via interaction:
   * Recharts injects .recharts-tooltip-wrapper only on hover of a data point,
   * which requires DOM layout + pointer events that jsdom cannot provide.
   * The CSS rule is verified by visual review only.
   */
})

describe('WellbeingTrendChart — DEC-MOTION-007 tooltip motion class', () => {
  it('renders the chart-tooltip-motion class on the ResponsiveContainer wrapper', () => {
    const { container } = render(<WellbeingTrendChart data={WELLBEING_DATA} />)
    const wrapper = container.querySelector('.chart-tooltip-motion')
    expect(wrapper).toBeInTheDocument()
  })

  it('renders the WHO-5 wellbeing trend heading', () => {
    render(<WellbeingTrendChart data={WELLBEING_DATA} />)
    expect(screen.getByText(/WHO-5 Wellbeing Trend/i)).toBeInTheDocument()
  })

  it('renders empty state when data is empty', () => {
    render(<WellbeingTrendChart data={[]} />)
    expect(screen.getByText(/No WHO-5 data available/i)).toBeInTheDocument()
  })

  it('renders delta annotation when two or more data points are present', () => {
    render(<WellbeingTrendChart data={WELLBEING_DATA} />)
    // Delta = 56 - 48 = +8
    expect(screen.getByText(/Change: \+8 points/i)).toBeInTheDocument()
  })
})
