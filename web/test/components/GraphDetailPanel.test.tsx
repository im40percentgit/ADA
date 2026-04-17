/**
 * GraphDetailPanel.test.tsx — unit tests for the dialog detail panel,
 * covering motion class presence, focus-trap semantics, and mount/unmount
 * coordination for entrance/exit animation.
 *
 * # Testing strategy
 *
 * jsdom does not evaluate CSS transitions, so we cannot observe transition
 * completion or verify visual opacity changes. Instead we:
 *  - Assert the correct CSS classes are applied (ada-dialog, ada-dialog--open)
 *    so the rules in base.css (DEC-MOTION-004) will apply in a real browser.
 *  - Use fake timers to advance the 240ms exit timeout and assert the element
 *    unmounts after the timer fires, without actually waiting.
 *  - Test focus-trap behaviour directly via userEvent keyboard simulation.
 *
 * # Reduced-motion
 * The blanket prefers-reduced-motion override in base.css zeroes all transition
 * durations to 0.01ms. The 240ms setTimeout in GraphDetailPanel is a JS timer,
 * not a CSS duration, so reduced-motion does NOT affect unmount timing — the
 * element unmounts 240ms after close regardless of motion preference. This is
 * intentional: the brief 240ms is imperceptible with a 0.01ms transition and
 * the UX is equivalent to instant close. axe-core is not installed in this
 * project's test suite; a11y is validated via role/label assertions instead.
 *
 * @decision DEC-MOTION-004
 * @title Dialog entrance/exit uses opacity + translateY(12px), duration-base
 * @status accepted
 * @rationale See GraphDetailPanel.tsx for full rationale.
 */

import { render, screen, act, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { GraphDetailPanel } from '../../src/components/GraphDetailPanel'
import type { KnowledgeNode, KnowledgeEdge } from '../../src/types'

// ── Fixtures ─────────────────────────────────────────────────────────────────

function makeNode(overrides: Partial<KnowledgeNode> = {}): KnowledgeNode {
  return {
    id: 'node-1',
    patient_id: 'patient-1',
    node_type: 'emotion',
    label: 'Anxiety',
    properties: {},
    mention_count: 7,
    confidence: 0.85,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeEdge(overrides: Partial<KnowledgeEdge> = {}): KnowledgeEdge {
  return {
    id: 'edge-1',
    patient_id: 'patient-1',
    from_node: 'node-1',
    to_node: 'node-2',
    relation: 'co-occurs',
    weight: 0.6,
    mention_count: 3,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

const connectedNode = makeNode({ id: 'node-2', label: 'Stress', node_type: 'symptom' })

// ── Default render helper ─────────────────────────────────────────────────────

function renderPanel(
  node: KnowledgeNode | null,
  overrides: { onClose?: () => void; onSelectNode?: (id: string) => void } = {},
) {
  const onClose = overrides.onClose ?? vi.fn()
  const onSelectNode = overrides.onSelectNode ?? vi.fn()
  const utils = render(
    <GraphDetailPanel
      node={node}
      edges={[makeEdge()]}
      allNodes={[makeNode(), connectedNode]}
      onSelectNode={onSelectNode}
      onClose={onClose}
    />,
  )
  return { ...utils, onClose, onSelectNode }
}

// ═════════════════════════════════════════════════════════════════════════════
// Null node — panel should not render
// ═════════════════════════════════════════════════════════════════════════════

describe('GraphDetailPanel — null node', () => {
  it('renders nothing when node is null', () => {
    const { container } = renderPanel(null)
    expect(container.firstChild).toBeNull()
  })
})

// ── Helper: render an open panel and flush the setTimeout(0) that applies
//    ada-dialog--open. All timer-dependent tests call this.
async function renderOpenPanel(
  node: KnowledgeNode = makeNode(),
  overrides: { onClose?: () => void; onSelectNode?: (id: string) => void } = {},
) {
  const result = renderPanel(node, overrides)
  // Flush the zero-delay setTimeout that triggers setIsOpen(true), plus any
  // queued state updates, so ada-dialog--open is applied before assertions.
  await act(async () => { vi.runAllTimers() })
  return result
}

// ═════════════════════════════════════════════════════════════════════════════
// Open state — content, roles, and motion classes
// ═════════════════════════════════════════════════════════════════════════════

describe('GraphDetailPanel — open state', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('renders the dialog when a node is provided', async () => {
    await renderOpenPanel()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('dialog has aria-modal="true"', async () => {
    await renderOpenPanel()
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
  })

  it('dialog is labelled by the node title', async () => {
    await renderOpenPanel()
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-labelledby', 'graph-detail-panel-title')
    expect(screen.getByText('Anxiety')).toBeInTheDocument()
  })

  it('applies ada-dialog base class for motion CSS', async () => {
    await renderOpenPanel()
    expect(screen.getByRole('dialog').classList.contains('ada-dialog')).toBe(true)
  })

  it('applies ada-dialog--open class after entering open state', async () => {
    await renderOpenPanel()
    expect(screen.getByRole('dialog').classList.contains('ada-dialog--open')).toBe(true)
  })

  it('shows node label, type badge, mention count, and confidence', async () => {
    await renderOpenPanel()
    expect(screen.getByText('Anxiety')).toBeInTheDocument()
    expect(screen.getByText('emotion')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()   // mention_count
    expect(screen.getByText('85%')).toBeInTheDocument() // confidence 0.85
  })

  it('renders connected node buttons', async () => {
    await renderOpenPanel()
    expect(screen.getByRole('button', { name: 'Stress' })).toBeInTheDocument()
  })

  it('close button is present and has accessible label', async () => {
    await renderOpenPanel()
    expect(screen.getByRole('button', { name: 'Close detail panel' })).toBeInTheDocument()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Exit animation — mount/unmount coordination
// ═════════════════════════════════════════════════════════════════════════════

describe('GraphDetailPanel — exit animation (mount/unmount coordination)', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  function rerenderClosed(rerender: ReturnType<typeof render>['rerender']) {
    rerender(
      <GraphDetailPanel
        node={null}
        edges={[makeEdge()]}
        allNodes={[makeNode(), connectedNode]}
        onSelectNode={vi.fn()}
        onClose={vi.fn()}
      />,
    )
  }

  it('panel stays in DOM immediately after node is set to null (exit in progress)', async () => {
    const { rerender } = await renderOpenPanel()
    rerenderClosed(rerender)
    // Dialog still in DOM — exit timer (240ms) hasn't fired yet
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('removes ada-dialog--open class when node becomes null (triggers CSS exit)', async () => {
    const { rerender } = await renderOpenPanel()
    rerenderClosed(rerender)
    const dialog = screen.getByRole('dialog')
    expect(dialog.classList.contains('ada-dialog--open')).toBe(false)
    // Base ada-dialog class remains (provides exit transition styles)
    expect(dialog.classList.contains('ada-dialog')).toBe(true)
  })

  it('unmounts from DOM after the 240ms exit timer fires', async () => {
    const { rerender } = await renderOpenPanel()
    rerenderClosed(rerender)
    await act(async () => { vi.advanceTimersByTime(240) })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('element still present at 239ms (just before exit timer fires)', async () => {
    const { rerender } = await renderOpenPanel()
    rerenderClosed(rerender)
    await act(async () => { vi.advanceTimersByTime(239) })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Focus trap
// ═════════════════════════════════════════════════════════════════════════════
//
// Focus-trap tests use REAL timers to avoid the known deadlock between
// @testing-library/user-event v14 internal delays and vi.useFakeTimers().
// The component's setTimeout(0) fires near-instantly under real timers; we
// wait for the ada-dialog--open class using waitFor instead of advancing time.
//
// Keyboard/click events that trigger focus trap logic are dispatched directly
// via fireEvent (synchronous, no timer dependency) for assertions on focus
// movement. userEvent is used only for non-timer-sensitive click tests.

describe('GraphDetailPanel — focus trap', () => {
  // Helper: render and wait for the open state under real timers
  async function renderAndWaitOpen(
    node: KnowledgeNode = makeNode(),
    overrides: { onClose?: () => void; onSelectNode?: (id: string) => void } = {},
  ) {
    const result = renderPanel(node, overrides)
    await waitFor(() => {
      expect(screen.getByRole('dialog').classList.contains('ada-dialog--open')).toBe(true)
    })
    return result
  }

  it('focuses the close button on open', async () => {
    await renderAndWaitOpen()
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: 'Close detail panel' }),
    )
  })

  it('Escape key calls onClose immediately (no wait for animation)', async () => {
    const onClose = vi.fn()
    await renderAndWaitOpen(makeNode(), { onClose })

    // Fire Escape on the close button (which holds focus after open)
    const closeBtn = screen.getByRole('button', { name: 'Close detail panel' })
    fireEvent.keyDown(closeBtn, { key: 'Escape', bubbles: true })

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('Tab forward wraps from last to first focusable element', async () => {
    await renderAndWaitOpen()

    // Focus the last focusable element (connected node button "Stress")
    const stressBtn = screen.getByRole('button', { name: 'Stress' })
    stressBtn.focus()
    expect(document.activeElement).toBe(stressBtn)

    // Simulate Tab from the last element — focus trap should redirect to first
    fireEvent.keyDown(stressBtn, { key: 'Tab', bubbles: true })
    // The keyDown handler calls e.preventDefault() + last.focus() when on last element;
    // jsdom moves focus to the first element
    expect(document.activeElement).toBe(
      screen.getByRole('button', { name: 'Close detail panel' }),
    )
  })

  it('Shift+Tab backward wraps from first to last focusable element', async () => {
    await renderAndWaitOpen()

    // Focus the first focusable element (close button)
    const closeBtn = screen.getByRole('button', { name: 'Close detail panel' })
    closeBtn.focus()
    expect(document.activeElement).toBe(closeBtn)

    // Simulate Shift+Tab from the first element — focus trap redirects to last
    fireEvent.keyDown(closeBtn, { key: 'Tab', shiftKey: true, bubbles: true })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Stress' }))
  })

  it('clicking close button calls onClose', async () => {
    const onClose = vi.fn()
    await renderAndWaitOpen(makeNode(), { onClose })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Close detail panel' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('clicking connected node button calls onSelectNode with correct id', async () => {
    const onSelectNode = vi.fn()
    await renderAndWaitOpen(makeNode(), { onSelectNode })

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Stress' }))

    expect(onSelectNode).toHaveBeenCalledWith('node-2')
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Motion CSS source checks (parallel to the micro-interactions.test.tsx pattern)
// ═════════════════════════════════════════════════════════════════════════════

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const BASE_CSS_PATH = resolve(__dirname, '../../src/styles/base.css')
const baseCss = readFileSync(BASE_CSS_PATH, 'utf-8')

describe('base.css — DEC-MOTION-004 dialog motion rules', () => {
  it('contains DEC-MOTION-004 annotation', () => {
    expect(baseCss).toContain('DEC-MOTION-004')
  })

  it('defines .ada-dialog rule with opacity and transform', () => {
    expect(baseCss).toContain('.ada-dialog')
    // Default (closed) state: opacity 0, translateY(12px)
    const dialogSection = baseCss.slice(baseCss.indexOf('.ada-dialog'))
    expect(dialogSection).toContain('opacity: 0')
    expect(dialogSection).toContain('translateY(12px)')
  })

  it('.ada-dialog uses --motion-duration-base token (no hardcoded ms)', () => {
    const start = baseCss.indexOf('DEC-MOTION-004')
    const end = baseCss.indexOf('Reduced motion', start)
    const section = end > start ? baseCss.slice(start, end) : baseCss.slice(start)
    expect(section).toContain('var(--motion-duration-base)')
    // No bare ms values in the dialog section
    expect(section).not.toMatch(/:\s*240ms\s*[;,]/)
  })

  it('.ada-dialog transition uses --motion-ease-in for exit', () => {
    const dialogBlock = baseCss.slice(
      baseCss.indexOf('.ada-dialog\n') !== -1
        ? baseCss.indexOf('.ada-dialog\n')
        : baseCss.indexOf('.ada-dialog {'),
      baseCss.indexOf('.ada-dialog--open')
    )
    expect(dialogBlock).toContain('var(--motion-ease-in)')
  })

  it('.ada-dialog--open sets opacity: 1 and translateY(0)', () => {
    const openBlock = baseCss.slice(baseCss.indexOf('.ada-dialog--open'))
    expect(openBlock).toContain('opacity: 1')
    expect(openBlock).toContain('translateY(0)')
  })

  it('.ada-dialog--open transition uses --motion-ease-out for entrance', () => {
    const openBlock = baseCss.slice(baseCss.indexOf('.ada-dialog--open'))
    expect(openBlock).toContain('var(--motion-ease-out)')
  })

  it('DEC-MOTION-004 section comes before the reduced-motion block', () => {
    const motionIdx = baseCss.indexOf('DEC-MOTION-004')
    const reduceIdx = baseCss.indexOf('prefers-reduced-motion: reduce')
    expect(reduceIdx).toBeGreaterThan(motionIdx)
  })
})
