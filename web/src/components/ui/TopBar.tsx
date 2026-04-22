/**
 * TopBar — app header bar with greeting, notification bell, and avatar.
 *
 * Renders a flex row with the greeting/subtitle on the left and
 * action buttons (notification bell, avatar circle) on the right.
 * All visual values come from CSS custom properties defined in
 * `styles/tokens.css`.
 *
 * @decision DEC-UI-TOPBAR
 * @title TopBar uses inline styles referencing CSS custom properties
 * @status accepted
 * @rationale Matches the existing component pattern (Card, Button, etc.)
 *   of inline style objects that reference `var(--token)` for zero-CSS-file
 *   overhead while keeping values tied to the shared design token layer.
 */

import type { CSSProperties } from 'react'
import { Button } from './Button'

export interface TopBarProps {
  greeting: string
  subtitle?: string
  onNotification?: () => void
  onProfile?: () => void
  notificationCount?: number
  onLogout?: () => void
}

const barStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  background: 'var(--color-bg-card)',
  padding: 'var(--space-md)',
}

const leftStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '2px',
}

const subtitleStyle: CSSProperties = {
  fontSize: 'var(--size-caption)',
  color: 'var(--color-text-muted)',
  fontFamily: 'var(--font-body)',
}

const titleStyle: CSSProperties = {
  fontSize: 'var(--size-h2)',
  fontWeight: 700,
  fontFamily: 'var(--font-heading)',
  color: 'var(--color-text-primary)',
  margin: 0,
}

const rightStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-sm)',
}

const iconBtnStyle: CSSProperties = {
  background: 'transparent',
  border: 'none',
  cursor: 'pointer',
  position: 'relative',
  minWidth: 'var(--touch-target-min)',
  minHeight: 'var(--touch-target-min)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '20px',
  color: 'var(--color-text-secondary)',
  borderRadius: 'var(--radius-button)',
  padding: 0,
}

const badgeStyle: CSSProperties = {
  position: 'absolute',
  top: '4px',
  right: '4px',
  background: 'var(--color-danger)',
  color: '#fff',
  fontSize: '10px',
  fontWeight: 700,
  borderRadius: '50%',
  width: '18px',
  height: '18px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  lineHeight: 1,
}

const avatarStyle: CSSProperties = {
  width: '36px',
  height: '36px',
  borderRadius: '50%',
  background: 'var(--color-primary-subtle)',
  border: '2px solid var(--color-primary)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '14px',
  color: 'var(--color-primary-light)',
  cursor: 'pointer',
}

export function TopBar({ greeting, subtitle, onNotification, onProfile, notificationCount, onLogout }: TopBarProps) {
  return (
    <header className="ada-topbar" style={barStyle}>
      <div style={leftStyle}>
        {subtitle && <span style={subtitleStyle}>{subtitle}</span>}
        <h2 style={titleStyle}>{greeting}</h2>
      </div>
      <div style={rightStyle}>
        {onLogout && (
          <Button variant="secondary" size="sm" onClick={onLogout}>
            Sign out
          </Button>
        )}
        <button
          type="button"
          className="ada-topbar-icon-btn"
          style={iconBtnStyle}
          onClick={onNotification}
          aria-label={
            notificationCount
              ? `Notifications (${notificationCount} unread)`
              : 'Notifications'
          }
        >
          🔔
          {notificationCount != null && notificationCount > 0 && (
            <span style={badgeStyle} aria-hidden="true">
              {notificationCount > 9 ? '9+' : notificationCount}
            </span>
          )}
        </button>
        <div
          className="ada-topbar-icon-btn"
          style={avatarStyle}
          role="button"
          tabIndex={0}
          onClick={onProfile}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onProfile?.()
          }}
          aria-label="Profile menu"
        >
          👤
        </div>
      </div>
    </header>
  )
}
