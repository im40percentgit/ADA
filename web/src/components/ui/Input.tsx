/**
 * Input — labelled text input with optional error message display.
 *
 * Wraps a native `<input>` inside a `<label>` with caption-sized label text
 * above and an error message below. All visual properties reference design
 * tokens. When `error` is truthy the border switches to the danger colour
 * and the message renders in danger text.
 *
 * Spreads remaining `InputHTMLAttributes` onto the `<input>` so callers
 * can pass `placeholder`, `value`, `onChange`, `name`, etc. directly.
 *
 * @decision DEC-UI-004
 * @title Input wraps native input with label + error, no controlled-only API
 * @status accepted
 * @rationale Keeping the component as a thin wrapper around the native input
 *   (via attribute spread) lets it work in both controlled and uncontrolled
 *   forms without duplicating React form state logic. The label/error chrome
 *   is pure presentation.
 */

import type { CSSProperties, InputHTMLAttributes } from 'react'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

const wrapperStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
}

const labelStyle: CSSProperties = {
  fontSize: 'var(--size-caption)',
  color: 'var(--color-text-muted)',
  marginBottom: '4px',
}

const inputBaseStyle: CSSProperties = {
  width: '100%',
  background: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-input)',
  height: 'var(--touch-target-min)',
  padding: '0 var(--space-sm)',
  color: 'var(--color-text-primary)',
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  boxSizing: 'border-box',
}

const inputErrorStyle: CSSProperties = {
  borderColor: 'var(--color-danger)',
}

const errorMsgStyle: CSSProperties = {
  fontSize: 'var(--size-caption)',
  color: 'var(--color-danger)',
  marginTop: '4px',
}

export function Input({ label, error, className, style, ...rest }: InputProps) {
  const inputStyle: CSSProperties = {
    ...inputBaseStyle,
    ...(error ? inputErrorStyle : undefined),
    ...style,
  }

  return (
    <label className={['ada-input', className].filter(Boolean).join(' ')} style={wrapperStyle}>
      {label && <span style={labelStyle}>{label}</span>}
      <input style={inputStyle} aria-invalid={error ? true : undefined} {...rest} />
      {error && <span style={errorMsgStyle} role="alert">{error}</span>}
    </label>
  )
}
