/**
 * AppShell.test.tsx — component tests for the AppShell responsive layout.
 *
 * Verifies:
 * - Children render inside the shell
 * - TopBar renders with the provided greeting
 * - BottomNav renders tabs in mobile mode (matchMedia defaults to false in tests)
 * - Tab change callback fires with the correct tab id
 * - Desktop layout renders sidebar when matchMedia matches
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AppShell } from '../../src/components/AppShell'

describe('AppShell', () => {
  // The global matchMedia mock from setup.ts returns matches: false by default,
  // which means the shell defaults to mobile layout.

  const defaultProps = {
    activeTab: 'home',
    onTabChange: vi.fn(),
    greeting: 'Good morning, Alex',
    subtitle: 'How are you today?',
  }

  beforeEach(() => {
    defaultProps.onTabChange = vi.fn()
  })

  it('renders children', () => {
    render(
      <AppShell {...defaultProps}>
        <div data-testid="child-content">Hello from child</div>
      </AppShell>,
    )
    expect(screen.getByTestId('child-content')).toBeTruthy()
    expect(screen.getByText('Hello from child')).toBeTruthy()
  })

  it('renders TopBar with greeting', () => {
    render(
      <AppShell {...defaultProps}>
        <div>Content</div>
      </AppShell>,
    )
    expect(screen.getByText('Good morning, Alex')).toBeTruthy()
  })

  it('renders TopBar with subtitle', () => {
    render(
      <AppShell {...defaultProps}>
        <div>Content</div>
      </AppShell>,
    )
    expect(screen.getByText('How are you today?')).toBeTruthy()
  })

  it('renders BottomNav with tabs in mobile mode', () => {
    render(
      <AppShell {...defaultProps}>
        <div>Content</div>
      </AppShell>,
    )
    // BottomNav should be present with tab labels
    expect(screen.getByText('Home')).toBeTruthy()
    expect(screen.getByText('Chat')).toBeTruthy()
    expect(screen.getByText('Journey')).toBeTruthy()
    expect(screen.getByText('Settings')).toBeTruthy()
  })

  it('fires onTabChange when a tab is clicked', async () => {
    render(
      <AppShell {...defaultProps}>
        <div>Content</div>
      </AppShell>,
    )
    const chatBtn = screen.getByLabelText('Chat')
    await userEvent.click(chatBtn)
    expect(defaultProps.onTabChange).toHaveBeenCalledWith('chat')
  })

  it('fires onTabChange with correct id for each tab', async () => {
    render(
      <AppShell {...defaultProps}>
        <div>Content</div>
      </AppShell>,
    )
    await userEvent.click(screen.getByLabelText('Journey'))
    expect(defaultProps.onTabChange).toHaveBeenCalledWith('journey')

    await userEvent.click(screen.getByLabelText('Settings'))
    expect(defaultProps.onTabChange).toHaveBeenCalledWith('settings')
  })

  it('highlights the active tab', () => {
    render(
      <AppShell {...defaultProps} activeTab="chat">
        <div>Content</div>
      </AppShell>,
    )
    const chatBtn = screen.getByLabelText('Chat')
    expect(chatBtn.getAttribute('aria-selected')).toBe('true')

    const homeBtn = screen.getByLabelText('Home')
    expect(homeBtn.getAttribute('aria-selected')).toBe('false')
  })

  describe('desktop layout', () => {
    beforeEach(() => {
      // Override matchMedia to simulate desktop
      Object.defineProperty(globalThis, 'matchMedia', {
        writable: true,
        value: (query: string) => ({
          matches: query === '(min-width: 768px)',
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        }),
      })
    })

    afterEach(() => {
      // Restore the default mock (matches: false)
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
    })

    it('renders sidebar with nav items on desktop', () => {
      const { container } = render(
        <AppShell {...defaultProps}>
          <div>Content</div>
        </AppShell>,
      )
      // Should have sidebar class
      expect(container.querySelector('.ada-shell--desktop')).toBeTruthy()
      expect(container.querySelector('.ada-shell__sidebar')).toBeTruthy()

      // Sidebar should show nav items
      const nav = screen.getByRole('navigation', { name: 'Main navigation' })
      expect(nav).toBeTruthy()
    })

    it('renders companion name in sidebar brand', () => {
      render(
        <AppShell {...defaultProps} companionName="Sage">
          <div>Content</div>
        </AppShell>,
      )
      expect(screen.getByText('Sage')).toBeTruthy()
    })

    it('defaults companion name to Ada', () => {
      render(
        <AppShell {...defaultProps}>
          <div>Content</div>
        </AppShell>,
      )
      expect(screen.getByText('Ada')).toBeTruthy()
    })
  })
})
