/**
 * AppShell — responsive layout wrapper for Ada.
 *
 * Provides two distinct layouts depending on viewport width:
 *
 * Mobile (< 768px):
 *   - TopBar at top
 *   - Main content area (flex: 1, scrollable, bottom-padded for nav)
 *   - BottomNav fixed at bottom
 *
 * Desktop (>= 768px):
 *   - Flex row: sidebar left (240px) + main area right
 *   - TopBar at top of main area
 *   - BottomNav hidden
 *   - Sidebar nav items mirror the tab icons/labels
 *
 * Uses `window.matchMedia` to detect the breakpoint in a React hook
 * rather than CSS media queries, since the layout structure differs
 * between mobile and desktop (not just styling).
 *
 * @decision DEC-UI-APPSHELL
 * @title matchMedia hook for responsive layout switching
 * @status accepted
 * @rationale CSS media queries can toggle visibility but cannot
 *   restructure the React component tree. The matchMedia approach
 *   renders completely different DOM structures for mobile and
 *   desktop, keeping each layout clean and avoiding hidden-but-mounted
 *   elements.
 */

import { useState, useEffect } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { TopBar } from './ui/TopBar'
import { BottomNav } from './ui/BottomNav'
import type { NavTab } from './ui/BottomNav'

const DEFAULT_TABS: NavTab[] = [
  { id: 'home', icon: '\u{1F3E0}', label: 'Home' },
  { id: 'chat', icon: '\u{1F4AC}', label: 'Chat' },
  { id: 'journey', icon: '\u{1F5FA}\uFE0F', label: 'Journey' },
  { id: 'settings', icon: '\u2699\uFE0F', label: 'Settings' },
]

export interface AppShellProps {
  children: ReactNode
  activeTab: string
  onTabChange: (id: string) => void
  greeting: string
  subtitle?: string
  companionName?: string
  onNotification?: () => void
  onLogout?: () => void
}

// --- Styles ---

const shellMobileStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  overflow: 'hidden',
}

const mainMobileStyle: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  paddingBottom: '60px',
}

const shellDesktopStyle: CSSProperties = {
  display: 'flex',
  height: '100%',
  overflow: 'hidden',
}

const sidebarStyle: CSSProperties = {
  width: '240px',
  flexShrink: 0,
  display: 'flex',
  flexDirection: 'column',
  background: 'var(--color-bg-card)',
  borderRight: '1px solid var(--color-border)',
}

const sidebarBrandStyle: CSSProperties = {
  padding: 'var(--space-lg) var(--space-md)',
  borderBottom: '1px solid var(--color-border)',
}

const sidebarBrandNameStyle: CSSProperties = {
  fontSize: 'var(--size-h1)',
  fontWeight: 700,
  fontFamily: 'var(--font-heading)',
  color: 'var(--color-text-primary)',
  margin: 0,
}

const sidebarBrandTaglineStyle: CSSProperties = {
  fontSize: 'var(--size-caption)',
  color: 'var(--color-text-muted)',
  fontFamily: 'var(--font-body)',
  marginTop: '2px',
}

const sidebarNavStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  padding: 'var(--space-sm) 0',
  flex: 1,
}

const sidebarNavBtnBase: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-sm)',
  padding: 'var(--space-sm) var(--space-md)',
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  minHeight: 'var(--touch-target-min)',
  width: '100%',
  textAlign: 'left',
  borderRadius: 0,
}

const desktopMainAreaStyle: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const desktopContentStyle: CSSProperties = {
  flex: 1,
  overflowY: 'auto',
}

function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(
    typeof window !== 'undefined'
      ? window.matchMedia('(min-width: 768px)').matches
      : false,
  )

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return isDesktop
}

export function AppShell({
  children,
  activeTab,
  onTabChange,
  greeting,
  subtitle,
  companionName,
  onNotification,
  onLogout,
}: AppShellProps) {
  const isDesktop = useIsDesktop()

  if (isDesktop) {
    return (
      <div className="ada-shell ada-shell--desktop" style={shellDesktopStyle}>
        <a href="#main-content" className="skip-link">Skip to main content</a>
        {/* Sidebar */}
        <aside className="ada-shell__sidebar" style={sidebarStyle}>
          <div style={sidebarBrandStyle}>
            <h1 style={sidebarBrandNameStyle}>{companionName ?? 'Ada'}</h1>
            <p style={sidebarBrandTaglineStyle}>Mental Health Support</p>
          </div>
          <nav style={sidebarNavStyle} aria-label="Main navigation">
            {DEFAULT_TABS.map((tab) => {
              const isActive = tab.id === activeTab
              return (
                <button
                  key={tab.id}
                  type="button"
                  style={{
                    ...sidebarNavBtnBase,
                    color: isActive
                      ? 'var(--color-primary-light)'
                      : 'var(--color-text-muted)',
                    background: isActive
                      ? 'var(--color-primary-subtle)'
                      : 'transparent',
                  }}
                  onClick={() => onTabChange(tab.id)}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <span aria-hidden="true">{tab.icon}</span>
                  {tab.label}
                </button>
              )
            })}
          </nav>
        </aside>

        {/* Main area */}
        <div style={desktopMainAreaStyle}>
          <TopBar
            greeting={greeting}
            subtitle={subtitle}
            onNotification={onNotification}
            onLogout={onLogout}
          />
          <main id="main-content" className="ada-shell__content" style={desktopContentStyle}>
            {children}
          </main>
        </div>
      </div>
    )
  }

  // Mobile layout
  return (
    <div className="ada-shell ada-shell--mobile" style={shellMobileStyle}>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <TopBar
        greeting={greeting}
        subtitle={subtitle}
        onNotification={onNotification}
        onLogout={onLogout}
      />
      <main id="main-content" className="ada-shell__content" style={mainMobileStyle}>
        {children}
      </main>
      <BottomNav tabs={DEFAULT_TABS} activeTab={activeTab} onTabChange={onTabChange} />
    </div>
  )
}
