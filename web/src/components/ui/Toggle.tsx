/**
 * Toggle — accessible switch control styled as a sliding track + thumb.
 *
 * Renders a hidden `<input type="checkbox">` for form compatibility and
 * an adjacent visual track/thumb that reflects the checked state. The
 * track transitions between the elevated background and primary colour.
 *
 * Transition timing for the track and thumb is controlled via the CSS classes
 * `ada-toggle__track` and `ada-toggle__thumb` in base.css, which reference
 * `--motion-duration-quick` and `--motion-ease-standard` tokens (DEC-MOTION-003).
 * Inline styles previously hardcoded `transition: '... 0.2s'` — those have been
 * removed so that all motion timing flows through the token layer.
 *
 * @decision DEC-UI-005
 * @title Toggle uses hidden checkbox + visual div, not pure div with role
 * @status accepted
 * @rationale A real hidden checkbox gives native form semantics, keyboard
 *   interaction (space to toggle), and works with label `htmlFor` without
 *   additional ARIA wiring. The visual track/thumb pair is aria-hidden.
 */

import { useId, type CSSProperties } from 'react'

export interface ToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: string
  disabled?: boolean
}

const containerStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 'var(--space-sm)',
  cursor: 'pointer',
}

const containerDisabledStyle: CSSProperties = {
  opacity: 0.5,
  pointerEvents: 'none',
}

const trackBase: CSSProperties = {
  position: 'relative',
  width: '44px',
  height: '24px',
  borderRadius: '12px',
  // Transition handled by .ada-toggle__track in base.css (DEC-MOTION-003)
  flexShrink: 0,
}

const thumbBase: CSSProperties = {
  position: 'absolute',
  top: '2px',
  width: '20px',
  height: '20px',
  borderRadius: '50%',
  background: '#ffffff',
  // Transition handled by .ada-toggle__thumb in base.css (DEC-MOTION-003)
}

const labelTextStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-primary)',
}

const hiddenInput: CSSProperties = {
  position: 'absolute',
  opacity: 0,
  width: 0,
  height: 0,
  margin: 0,
  padding: 0,
}

export function Toggle({ checked, onChange, label, disabled = false }: ToggleProps) {
  const id = useId()

  const trackStyle: CSSProperties = {
    ...trackBase,
    background: checked ? 'var(--color-primary)' : 'var(--color-bg-elevated)',
  }

  const thumbStyle: CSSProperties = {
    ...thumbBase,
    left: checked ? '22px' : '2px',
  }

  return (
    <label
      htmlFor={id}
      style={{ ...containerStyle, ...(disabled ? containerDisabledStyle : undefined) }}
      className="ada-toggle"
    >
      <input
        id={id}
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        style={hiddenInput}
        aria-label={label}
      />
      <span className="ada-toggle__track" style={trackStyle} aria-hidden="true">
        <span className="ada-toggle__thumb" style={thumbStyle} />
      </span>
      {label && <span style={labelTextStyle}>{label}</span>}
    </label>
  )
}
