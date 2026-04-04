/**
 * BottomNav — fixed bottom tab navigation for mobile layout.
 *
 * Renders a flex row of tab buttons fixed to the bottom of the viewport.
 * Each tab displays an icon (emoji/text) above a label. The active tab
 * uses the primary-light colour; inactive tabs use text-muted.
 *
 * All visual values come from CSS custom properties defined in
 * `styles/tokens.css`.
 *
 * @decision DEC-UI-BOTTOMNAV
 * @title BottomNav uses inline styles referencing CSS custom properties
 * @status accepted
 * @rationale Consistent with the project's inline-style-with-tokens pattern
 *   used by Card, Button, TopBar, etc. Fixed positioning and full-width
 *   layout are straightforward with inline styles.
 */

import { useRef, type CSSProperties, type KeyboardEvent } from 'react'

export interface NavTab {
  id: string
  icon: string
  label: string
}

export interface BottomNavProps {
  tabs: NavTab[]
  activeTab: string
  onTabChange: (id: string) => void
}

const navStyle: CSSProperties = {
  position: 'fixed',
  bottom: 0,
  left: 0,
  right: 0,
  display: 'flex',
  background: 'var(--color-bg-card)',
  borderTop: '1px solid var(--color-border)',
  zIndex: 100,
}

const tabBaseStyle: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  minHeight: 'var(--touch-target-min)',
  padding: 'var(--space-xs) 0',
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  gap: '2px',
}

const iconStyle: CSSProperties = {
  fontSize: '20px',
  lineHeight: 1,
}

const labelStyle: CSSProperties = {
  fontSize: 'var(--size-xs)',
  lineHeight: 1,
}

export function BottomNav({ tabs, activeTab, onTabChange }: BottomNavProps) {
  const tabListRef = useRef<HTMLDivElement>(null)

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = tabs.findIndex((t) => t.id === activeTab)
    let nextIndex: number | null = null

    if (e.key === 'ArrowRight') {
      nextIndex = (currentIndex + 1) % tabs.length
    } else if (e.key === 'ArrowLeft') {
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
    }

    if (nextIndex !== null) {
      e.preventDefault()
      onTabChange(tabs[nextIndex].id)
      const buttons = tabListRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
      buttons?.[nextIndex]?.focus()
    }
  }

  return (
    <nav className="ada-bottom-nav" style={navStyle} aria-label="Main navigation">
      <div role="tablist" ref={tabListRef} style={{ display: 'flex', flex: 1 }} onKeyDown={handleKeyDown}>
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab
          const color = isActive ? 'var(--color-primary-light)' : 'var(--color-text-muted)'

          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              style={{ ...tabBaseStyle, color }}
              onClick={() => onTabChange(tab.id)}
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              aria-label={tab.label}
            >
              <span style={iconStyle} aria-hidden="true">{tab.icon}</span>
              <span style={labelStyle}>{tab.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}
