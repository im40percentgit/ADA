/**
 * micro-interactions.test.tsx — Verify hover/focus/press micro-interaction rules
 * for all 8 UI primitives (Button, Card, Input, Toggle, Badge, BottomNav,
 * ProgressBar, TopBar).
 *
 * Strategy (matching motion-tokens.test.ts):
 * - vitest.config.ts sets `css: false` so jsdom never evaluates stylesheets.
 *   `getComputedStyle` cannot resolve CSS custom properties or class-based rules.
 * - For CSS rules: read base.css as raw text and assert the expected selectors,
 *   property names, and token references appear in the source. This directly
 *   tests the source of truth without relying on jsdom CSS processing.
 * - For component class names: render via @testing-library/react and assert that
 *   the correct className is applied so that the CSS rules will target the element
 *   in a real browser.
 * - For inline-style transitions (ProgressBar): inspect the style attribute on
 *   the rendered fill div.
 *
 * @decision DEC-MOTION-003
 * @title Hover/press motion uses transform + opacity only (GPU-accelerated)
 * @status accepted
 * @rationale See base.css for full rationale. This test file verifies that the
 *   implementation matches the decision: tokens are used (no hardcoded ms),
 *   correct selectors exist, and components emit the expected class names.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Button } from '../../../src/components/ui/Button'
import { Card } from '../../../src/components/ui/Card'
import { Input } from '../../../src/components/ui/Input'
import { Toggle } from '../../../src/components/ui/Toggle'
import { Badge } from '../../../src/components/ui/Badge'
import { BottomNav } from '../../../src/components/ui/BottomNav'
import { ProgressBar } from '../../../src/components/ui/ProgressBar'
import { TopBar } from '../../../src/components/ui/TopBar'

const BASE_CSS = resolve(__dirname, '../../../src/styles/base.css')
const baseSource = readFileSync(BASE_CSS, 'utf-8')

// ── Helper: extract all text after a given marker within base.css ─────────────
function sectionAfter(marker: string): string {
  const idx = baseSource.indexOf(marker)
  return idx === -1 ? '' : baseSource.slice(idx)
}

const microSection = sectionAfter('DEC-MOTION-003')

// ═════════════════════════════════════════════════════════════════════════════
// base.css structural checks
// ═════════════════════════════════════════════════════════════════════════════

describe('base.css — DEC-MOTION-003 annotation and structure', () => {
  it('contains DEC-MOTION-003 annotation', () => {
    expect(baseSource).toContain('DEC-MOTION-003')
  })

  it('references DEC-MOTION-001 in the annotation block', () => {
    expect(microSection).toContain('DEC-MOTION-001')
  })

  it('references DEC-MOTION-002 in the annotation block', () => {
    expect(microSection).toContain('DEC-MOTION-002')
  })

  it('uses only motion token vars — no hardcoded ms values in micro-interaction rules', () => {
    // Extract the micro-interactions section (everything between DEC-MOTION-003
    // and the reduced-motion section)
    const start = baseSource.indexOf('DEC-MOTION-003')
    const end = baseSource.indexOf('Reduced motion', start)
    const section = end > start ? baseSource.slice(start, end) : microSection

    // Should not contain bare ms values like "80ms", "160ms", "240ms", "300ms", "0.3s", "0.2s"
    // (These are only acceptable inside token definitions in tokens.css, not here)
    expect(section).not.toMatch(/:\s*\d+ms\s*[;,]/)
    expect(section).not.toMatch(/:\s*0\.\d+s\s*[;,]/)
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Button
// ═════════════════════════════════════════════════════════════════════════════

describe('Button — micro-interaction CSS rules', () => {
  it('has .ada-btn transition rule using motion tokens', () => {
    expect(microSection).toContain('.ada-btn')
    expect(microSection).toContain('var(--motion-duration-instant)')
    expect(microSection).toContain('var(--motion-ease-standard)')
  })

  it('has .ada-btn:hover:not(:disabled) translateY rule', () => {
    expect(microSection).toContain('.ada-btn:hover:not(:disabled)')
    expect(microSection).toContain('translateY(-1px)')
  })

  it('has .ada-btn:active:not(:disabled) scale rule', () => {
    expect(microSection).toContain('.ada-btn:active:not(:disabled)')
    expect(microSection).toContain('scale(0.98)')
  })
})

describe('Button — component class names', () => {
  it('primary button has ada-btn class', () => {
    const { container } = render(<Button>Save</Button>)
    expect(container.querySelector('.ada-btn')).toBeTruthy()
  })

  it('secondary button has ada-btn class', () => {
    const { container } = render(<Button variant="secondary">Cancel</Button>)
    expect(container.querySelector('.ada-btn')).toBeTruthy()
  })

  it('ghost button has ada-btn class', () => {
    const { container } = render(<Button variant="ghost">Skip</Button>)
    expect(container.querySelector('.ada-btn')).toBeTruthy()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Card
// ═════════════════════════════════════════════════════════════════════════════

describe('Card — micro-interaction CSS rules', () => {
  it('has .ada-card--clickable transition rule', () => {
    expect(microSection).toContain('.ada-card--clickable')
  })

  it('has .ada-card--clickable:hover translateY rule', () => {
    expect(microSection).toContain('.ada-card--clickable:hover')
    expect(microSection).toContain('translateY(-1px)')
  })

  it('has .ada-card--clickable:active scale rule', () => {
    expect(microSection).toContain('.ada-card--clickable:active')
    expect(microSection).toContain('scale(0.98)')
  })
})

describe('Card — component class names', () => {
  it('clickable card has ada-card--clickable class', () => {
    const { container } = render(<Card onClick={() => {}}>Click me</Card>)
    expect(container.querySelector('.ada-card--clickable')).toBeTruthy()
  })

  it('non-clickable card does NOT have ada-card--clickable', () => {
    const { container } = render(<Card>Static</Card>)
    expect(container.querySelector('.ada-card--clickable')).toBeNull()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Input
// ═════════════════════════════════════════════════════════════════════════════

describe('Input — micro-interaction CSS rules', () => {
  it('has .ada-input input transition rule for border-color', () => {
    expect(microSection).toContain('.ada-input input')
    expect(microSection).toContain('border-color')
    expect(microSection).toContain('var(--motion-duration-quick)')
  })

  it('uses :focus-visible (not :focus) for the focus ring — a11y pattern', () => {
    expect(microSection).toContain('.ada-input input:focus-visible')
    // Must NOT use bare :focus for input (would catch mouse clicks too)
    const focusRule = microSection.match(/\.ada-input input:focus[^-]/g)
    expect(focusRule).toBeNull()
  })
})

describe('Input — component class names', () => {
  it('wrapper label has ada-input class', () => {
    const { container } = render(<Input label="Name" />)
    expect(container.querySelector('.ada-input')).toBeTruthy()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Toggle
// ═════════════════════════════════════════════════════════════════════════════

describe('Toggle — micro-interaction CSS rules', () => {
  it('has .ada-toggle__track transition rule using quick token', () => {
    expect(microSection).toContain('.ada-toggle__track')
    expect(microSection).toContain('var(--motion-duration-quick)')
  })

  it('has .ada-toggle__thumb transition rule', () => {
    expect(microSection).toContain('.ada-toggle__thumb')
  })
})

describe('Toggle — component class names', () => {
  it('track span has ada-toggle__track class', () => {
    const { container } = render(
      <Toggle checked={false} onChange={() => {}} label="Notifications" />
    )
    expect(container.querySelector('.ada-toggle__track')).toBeTruthy()
  })

  it('thumb span has ada-toggle__thumb class', () => {
    const { container } = render(
      <Toggle checked={true} onChange={() => {}} label="Dark mode" />
    )
    expect(container.querySelector('.ada-toggle__thumb')).toBeTruthy()
  })

  it('track has no hardcoded transition in inline style', () => {
    const { container } = render(
      <Toggle checked={false} onChange={() => {}} />
    )
    const track = container.querySelector('.ada-toggle__track') as HTMLElement
    // Inline style should NOT contain 'transition' — it's handled by CSS class
    expect(track?.style.transition).toBeFalsy()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Badge
// ═════════════════════════════════════════════════════════════════════════════

describe('Badge — micro-interaction CSS rules', () => {
  it('has .ada-badge--interactive opacity transition rule', () => {
    expect(microSection).toContain('.ada-badge--interactive')
    expect(microSection).toContain('opacity')
    expect(microSection).toContain('var(--motion-duration-instant)')
  })
})

describe('Badge — component class names', () => {
  it('badge has ada-badge class', () => {
    const { container } = render(<Badge variant="success">Active</Badge>)
    expect(container.querySelector('.ada-badge')).toBeTruthy()
  })

  it('badge variant class is present', () => {
    const { container } = render(<Badge variant="warning">Pending</Badge>)
    expect(container.querySelector('.ada-badge--warning')).toBeTruthy()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// BottomNav
// ═════════════════════════════════════════════════════════════════════════════

const testTabs = [
  { id: 'home', icon: '🏠', label: 'Home' },
  { id: 'chat', icon: '💬', label: 'Chat' },
  { id: 'settings', icon: '⚙️', label: 'Settings' },
]

describe('BottomNav — micro-interaction CSS rules', () => {
  it('has .ada-bottom-nav__indicator scaleX(0) rule', () => {
    expect(microSection).toContain('.ada-bottom-nav__indicator')
    expect(microSection).toContain('scaleX(0)')
  })

  it('has .ada-bottom-nav__tab--active .ada-bottom-nav__indicator scaleX(1) rule', () => {
    expect(microSection).toContain('.ada-bottom-nav__tab--active .ada-bottom-nav__indicator')
    expect(microSection).toContain('scaleX(1)')
  })

  it('indicator transition uses quick token', () => {
    const indicatorBlock = microSection.slice(
      microSection.indexOf('.ada-bottom-nav__indicator'),
      microSection.indexOf('.ada-bottom-nav__tab--active')
    )
    expect(indicatorBlock).toContain('var(--motion-duration-quick)')
    expect(indicatorBlock).toContain('var(--motion-ease-standard)')
  })
})

describe('BottomNav — component class names', () => {
  it('active tab has ada-bottom-nav__tab--active class', () => {
    const { container } = render(
      <BottomNav tabs={testTabs} activeTab="home" onTabChange={() => {}} />
    )
    const activeBtn = container.querySelector('.ada-bottom-nav__tab--active')
    expect(activeBtn).toBeTruthy()
    expect(activeBtn?.getAttribute('aria-selected')).toBe('true')
  })

  it('inactive tabs do NOT have ada-bottom-nav__tab--active class', () => {
    const { container } = render(
      <BottomNav tabs={testTabs} activeTab="home" onTabChange={() => {}} />
    )
    const allTabs = container.querySelectorAll('.ada-bottom-nav__tab')
    const activeTabs = container.querySelectorAll('.ada-bottom-nav__tab--active')
    expect(allTabs.length).toBe(3)
    expect(activeTabs.length).toBe(1)
  })

  it('every tab has an ada-bottom-nav__indicator span', () => {
    const { container } = render(
      <BottomNav tabs={testTabs} activeTab="chat" onTabChange={() => {}} />
    )
    const indicators = container.querySelectorAll('.ada-bottom-nav__indicator')
    expect(indicators.length).toBe(3)
  })

  it('indicator spans are aria-hidden', () => {
    const { container } = render(
      <BottomNav tabs={testTabs} activeTab="home" onTabChange={() => {}} />
    )
    const indicators = container.querySelectorAll('.ada-bottom-nav__indicator')
    indicators.forEach((el) => {
      expect(el.getAttribute('aria-hidden')).toBe('true')
    })
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// ProgressBar
// ═════════════════════════════════════════════════════════════════════════════

describe('ProgressBar — fill transition uses motion tokens', () => {
  it('fill div has transition referencing --motion-duration-base', () => {
    const { container } = render(
      <ProgressBar value={60} aria-label="Completion" />
    )
    const fill = container.querySelector('[role="progressbar"] div') as HTMLElement
    expect(fill).toBeTruthy()
    expect(fill.style.transition).toContain('var(--motion-duration-base)')
  })

  it('fill transition uses --motion-ease-emphasized', () => {
    const { container } = render(<ProgressBar value={40} />)
    const fill = container.querySelector('[role="progressbar"] div') as HTMLElement
    expect(fill.style.transition).toContain('var(--motion-ease-emphasized)')
  })

  it('fill transition does NOT use hardcoded 0.3s', () => {
    const { container } = render(<ProgressBar value={75} />)
    const fill = container.querySelector('[role="progressbar"] div') as HTMLElement
    expect(fill.style.transition).not.toContain('0.3s')
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// TopBar
// ═════════════════════════════════════════════════════════════════════════════

describe('TopBar — micro-interaction CSS rules', () => {
  it('has .ada-topbar-icon-btn transition rule', () => {
    expect(microSection).toContain('.ada-topbar-icon-btn')
    expect(microSection).toContain('var(--motion-duration-instant)')
  })

  it('has .ada-topbar-icon-btn:hover translateY rule', () => {
    expect(microSection).toContain('.ada-topbar-icon-btn:hover')
    expect(microSection).toContain('translateY(-1px)')
  })
})

describe('TopBar — component class names', () => {
  it('notification button has ada-topbar-icon-btn class', () => {
    const { container } = render(
      <TopBar greeting="Hello" onNotification={() => {}} />
    )
    const notifBtn = container.querySelector('button.ada-topbar-icon-btn')
    expect(notifBtn).toBeTruthy()
  })

  it('avatar div has ada-topbar-icon-btn class', () => {
    const { container } = render(
      <TopBar greeting="Hello" onProfile={() => {}} />
    )
    const avatar = container.querySelector('div.ada-topbar-icon-btn')
    expect(avatar).toBeTruthy()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// Reduced-motion safety check
// ═════════════════════════════════════════════════════════════════════════════

describe('Reduced-motion — blanket override still covers new rules', () => {
  it('prefers-reduced-motion block comes AFTER the micro-interaction rules', () => {
    const motionIdx = baseSource.indexOf('DEC-MOTION-003')
    const reduceIdx = baseSource.indexOf('prefers-reduced-motion: reduce')
    // The blanket override must appear after the interaction rules so it overrides them
    expect(reduceIdx).toBeGreaterThan(motionIdx)
  })

  it('reduced-motion block uses universal selector * (catches all new rules)', () => {
    const reduceStart = baseSource.indexOf('prefers-reduced-motion: reduce')
    const reduceSection = baseSource.slice(reduceStart)
    expect(reduceSection).toContain('transition-duration: 0.01ms !important')
  })

  it('micro-interaction section has no per-rule transition-duration overrides that escape blanket', () => {
    const start = baseSource.indexOf('DEC-MOTION-003')
    const end = baseSource.indexOf('Reduced motion', start)
    const section = end > start ? baseSource.slice(start, end) : microSection
    // Must not contain !important on transition-duration in the interaction section
    // (that would override the reduced-motion blanket override)
    expect(section).not.toContain('transition-duration:')
  })
})
